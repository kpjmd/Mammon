"""Aerodrome Finance protocol integration.

Aerodrome is the primary DEX on Base with $602M TVL.
https://aerodrome.finance/
"""

from typing import Any, Dict, List, Optional
from decimal import Decimal
from src.utils.logger import get_logger
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.utils.web3_provider import get_web3
from src.utils.aerodrome_abis import AERODROME_FACTORY_ABI, AERODROME_POOL_ABI
from src.utils.contracts import ERC20_ABI, ContractHelper, get_protocol_address
from .base import BaseProtocol, ProtocolPool

logger = get_logger(__name__)

# Aerodrome contract addresses by network
AERODROME_CONTRACTS = {
    "base-mainnet": {
        "router": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
        "factory": "0x420DD381b31aEf6683db6B902084cB0FFECe40Da",  # Verified ✅
        "aero_token": "0x940181a94A35A4569E4529A3CDfB74e38FD98631",
    },
    "base-sepolia": {
        # Using mock data for Phase 1C - real testnet addresses TBD
        "router": "0x0000000000000000000000000000000000000000",  # Mock
        "factory": "0x0000000000000000000000000000000000000000",  # Mock
    },
    "arbitrum-sepolia": {
        # Sprint 3 finding: Aerodrome is BASE-ONLY (not deployed on Arbitrum)
        "router": "0x0000000000000000000000000000000000000000",  # Not deployed
        "factory": "0x0000000000000000000000000000000000000000",  # Not deployed
    },
    "arbitrum-mainnet": {
        # Sprint 3 finding: Aerodrome is BASE-ONLY (not deployed on Arbitrum)
        "router": "0x0000000000000000000000000000000000000000",  # Not deployed
        "factory": "0x0000000000000000000000000000000000000000",  # Not deployed
    },
}


