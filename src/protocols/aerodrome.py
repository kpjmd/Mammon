"""Aerodrome Finance protocol integration.

Aerodrome is the primary DEX on Base with $602M TVL.
https://aerodrome.finance/
"""

from typing import Any, Dict, List, Optional
from decimal import Decimal
import asyncio
from src.utils.logger import get_logger
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings
from src.utils.aerodrome_abis import AERODROME_FACTORY_ABI, AERODROME_POOL_ABI
from src.utils.contracts import ERC20_ABI, ContractHelper, get_protocol_address
from src.data.oracles import PriceOracle, create_price_oracle
from src.api.aerodrome_bitquery import create_bitquery_client
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

        # Initialize price oracle for TVL calculations
        self._init_price_oracle(config)

        # Performance optimization settings
        self.max_pools = config.get("aerodrome_max_pools", 10)
        supported_tokens_str = config.get("supported_tokens", "ETH,WETH,USDC,USDT,DAI,BTC,WBTC")
        self.supported_tokens = set(token.strip().upper() for token in supported_tokens_str.split(","))

        # BitQuery integration settings
        self.use_bitquery = config.get("aerodrome_use_bitquery", True)
        self.bitquery_api_key = config.get("bitquery_api_key")
        self.aerodrome_min_tvl_usd = Decimal(str(config.get("aerodrome_min_tvl_usd", "10000")))
        self.aerodrome_min_volume_24h = Decimal(str(config.get("aerodrome_min_volume_24h", "100")))
        self.aerodrome_token_whitelist = set(
            token.strip().upper()
            for token in config.get("aerodrome_token_whitelist", "USDC,WETH,USDT,DAI,WBTC,AERO").split(",")
        )

        if self.dry_run_mode:
            logger.info("🔒 AerodromeProtocol initialized in DRY RUN mode")
        logger.info(
            f"📊 AerodromeProtocol: max_pools={self.max_pools}, "
            f"supported_tokens={len(self.supported_tokens)}, "
            f"use_bitquery={self.use_bitquery}"
        )

    def _init_price_oracle(self, config: Dict[str, Any]) -> None:
        """Initialize price oracle for TVL calculations.

        Uses Chainlink if enabled, otherwise falls back to mock oracle.

        Args:
            config: Configuration dict
        """
        # Check if shared price oracle provided in config
        if "price_oracle" in config and config["price_oracle"] is not None:
            self.price_oracle = config["price_oracle"]
            logger.info("Using shared price oracle from config")
            return

        chainlink_enabled = config.get("chainlink_enabled", True)

        if chainlink_enabled:
            # Use Chainlink oracle with Base mainnet for price data
            price_network = config.get("chainlink_price_network", "base-mainnet")
            cache_ttl = config.get("chainlink_cache_ttl_seconds", 300)
            max_staleness = config.get("chainlink_max_staleness_seconds", 3600)
            fallback_to_mock = config.get("chainlink_fallback_to_mock", True)

            logger.info(
                f"Initializing Chainlink price oracle: "
                f"price_network={price_network}, cache_ttl={cache_ttl}s"
            )

            self.price_oracle = create_price_oracle(
                "chainlink",
                network=self.network,
                price_network=price_network,
                cache_ttl_seconds=cache_ttl,
                max_staleness_seconds=max_staleness,
                fallback_to_mock=fallback_to_mock,
            )
        else:
            logger.info("Using mock price oracle (Chainlink disabled)")
            self.price_oracle = create_price_oracle("mock")

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

        # If Base mainnet, fetch REAL data (dry_run only affects transactions, not data)
        # Note: dry_run_mode controls transaction execution in RebalanceExecutor,
        # not data fetching. We want real pool data even when testing.
        if self.network == "base-mainnet":
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

    async def _get_real_pools_from_mainnet(self) -> List[ProtocolPool]:
        """Query real Aerodrome pools from Base mainnet (read-only).

        Uses hybrid approach:
        1. BitQuery API to get filtered pool list (if enabled)
        2. On-chain validation for real-time data
        3. Falls back to factory queries if BitQuery fails

        Returns:
            List of real Aerodrome pools with actual on-chain data
        """
        logger.info(f"📡 Fetching Aerodrome pools from Base mainnet...")
        print(f"📡 [AERODROME] Fetching pools from Base mainnet...", flush=True)

        # Debug: Log BitQuery configuration
        logger.info(f"🔧 BitQuery config: use_bitquery={self.use_bitquery}, "
                   f"api_key={'SET' if self.bitquery_api_key else 'NOT SET'}, "
                   f"max_pools={self.max_pools}")
        print(f"🔧 [AERODROME] BitQuery config: use_bitquery={self.use_bitquery}, "
              f"api_key={'SET' if self.bitquery_api_key else 'NOT SET'}, "
              f"max_pools={self.max_pools}", flush=True)

        # Try BitQuery API first if enabled
        if self.use_bitquery:
            logger.info("✅ BitQuery is ENABLED - attempting BitQuery API method")
            print("✅ [AERODROME] BitQuery is ENABLED - attempting BitQuery API method", flush=True)
            try:
                pools = await self._get_pools_via_bitquery()
                logger.info(f"✅ BitQuery method succeeded: {len(pools)} pools returned")
                print(f"✅ [AERODROME] BitQuery method succeeded: {len(pools)} pools returned", flush=True)
                return pools
            except Exception as e:
                logger.warning(
                    f"❌ BitQuery failed: {e}. Falling back to factory method with limit={self.max_pools}"
                )
                print(f"❌ [AERODROME] BitQuery failed: {e}. Falling back to factory method", flush=True)
                # Fall through to factory method
        else:
            logger.info(f"⚠️  BitQuery is DISABLED - using factory method directly")
            print("⚠️  [AERODROME] BitQuery is DISABLED - using factory method directly", flush=True)

        # Fallback: Direct factory queries (legacy method)
        logger.info(f"🏭 Using factory method with max_pools={self.max_pools}")
        print(f"🏭 [AERODROME] Using factory method with max_pools={self.max_pools}", flush=True)
        return await self._get_pools_via_factory()

    async def _get_pools_via_bitquery(self) -> List[ProtocolPool]:
        """Fetch pools using BitQuery API + on-chain validation.

        Returns:
            List of validated Aerodrome pools
        """
        logger.info("🔍 Using BitQuery to filter Aerodrome pools...")
        print("🔍 [BITQUERY] Using BitQuery to filter Aerodrome pools...", flush=True)
        logger.info(f"   Filters: min_tvl=${self.aerodrome_min_tvl_usd}, "
                   f"min_volume_24h=${self.aerodrome_min_volume_24h}, "
                   f"tokens={self.aerodrome_token_whitelist}")
        print(f"   Filters: min_tvl=${self.aerodrome_min_tvl_usd}, "
              f"min_volume_24h=${self.aerodrome_min_volume_24h}, "
              f"tokens={self.aerodrome_token_whitelist}", flush=True)

        # Create BitQuery client
        logger.info("📡 Creating BitQuery client...")
        print("📡 [BITQUERY] Creating BitQuery client...", flush=True)
        bitquery_client = await create_bitquery_client(
            api_key=self.bitquery_api_key,
            min_tvl_usd=self.aerodrome_min_tvl_usd,
            min_volume_24h=self.aerodrome_min_volume_24h,
            token_whitelist=self.aerodrome_token_whitelist,
        )
        logger.info("✅ BitQuery client created successfully")
        print("✅ [BITQUERY] Client created successfully", flush=True)

        try:
            # Get filtered pool list from BitQuery
            logger.info("🌐 Calling BitQuery API...")
            print("🌐 [BITQUERY] Calling BitQuery API...", flush=True)
            bitquery_pools = await bitquery_client.get_quality_pools()
            logger.info(f"✅ BitQuery API call completed")
            print(f"✅ [BITQUERY] API call completed", flush=True)

            if not bitquery_pools:
                logger.warning("BitQuery returned no pools, falling back to factory")
                print("⚠️  [BITQUERY] No pools returned, falling back to factory", flush=True)
                raise ValueError("No pools returned from BitQuery")

            logger.info(f"BitQuery returned {len(bitquery_pools)} candidate pools")
            print(f"📊 [BITQUERY] Returned {len(bitquery_pools)} candidate pools", flush=True)

            # Sort by volume (highest first) and limit to top N for on-chain validation
            # This prevents timeout by only validating the most active pools
            bitquery_pools = sorted(
                bitquery_pools,
                key=lambda p: p.get("volume_24h_usd", 0),
                reverse=True
            )

            # Get Web3 instance for on-chain validation
            settings = get_settings()
            w3 = get_web3("base-mainnet", config=settings)
            factory_address = AERODROME_CONTRACTS["base-mainnet"]["factory"]
            factory = ContractHelper.get_contract(w3, factory_address, AERODROME_FACTORY_ABI)

            # Validate each pool on-chain and fetch real-time data
            pools = []
            max_to_fetch = min(len(bitquery_pools), self.max_pools)

            logger.info(
                f"Validating top {max_to_fetch} pools by volume on-chain "
                f"(from {len(bitquery_pools)} BitQuery results)..."
            )
            print(f"🔄 [BITQUERY] Validating top {max_to_fetch} pools on-chain...", flush=True)

            for i, pool_info in enumerate(bitquery_pools[:max_to_fetch]):
                print(f"   [{i+1}/{max_to_fetch}] Validating pool {pool_info.get('pool_address', 'unknown')[:10]}...", flush=True)
                try:
                    pool_address = pool_info["pool_address"]

                    # Query real-time pool data on-chain
                    pool_data = await self._query_pool_data(w3, pool_address, factory)

                    if pool_data:
                        pools.append(pool_data)
                        logger.debug(
                            f"[{i+1}/{max_to_fetch}] Validated {pool_data.pool_id} "
                            f"(TVL: ${pool_data.tvl:.2f})"
                        )

                except Exception as e:
                    logger.warning(f"Failed to validate pool {pool_address}: {e}")
                    continue

            logger.info(f"✅ BitQuery method: Successfully fetched {len(pools)} validated pools")
            return pools

        finally:
            await bitquery_client.close()

    async def _get_pools_via_factory(self) -> List[ProtocolPool]:
        """Fetch pools using direct factory queries (legacy fallback method).

        This is the original method that queries pools sequentially from the factory.
        Much slower than BitQuery, but guaranteed to work.

        Returns:
            List of Aerodrome pools
        """
        logger.info(f"📡 Using factory method (max {self.max_pools} pools)...")

        # Get Web3 instance for Base mainnet
        settings = get_settings()
        w3 = get_web3("base-mainnet", config=settings)

        # Get factory contract
        factory_address = AERODROME_CONTRACTS["base-mainnet"]["factory"]
        factory = ContractHelper.get_contract(w3, factory_address, AERODROME_FACTORY_ABI)

        # Get total number of pools
        pool_count = await asyncio.to_thread(factory.functions.allPoolsLength().call)
        logger.info(f"Found {pool_count} total pools in Aerodrome factory")

        # Fetch pool data (limited by max_pools)
        pools = []
        fetch_count = min(pool_count, self.max_pools)

        logger.warning(
            f"⚠️ Factory method will only check first {fetch_count} pools "
            f"(out of {pool_count} total). Consider enabling BitQuery for better coverage."
        )

        for i in range(fetch_count):
            try:
                # Get pool address
                pool_address = await asyncio.to_thread(factory.functions.allPools(i).call)

                # Query pool data
                pool_data = await self._query_pool_data(w3, pool_address, factory)

                if pool_data:
                    # Filter: Only include pools with supported tokens
                    tokens = pool_data.tokens
                    if any(token.upper() in self.supported_tokens for token in tokens):
                        pools.append(pool_data)
                    else:
                        logger.debug(
                            f"Skipping Aerodrome {'/'.join(tokens)} pool "
                            f"(tokens not in supported list)"
                        )

            except Exception as e:
                logger.warning(f"Failed to fetch pool {i}: {e}")
                continue

        logger.info(f"✅ Factory method: Successfully fetched {len(pools)} pools")
        return pools

    async def _query_pool_data(
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
            # Ensure pool address is checksummed (BitQuery returns lowercase addresses)
            pool_address = w3.to_checksum_address(pool_address)
            # Get pool contract
            pool = ContractHelper.get_contract(w3, pool_address, AERODROME_POOL_ABI)

            # Get pool metadata (includes tokens, reserves, decimals, stable flag)
            metadata = await asyncio.to_thread(pool.functions.metadata().call)
            dec0, dec1, reserve0, reserve1, is_stable, token0_addr, token1_addr = metadata

            # Get token symbols (async to avoid blocking)
            token0_symbol = await self._get_token_symbol(w3, token0_addr)
            token1_symbol = await self._get_token_symbol(w3, token1_addr)

            # Get pool name (wrap blocking call in thread pool)
            try:
                pool_name = await asyncio.to_thread(pool.functions.name().call)
            except:
                pool_name = f"{token0_symbol}/{token1_symbol} Pool"

            # Calculate TVL using Chainlink price oracle (with timeout protection)
            try:
                tvl, tvl_metadata = await asyncio.wait_for(
                    self._estimate_tvl(
                        reserve0, reserve1, dec0, dec1, token0_symbol, token1_symbol
                    ),
                    timeout=15.0  # 15 second timeout for TVL estimation
                )
            except asyncio.TimeoutError:
                logger.warning(f"TVL estimation timed out for {token0_symbol}/{token1_symbol}")
                tvl = Decimal("0")
                tvl_metadata = {"error": "timeout"}

            # Get fee from factory (wrap blocking call in thread pool)
            fee = await asyncio.to_thread(factory.functions.getFee(pool_address, is_stable).call)
            fee_percent = Decimal(fee) / Decimal(10000)  # Convert basis points to percent

            # Create pool ID
            pool_id = f"aero-{token0_symbol.lower()}-{token1_symbol.lower()}"
            if is_stable:
                pool_id += "-stable"

            # Create ProtocolPool with accurate TVL pricing metadata
            pool_metadata = {
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
            }

            # Merge TVL pricing metadata
            pool_metadata.update(tvl_metadata)

            pool = ProtocolPool(
                pool_id=pool_id,
                name=pool_name,
                tokens=[token0_symbol, token1_symbol],
                apy=Decimal("0"),  # APY calculation requires historical data
                tvl=tvl,
                metadata=pool_metadata,
            )
            return pool

        except Exception as e:
            logger.error(f"Failed to query pool {pool_address}: {e}")
            return None

    async def _get_token_symbol(self, w3: Any, token_address: str) -> str:
        """Get token symbol from contract (async to avoid blocking).

        Args:
            w3: Web3 instance
            token_address: Token contract address

        Returns:
            Token symbol (or address if symbol not available)
        """
        try:
            token = ContractHelper.get_erc20_contract(w3, token_address)
            # Wrap blocking call in thread pool
            symbol = await asyncio.to_thread(token.functions.symbol().call)
            return symbol
        except Exception as e:
            logger.warning(f"Could not get symbol for {token_address}: {e}")
            # Return shortened address as fallback
            return f"{token_address[:6]}...{token_address[-4:]}"

    async def _estimate_tvl(
        self,
        reserve0: int,
        reserve1: int,
        decimals0: int,
        decimals1: int,
        token0_symbol: str,
        token1_symbol: str,
    ) -> tuple[Decimal, Dict[str, Any]]:
        """Calculate pool TVL using real price oracle data.

        Phase 2A Sprint 2: Now uses Chainlink price oracles for accurate pricing.

        Args:
            reserve0: Reserve of token0 (raw amount)
            reserve1: Reserve of token1 (raw amount)
            decimals0: Decimals of token0
            decimals1: Decimals of token1
            token0_symbol: Symbol of token0 (e.g., "ETH", "USDC")
            token1_symbol: Symbol of token1

        Returns:
            Tuple of (TVL in USD, metadata dict with pricing info)

        Metadata includes:
            - price0: Token0 price in USD
            - price1: Token1 price in USD
            - tvl_method: "chainlink_oracle" or "mock_oracle"
            - price_source: Network prices were fetched from
        """
        # Convert reserves to human-readable amounts
        # Note: Aerodrome metadata() returns decimals as 10^n (multiplier), not n
        # So dec0=1000000 means 6 decimals (10^6), not that we need to compute 10^1000000
        amount0 = Decimal(reserve0) / Decimal(decimals0)
        amount1 = Decimal(reserve1) / Decimal(decimals1)

        # Initialize metadata
        metadata = {
            "token0_amount": str(amount0),
            "token1_amount": str(amount1),
        }

        try:
            # Get prices from oracle with timeout (individual calls are more robust)
            price0 = await asyncio.wait_for(
                self.price_oracle.get_price(token0_symbol),
                timeout=10.0
            )
            price1 = await asyncio.wait_for(
                self.price_oracle.get_price(token1_symbol),
                timeout=10.0
            )

            # Calculate TVL using real prices
            tvl = (amount0 * price0) + (amount1 * price1)

            # Add pricing metadata
            metadata.update({
                "price0_usd": str(price0),
                "price1_usd": str(price1),
                "tvl_method": "chainlink_oracle" if hasattr(self.price_oracle, "price_network") else "mock_oracle",
                "price_source": getattr(self.price_oracle, "price_network", "mock"),
            })

            logger.debug(
                f"TVL calculation: {amount0:.2f} {token0_symbol} @ ${price0} + "
                f"{amount1:.2f} {token1_symbol} @ ${price1} = ${tvl:.2f}"
            )

            return tvl, metadata

        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout fetching prices for {token0_symbol}/{token1_symbol}. "
                f"Using $1 fallback estimate."
            )
            # Fallback to $1 per token estimate
            tvl = amount0 + amount1
            metadata.update({
                "price0_usd": "1.00",
                "price1_usd": "1.00",
                "tvl_method": "fallback_estimate",
                "tvl_error": "timeout",
                "tvl_warning": "Price fetch timeout - using $1 per token estimate",
            })
            return tvl, metadata

        except Exception as e:
            # If price fetching fails, log error and use fallback
            logger.error(
                f"Failed to fetch prices for {token0_symbol}/{token1_symbol}: {e}. "
                f"Using $1 fallback estimate."
            )

            # Fallback to $1 per token estimate
            tvl = amount0 + amount1

            metadata.update({
                "price0_usd": "1.00",
                "price1_usd": "1.00",
                "tvl_method": "fallback_estimate",
                "tvl_error": str(e),
                "tvl_warning": "Prices unavailable - using $1 per token estimate",
            })
            return tvl, metadata
