"""Gas price fetching and cost calculation utilities.

This module provides comprehensive gas estimation including:
- Gas price fetching (legacy and EIP-1559)
- Total gas cost calculation in ETH and USD
- Network-specific strategies
- Caching for performance
"""

from typing import Dict, Optional, Tuple
from decimal import Decimal
from enum import Enum
import time
from web3 import Web3

from src.utils.logger import get_logger
from src.utils.web3_provider import get_web3
from src.data.oracles import PriceOracle

logger = get_logger(__name__)


class GasEstimateMode(Enum):
    """Gas estimation strategies."""

    SIMULATION = "simulation"  # eth_call + eth_estimateGas (more accurate, slower)
    DIRECT = "direct"  # eth_estimateGas only (faster, less accurate)


class GasEstimator:
    """Estimates gas costs and fetches gas prices.

    Provides both gas limit estimation and gas price fetching,
    with support for different network types (legacy vs EIP-1559).

    Attributes:
        network: Network identifier
        w3: Web3 instance
        price_oracle: Price oracle for ETH/USD conversion
        cache_ttl: Cache TTL in seconds
        max_gas_price_gwei: Maximum acceptable gas price
        estimate_mode: Estimation strategy (simulation or direct)
    """

    def __init__(
        self,
        network: str,
        price_oracle: PriceOracle,
        cache_ttl_seconds: int = 300,
        max_gas_price_gwei: Optional[int] = None,
        estimate_mode: GasEstimateMode = GasEstimateMode.DIRECT,
    ) -> None:
        """Initialize gas estimator.

        Args:
            network: Network identifier (e.g., "base-sepolia")
            price_oracle: Price oracle for ETH/USD conversion
            cache_ttl_seconds: Cache time-to-live (default: 300s)
            max_gas_price_gwei: Maximum acceptable gas price in gwei (None = no limit)
            estimate_mode: Estimation mode (simulation or direct)
        """
        self.network = network
        self.w3 = get_web3(network)
        self.price_oracle = price_oracle
        self.cache_ttl = cache_ttl_seconds
        self.max_gas_price_gwei = max_gas_price_gwei
        self.estimate_mode = estimate_mode

        # Cache: {cache_key: (value, timestamp)}
        self._gas_price_cache: Optional[Tuple[int, float]] = None
        self._estimate_cache: Dict[str, Tuple[int, float]] = {}

        # Network characteristics
        self.supports_eip1559 = self._check_eip1559_support()

        logger.info(
            f"Initialized GasEstimator for {network}: "
            f"mode={estimate_mode.value}, eip1559={self.supports_eip1559}, "
            f"max_gas_price={max_gas_price_gwei}gwei"
        )

    def _check_eip1559_support(self) -> bool:
        """Check if network supports EIP-1559.

        Returns:
            True if network supports EIP-1559, False otherwise
        """
        # Base network uses EIP-1559, Arbitrum also supports it
        # For now, detect by trying to get base fee
        try:
            latest_block = self.w3.eth.get_block("latest")
            return hasattr(latest_block, "baseFeePerGas")
        except Exception as e:
            logger.warning(f"Could not detect EIP-1559 support: {e}")
            return False

    async def get_gas_price(self) -> int:
        """Get current gas price in wei.

        Uses cached value if available and fresh. For EIP-1559 networks,
        returns base fee + priority fee.

        Returns:
            Gas price in wei

        Raises:
            ValueError: If gas price exceeds configured maximum
        """
        # Check cache first
        if self._gas_price_cache:
            cached_price, cached_time = self._gas_price_cache
            if time.time() - cached_time < self.cache_ttl:
                logger.debug(f"Using cached gas price: {cached_price} wei")
                return cached_price

        # Fetch fresh gas price
        try:
            if self.supports_eip1559:
                # EIP-1559: base fee + priority fee
                latest_block = self.w3.eth.get_block("latest")
                base_fee = latest_block["baseFeePerGas"]

                # Get suggested priority fee (or use default 1 gwei)
                try:
                    priority_fee = self.w3.eth.max_priority_fee
                except:
                    priority_fee = self.w3.to_wei(1, "gwei")

                gas_price = base_fee + priority_fee
                logger.debug(
                    f"EIP-1559 gas price: base={base_fee} + priority={priority_fee} "
                    f"= {gas_price} wei"
                )
            else:
                # Legacy: simple gas price
                gas_price = self.w3.eth.gas_price
                logger.debug(f"Legacy gas price: {gas_price} wei")

            # Check against maximum if configured
            if self.max_gas_price_gwei:
                max_gas_price_wei = self.w3.to_wei(self.max_gas_price_gwei, "gwei")
                if gas_price > max_gas_price_wei:
                    raise ValueError(
                        f"Gas price {self.w3.from_wei(gas_price, 'gwei'):.2f} gwei "
                        f"exceeds maximum {self.max_gas_price_gwei} gwei"
                    )

            # Update cache
            self._gas_price_cache = (gas_price, time.time())

            gas_price_gwei = self.w3.from_wei(gas_price, "gwei")
            logger.info(f"Current gas price: {gas_price_gwei:.2f} gwei ({gas_price} wei)")

            return gas_price

        except Exception as e:
            logger.error(f"Failed to fetch gas price: {e}")
            # Return network-appropriate default
            # Base L2: 0.01 gwei, Ethereum: 50 gwei
            if "base" in self.network.lower():
                default_gwei = 0.01  # Base L2 pricing
            else:
                default_gwei = 50  # Ethereum mainnet pricing

            default_gas_price = self.w3.to_wei(default_gwei, "gwei")
            logger.warning(f"Using default gas price: {default_gwei} gwei for {self.network}")
            return default_gas_price

    async def estimate_gas(
        self,
        to: str,
        value: int = 0,
        data: str = "0x",
        from_address: Optional[str] = None,
    ) -> int:
        """Estimate gas limit for a transaction.

        Uses simulation mode (eth_call then eth_estimateGas) or direct mode
        based on configuration.

        Args:
            to: Target address
            value: ETH value in wei
            data: Transaction data
            from_address: Sender address (optional)

        Returns:
            Estimated gas limit with safety buffer
        """
        # Check cache (using transaction hash as key)
        cache_key = f"{to}:{value}:{data[:20]}"  # Truncate data for cache key
        if cache_key in self._estimate_cache:
            cached_estimate, cached_time = self._estimate_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                logger.debug(f"Using cached gas estimate: {cached_estimate}")
                return cached_estimate

        try:
            # Build transaction params
            tx_params = {
                "to": Web3.to_checksum_address(to),
                "value": value,
            }

            if data and data != "0x":
                tx_params["data"] = data

            if from_address:
                tx_params["from"] = Web3.to_checksum_address(from_address)

            # Simulation mode: try eth_call first
            if self.estimate_mode == GasEstimateMode.SIMULATION:
                try:
                    self.w3.eth.call(tx_params)
                    logger.debug("Transaction simulation succeeded")
                except Exception as e:
                    logger.warning(f"Transaction simulation failed: {e}")
                    # Continue to estimation anyway

            # Estimate gas
            estimated_gas = self.w3.eth.estimate_gas(tx_params)

            # Apply tiered safety buffer based on complexity
            data_length = len(data) if data and data != "0x" else 0

            if value > 0 and data_length == 0:
                # Simple ETH transfer
                buffer_percent = 1.20  # 20%
                complexity = "simple_transfer"
            elif data_length < 100:
                # Simple contract call (e.g., ERC20 transfer)
                buffer_percent = 1.30  # 30%
                complexity = "simple_contract"
            elif data_length < 500:
                # DEX swap or moderate complexity
                buffer_percent = 1.50  # 50%
                complexity = "dex_swap"
            else:
                # Complex operation (multi-hop, batch)
                buffer_percent = 2.00  # 100%
                complexity = "complex_operation"

            gas_with_buffer = int(estimated_gas * buffer_percent)

            logger.info(
                f"Gas estimate: {estimated_gas} units ({complexity}, "
                f"{int((buffer_percent-1)*100)}% buffer) → {gas_with_buffer} units"
            )

            # Update cache
            self._estimate_cache[cache_key] = (gas_with_buffer, time.time())

            return gas_with_buffer

        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            # Provide conservative default
            if data and len(data) > 100:
                default_gas = 500000  # Complex operation default
            elif data and data != "0x":
                default_gas = 100000  # Contract call default
            else:
                default_gas = 21000  # Simple transfer default

            logger.warning(f"Using default gas estimate: {default_gas}")
            return int(default_gas * 1.2)  # Add 20% buffer to default

    async def calculate_gas_cost(
        self,
        gas_limit: int,
        in_usd: bool = True,
    ) -> Decimal:
        """Calculate total gas cost.

        Args:
            gas_limit: Gas limit in units
            in_usd: If True, return cost in USD; if False, return in ETH

        Returns:
            Gas cost in USD or ETH
        """
        # Get current gas price
        gas_price_wei = await self.get_gas_price()

        # Calculate total cost in wei
        total_cost_wei = gas_limit * gas_price_wei

        # Convert to ETH
        total_cost_eth = Decimal(str(self.w3.from_wei(total_cost_wei, "ether")))

        if not in_usd:
            return total_cost_eth

        # Convert to USD using price oracle
        try:
            eth_price_usd = await self.price_oracle.get_price("ETH", "USD")
            total_cost_usd = total_cost_eth * eth_price_usd

            logger.info(
                f"Gas cost: {gas_limit} units × {self.w3.from_wei(gas_price_wei, 'gwei'):.2f} gwei "
                f"= {total_cost_eth:.6f} ETH = ${total_cost_usd:.2f}"
            )

            return total_cost_usd

        except Exception as e:
            logger.error(f"Failed to convert gas cost to USD: {e}")
            # Return ETH value as fallback
            logger.warning(f"Returning gas cost in ETH: {total_cost_eth}")
            return total_cost_eth

    async def estimate_transaction_cost(
        self,
        to: str,
        value: int = 0,
        data: str = "0x",
        from_address: Optional[str] = None,
    ) -> Dict[str, any]:
        """Estimate complete transaction cost including gas.

        Args:
            to: Target address
            value: ETH value in wei
            data: Transaction data
            from_address: Sender address (optional)

        Returns:
            Dict with gas_limit, gas_price, gas_cost_eth, gas_cost_usd,
            total_value_eth, total_cost_usd
        """
        # Estimate gas limit
        gas_limit = await self.estimate_gas(to, value, data, from_address)

        # Get gas price
        gas_price_wei = await self.get_gas_price()

        # Calculate gas cost
        gas_cost_eth = await self.calculate_gas_cost(gas_limit, in_usd=False)
        gas_cost_usd = await self.calculate_gas_cost(gas_limit, in_usd=True)

        # Calculate total value (value + gas)
        value_eth = Decimal(str(self.w3.from_wei(value, "ether")))
        total_value_eth = value_eth + gas_cost_eth

        # Convert total to USD
        try:
            eth_price_usd = await self.price_oracle.get_price("ETH", "USD")
            total_cost_usd = total_value_eth * eth_price_usd
        except:
            total_cost_usd = gas_cost_usd  # Fallback to just gas cost in USD

        return {
            "gas_limit": gas_limit,
            "gas_price_wei": gas_price_wei,
            "gas_price_gwei": float(self.w3.from_wei(gas_price_wei, "gwei")),
            "gas_cost_eth": gas_cost_eth,
            "gas_cost_usd": gas_cost_usd,
            "value_eth": value_eth,
            "total_value_eth": total_value_eth,
            "total_cost_usd": total_cost_usd,
        }

    def clear_cache(self) -> None:
        """Clear all cached gas data."""
        self._gas_price_cache = None
        self._estimate_cache.clear()
        logger.debug("Cleared gas estimator cache")