class AerodromeProtocol(BaseProtocol):
    """Aerodrome Finance protocol integration.

    Provides access to Aerodrome's liquidity pools and yield opportunities
    on Base network.

    For Phase 1B: Using mock pool data for testing.
    Phase 2: Will integrate with real contract calls and subgraph.

    Attributes:
        network: Network identifier (base-mainnet or base-sepolia)
        router_address: Aerodrome router contract address
        dry_run_mode: If True, returns mock data
        audit_logger: Audit logging instance
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize Aerodrome protocol integration.

        Args:
            config: Configuration including network and dry-run settings
        """
        super().__init__("Aerodrome", "base", config)
        self.network = config.get("network", "base-sepolia")
        self.router_address = AERODROME_CONTRACTS.get(self.network, {}).get("router", "")
        self.dry_run_mode = config.get("dry_run_mode", True)
        self.audit_logger = AuditLogger()

        if self.dry_run_mode:
            logger.info("🔒 AerodromeProtocol initialized in DRY RUN mode")

    async def get_pools(self) -> List[ProtocolPool]:
        """Fetch all available liquidity pools from Aerodrome.

        Phase 1C Sprint 3: Queries real pools from Base mainnet (read-only)
        For other networks: Returns mock data

        Returns:
            List of Aerodrome liquidity pools
        """
        # Log pool query
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {"protocol": "Aerodrome", "network": self.network, "action": "get_pools"},
        )

        # If Base mainnet and not dry-run, fetch REAL data
        if self.network == "base-mainnet" and not self.dry_run_mode:
            try:
                return await self._get_real_pools_from_mainnet()
            except Exception as e:
                logger.error(f"Failed to fetch real pools, falling back to mock: {e}")
                # Fall through to mock data

        # Return mock pools for testing/other networks
        mock_pools = [
            ProtocolPool(
                pool_id="aero-weth-usdc",
                name="WETH/USDC Pool",
                tokens=["WETH", "USDC"],
                apy=Decimal("15.7"),
                tvl=Decimal("12500000"),
                metadata={
                    "pool_address": "0x1234567890123456789012345678901234567890",
                    "fee_tier": "0.3%",
                    "volume_24h": Decimal("2500000"),
                },
            ),
            ProtocolPool(
                pool_id="aero-usdc-usdt",
                name="USDC/USDT Stable Pool",
                tokens=["USDC", "USDT"],
                apy=Decimal("8.3"),
                tvl=Decimal("8000000"),
                metadata={
                    "pool_address": "0x2345678901234567890123456789012345678901",
                    "fee_tier": "0.05%",
                    "volume_24h": Decimal("1800000"),
                },
            ),
            ProtocolPool(
                pool_id="aero-weth-aero",
                name="WETH/AERO Pool",
                tokens=["WETH", "AERO"],
                apy=Decimal("22.4"),
                tvl=Decimal("5500000"),
                metadata={
                    "pool_address": "0x3456789012345678901234567890123456789012",
                    "fee_tier": "1.0%",
                    "volume_24h": Decimal("800000"),
                },
            ),
        ]

        logger.info(f"Retrieved {len(mock_pools)} Aerodrome pools (mock data)")
        return mock_pools

    async def get_pool_apy(self, pool_id: str) -> Decimal:
        """Get current APY for an Aerodrome pool.

        Args:
            pool_id: Pool identifier

        Returns:
            Current APY
        """
        # Get all pools and find the matching one
        pools = await self.get_pools()

        for pool in pools:
            if pool.pool_id == pool_id:
                logger.debug(f"APY for {pool_id}: {pool.apy}%")
                return pool.apy

        logger.warning(f"Pool not found: {pool_id}")
        return Decimal("0")

    async def deposit(
        self,
        pool_id: str,
        token: str,
        amount: Decimal,
    ) -> str:
        """Add liquidity to an Aerodrome pool (DRY-RUN in Phase 1B).

        Args:
            pool_id: Target pool identifier
            token: Token to deposit
            amount: Amount to deposit

        Returns:
            Transaction hash (simulated in dry-run mode)
        """
        if self.dry_run_mode:
            tx_hash = f"dry_run_deposit_{pool_id}_{amount}_{token}"
            logger.info(f"🔒 DRY RUN: Would deposit {amount} {token} to pool {pool_id}")
            logger.info(f"   Simulated tx hash: {tx_hash}")

            # Log deposit attempt
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_INITIATED,
                AuditSeverity.INFO,
                {
                    "mode": "DRY_RUN",
                    "protocol": "Aerodrome",
                    "action": "deposit",
                    "pool_id": pool_id,
                    "token": token,
                    "amount": str(amount),
                },
            )

            return tx_hash

        # Live mode not implemented in Phase 1B
        raise NotImplementedError("Live deposits not implemented in Phase 1B")

    async def withdraw(
        self,
        pool_id: str,
        token: str,
        amount: Decimal,
    ) -> str:
        """Remove liquidity from an Aerodrome pool (DRY-RUN in Phase 1B).

        Args:
            pool_id: Source pool identifier
            token: Token to withdraw
            amount: Amount to withdraw

        Returns:
            Transaction hash (simulated in dry-run mode)
        """
        if self.dry_run_mode:
            tx_hash = f"dry_run_withdraw_{pool_id}_{amount}_{token}"
            logger.info(f"🔒 DRY RUN: Would withdraw {amount} {token} from pool {pool_id}")
            logger.info(f"   Simulated tx hash: {tx_hash}")

            # Log withdrawal attempt
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_INITIATED,
                AuditSeverity.INFO,
                {
                    "mode": "DRY_RUN",
                    "protocol": "Aerodrome",
                    "action": "withdraw",
                    "pool_id": pool_id,
                    "token": token,
                    "amount": str(amount),
                },
            )

            return tx_hash

        # Live mode not implemented in Phase 1B
        raise NotImplementedError("Live withdrawals not implemented in Phase 1B")

    async def get_user_balance(self, pool_id: str, user_address: str) -> Decimal:
        """Get user's LP token balance in an Aerodrome pool.

        Phase 1B: Returns mock balance for testing.

        Args:
            pool_id: Pool identifier
            user_address: User's wallet address

        Returns:
            User's LP token balance (mock data in Phase 1B)
        """
        # Mock balance for Phase 1B
        mock_balance = Decimal("0.0")

        logger.debug(f"Mock LP balance for {user_address} in {pool_id}: {mock_balance}")
        return mock_balance

    async def estimate_gas(self, operation: str, params: Dict[str, Any]) -> int:
        """Estimate gas for Aerodrome operations.

        Phase 1B: Returns mock gas estimates.

        Args:
            operation: Operation type (deposit, withdraw, swap)
            params: Operation parameters

        Returns:
            Estimated gas units (mock in Phase 1B)
        """
        # Mock gas estimates for Phase 1B
        gas_estimates = {
            "deposit": 250000,
            "withdraw": 200000,
            "swap": 180000,
        }

        estimate = gas_estimates.get(operation, 150000)
        logger.debug(f"Gas estimate for {operation}: {estimate}")

        return estimate

    async def build_swap_transaction(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        slippage: Decimal = Decimal("0.5"),
    ) -> Dict[str, Any]:
        """Build a swap transaction for Aerodrome (DRY-RUN in Phase 1B).

        Args:
            token_in: Input token symbol
            token_out: Output token symbol
            amount_in: Amount of input token
            slippage: Max slippage percentage (default: 0.5%)

        Returns:
            Transaction object (simulated in dry-run mode)
        """
        # Calculate minimum output with slippage
        # Simplified calculation for Phase 1B
        min_amount_out = amount_in * (Decimal("1") - slippage / Decimal("100"))

        tx = {
            "to": self.router_address,
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": str(amount_in),
            "min_amount_out": str(min_amount_out),
            "slippage": str(slippage),
            "network": self.network,
        }

        if self.dry_run_mode:
            logger.info(f"🔒 DRY RUN: Would swap {amount_in} {token_in} for {token_out}")
            logger.info(f"   Min output: {min_amount_out} {token_out}")
            logger.info(f"   Max slippage: {slippage}%")

            # Log swap attempt
            await self.audit_logger.log_event(
                AuditEventType.POOL_QUERY,
                AuditSeverity.INFO,
                {
                    "mode": "DRY_RUN",
                    "protocol": "Aerodrome",
                    "action": "build_swap",
                    "token_in": token_in,
                    "token_out": token_out,
                    "amount_in": str(amount_in),
                },
            )

            return {
                "dry_run": True,
                "would_execute": False,
                "swap_details": tx,
                "message": "Swap transaction built in dry-run mode",
            }

        # Live mode
        logger.warning(f"⚠️ LIVE MODE: Building real swap transaction")
        return tx

    async def _get_real_pools_from_mainnet(self, max_pools: int = 5) -> List[ProtocolPool]:
        """Query real Aerodrome pools from Base mainnet (read-only).

        Args:
            max_pools: Maximum number of pools to fetch (default: 5)

        Returns:
            List of real Aerodrome pools with actual on-chain data
        """
        logger.info(f"📡 Fetching REAL Aerodrome pools from Base mainnet...")

        # Get Web3 instance for Base mainnet
        w3 = get_web3("base-mainnet")

        # Get factory contract
        factory_address = AERODROME_CONTRACTS["base-mainnet"]["factory"]
        factory = ContractHelper.get_contract(w3, factory_address, AERODROME_FACTORY_ABI)

        # Get total number of pools
        pool_count = factory.functions.allPoolsLength().call()
        logger.info(f"Found {pool_count} total pools in Aerodrome factory")

        # Fetch pool data
        pools = []
        fetch_count = min(pool_count, max_pools)

        for i in range(fetch_count):
            try:
                # Get pool address
                pool_address = factory.functions.allPools(i).call()

                # Query pool data (synchronous Web3 calls)
                pool_data = self._query_pool_data(w3, pool_address, factory)

                if pool_data:
                    pools.append(pool_data)

                logger.debug(f"Fetched pool {i+1}/{fetch_count}: {pool_address}")

            except Exception as e:
                logger.warning(f"Failed to fetch pool {i}: {e}")
                continue

        logger.info(f"✅ Successfully fetched {len(pools)} real Aerodrome pools")
        return pools

    def _query_pool_data(
        self, w3: Any, pool_address: str, factory: Any
    ) -> Optional[ProtocolPool]:
        """Query data for a specific pool.

        Args:
            w3: Web3 instance
            pool_address: Pool contract address
            factory: Factory contract instance

        Returns:
            ProtocolPool with real data, or None if query fails
        """
        try:
            # Get pool contract
            pool = ContractHelper.get_contract(w3, pool_address, AERODROME_POOL_ABI)

            # Get pool metadata (includes tokens, reserves, decimals, stable flag)
            metadata = pool.functions.metadata().call()
            dec0, dec1, reserve0, reserve1, is_stable, token0_addr, token1_addr = metadata

            # Get token symbols
            token0_symbol = self._get_token_symbol(w3, token0_addr)
            token1_symbol = self._get_token_symbol(w3, token1_addr)

            # Get pool name
            try:
                pool_name = pool.functions.name().call()
            except:
                pool_name = f"{token0_symbol}/{token1_symbol} Pool"

            # Calculate TVL (simplified - sum of reserves in USD)
            # For accurate TVL we'd need token prices, using approximate for now
            tvl = self._estimate_tvl(reserve0, reserve1, dec0, dec1)

            # Get fee from factory
            fee = factory.functions.getFee(pool_address, is_stable).call()
            fee_percent = Decimal(fee) / Decimal(10000)  # Convert basis points to percent

            # Create pool ID
            pool_id = f"aero-{token0_symbol.lower()}-{token1_symbol.lower()}"
            if is_stable:
                pool_id += "-stable"

            # Create ProtocolPool
            return ProtocolPool(
                pool_id=pool_id,
                name=pool_name,
                tokens=[token0_symbol, token1_symbol],
                apy=Decimal("0"),  # APY calculation requires historical data
                tvl=tvl,
                metadata={
                    "pool_address": pool_address,
                    "token0": token0_addr,
                    "token1": token1_addr,
                    "reserve0": str(reserve0),
                    "reserve1": str(reserve1),
                    "decimals0": dec0,
                    "decimals1": dec1,
                    "is_stable": is_stable,
                    "fee_percent": str(fee_percent),
                    "source": "base_mainnet",
                    # TVL metadata flags (Sprint 3 safeguards)
                    "tvl_is_estimate": True,
                    "tvl_method": "simplified_1dollar",
                    "tvl_warning": "Do not use for calculations - Phase 2A will add real price oracle",
                },
            )

        except Exception as e:
            logger.error(f"Failed to query pool {pool_address}: {e}")
            return None

    def _get_token_symbol(self, w3: Any, token_address: str) -> str:
        """Get token symbol from contract.

        Args:
            w3: Web3 instance
            token_address: Token contract address

        Returns:
            Token symbol (or address if symbol not available)
        """
        try:
            token = ContractHelper.get_erc20_contract(w3, token_address)
            symbol = token.functions.symbol().call()
            return symbol
        except Exception as e:
            logger.warning(f"Could not get symbol for {token_address}: {e}")
            # Return shortened address as fallback
            return f"{token_address[:6]}...{token_address[-4:]}"

    def _estimate_tvl(
        self, reserve0: int, reserve1: int, decimals0: int, decimals1: int
    ) -> Decimal:
        """Estimate pool TVL (simplified calculation).

        ⚠️ WARNING: This is a SIMPLIFIED calculation that assumes $1 per token.

        This TVL estimate should ONLY be used for:
        - Relative comparisons between pools (ranking)
        - Display purposes in dashboards
        - Filtering pools by approximate size

        DO NOT use this TVL estimate for:
        - Financial calculations or yield computations
        - Risk assessments or position sizing
        - Any production trading decisions

        For accurate TVL, Phase 2A will integrate Chainlink price oracles to get
        real-time token prices in USD.

        Args:
            reserve0: Reserve of token0 (raw amount)
            reserve1: Reserve of token1 (raw amount)
            decimals0: Decimals of token0
            decimals1: Decimals of token1

        Returns:
            Estimated TVL in USD (APPROXIMATE - see warnings above)
        """
        # Convert reserves to human-readable amounts
        amount0 = Decimal(reserve0) / Decimal(10**decimals0)
        amount1 = Decimal(reserve1) / Decimal(10**decimals1)

        # Simplified: assume $1 per token (we'll improve this in Phase 2A with price oracle)
        tvl = amount0 + amount1

        return tvl
