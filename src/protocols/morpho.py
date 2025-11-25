"""Morpho protocol integration.

Morpho is a Coinbase-promoted lending protocol optimizing yields.
https://morpho.org/

Phase 3 Sprint 2: Read-only implementation with REAL BASE MAINNET data.
"""

from typing import Any, Dict, List, Optional
from decimal import Decimal
import requests
from src.utils.logger import get_logger
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings
from src.data.oracles import create_price_oracle
from .base import BaseProtocol, ProtocolPool

logger = get_logger(__name__)

# Morpho GraphQL API endpoint
MORPHO_API_URL = "https://blue-api.morpho.org/graphql"

# Morpho contract addresses by network
MORPHO_CONTRACTS = {
    "base-mainnet": {
        "morpho_blue": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",  # Core protocol
        "morpho_token": "0xBAa5CC21fd487B8Fcc2F632f3F4E8D37262a0842",  # MORPHO token
    },
    "base-sepolia": {
        "morpho_chainlink_oracle_v2": "0x2DC205F24BCb6B311E5cdf0745B0741648Aebd3d",  # Verified ✅
        # Using oracle address for testnet development
    },
}

# Base network chain ID
BASE_CHAIN_ID = 8453


class MorphoProtocol(BaseProtocol):
    """Morpho lending protocol integration.

    Provides access to Morpho's optimized lending markets on Base.

    Phase 3 Sprint 2: Read-only mode with REAL BASE MAINNET data.
    Queries Morpho Blue markets via GraphQL API.

    Attributes:
        network: Network identifier (base-mainnet or base-sepolia)
        use_mock_data: If True, returns mock data for development
        read_only: If True, prevents any write operations (safety)
        audit_logger: Audit logging instance
        price_oracle: Price oracle for TVL calculations
        web3: Web3 instance for blockchain queries
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize Morpho protocol integration.

        Args:
            config: Configuration including network and safety settings
        """
        super().__init__("Morpho", "base", config)
        self.network = config.get("network", "base-sepolia")
        self.use_mock_data = config.get("use_mock_data", False)  # Default to real data
        self.read_only = config.get("read_only", True)
        self.audit_logger = AuditLogger()

        # Get contract addresses for this network
        self.contracts = MORPHO_CONTRACTS.get("base-mainnet", {})  # Always read from mainnet

        # Initialize Web3 for BASE MAINNET queries with premium RPC support
        settings = get_settings()
        self.web3 = get_web3("base-mainnet", config=settings)

        # Initialize price oracle for TVL calculations
        self._init_price_oracle(config)

        # Performance optimization settings
        self.max_markets = config.get("morpho_max_markets", 20)
        supported_tokens_str = config.get("supported_tokens", "ETH,WETH,USDC,USDT,DAI,BTC,WBTC")
        self.supported_tokens = set(token.strip().upper() for token in supported_tokens_str.split(","))

        if self.read_only:
            logger.info("🔒 MorphoProtocol initialized in READ-ONLY mode")
        if not self.use_mock_data:
            logger.info(
                f"📊 MorphoProtocol querying REAL data from Base mainnet "
                f"(max_markets={self.max_markets}, supported_tokens={len(self.supported_tokens)})"
            )

    def _init_price_oracle(self, config: Dict[str, Any]) -> None:
        """Initialize price oracle for TVL calculations.

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
            price_network = "base-mainnet"  # Always use mainnet for prices
            cache_ttl = config.get("chainlink_cache_ttl_seconds", 300)
            max_staleness = config.get("chainlink_max_staleness_seconds", 3600)
            fallback_to_mock = config.get("chainlink_fallback_to_mock", True)

            logger.info(
                f"Initializing Chainlink price oracle: "
                f"price_network={price_network}, cache_ttl={cache_ttl}s"
            )

            self.price_oracle = create_price_oracle(
                "chainlink",
                network="base-mainnet",
                price_network=price_network,
                cache_ttl_seconds=cache_ttl,
                max_staleness_seconds=max_staleness,
                fallback_to_mock=fallback_to_mock,
            )
        else:
            logger.info("Using mock price oracle (Chainlink disabled)")
            self.price_oracle = create_price_oracle("mock")

    def _query_morpho_api(self, query: str, variables: Dict[str, Any] = None, max_retries: int = 3) -> Dict[str, Any]:
        """Query Morpho Blue GraphQL API with retry logic.

        Phase 4 Sprint 3: Added retry logic and increased timeout for reliability.

        Args:
            query: GraphQL query string
            variables: Query variables
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            API response data

        Raises:
            Exception: If all retry attempts fail
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                # Increased timeout from 10s to 30s for better reliability
                response = requests.post(
                    MORPHO_API_URL,
                    json={"query": query, "variables": variables or {}},
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    logger.error(f"Morpho API errors: {data['errors']}")
                    raise Exception(f"Morpho API errors: {data['errors']}")

                # Success - return data
                if attempt > 0:
                    logger.info(f"✅ Morpho API succeeded on attempt {attempt + 1}")
                return data.get("data", {})

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(
                        f"⚠️  Morpho API attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    import time
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Morpho API failed after {max_retries} attempts: {e}")

            except Exception as e:
                # Non-retryable error
                logger.error(f"Failed to query Morpho API: {e}")
                raise

        # All retries exhausted
        raise Exception(f"Morpho API failed after {max_retries} attempts: {last_error}")

    async def get_pools(self) -> List[ProtocolPool]:
        """Fetch all available lending markets from Morpho on Base mainnet.

        Phase 3 Sprint 2: Queries REAL data from Morpho Blue GraphQL API.
        Falls back to mock data if API fails or if use_mock_data=True.

        Returns:
            List of Morpho lending markets
        """
        # Log pool query
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {
                "protocol": "Morpho",
                "network": "base-mainnet",
                "action": "get_pools",
                "data_source": "mock" if self.use_mock_data else "real_api",
            },
        )

        # Use mock data if requested
        if self.use_mock_data:
            logger.info("Using mock data (use_mock_data=True)")
            return self._get_mock_pools()

        # Query real Morpho Blue markets from API
        try:
            return await self._get_real_pools_from_api()
        except Exception as e:
            logger.error(f"Failed to fetch real Morpho data, falling back to mock: {e}")
            return self._get_mock_pools()

    async def _get_real_pools_from_api(self) -> List[ProtocolPool]:
        """Fetch real Morpho Blue markets from GraphQL API.

        Returns:
            List of Morpho lending markets from Base mainnet
        """
        # GraphQL query for Base markets (limit to max_markets)
        query = f"""
        query GetBaseMarkets {{
            markets(
                first: {self.max_markets}
                orderBy: SupplyAssetsUsd
                orderDirection: Desc
                where: {{ chainId_in: [8453] }}
            ) {{
                items {{
                    uniqueKey
                    loanAsset {{
                        address
                        symbol
                        decimals
                    }}
                    collateralAsset {{
                        address
                        symbol
                        decimals
                    }}
                    lltv
                    irmAddress
                    oracleAddress
                    state {{
                        borrowAssets
                        supplyAssets
                        borrowShares
                        supplyShares
                        fee
                        utilization
                        supplyApy
                        borrowApy
                    }}
                }}
            }}
        }}
        """

        logger.info(f"Querying top {self.max_markets} Morpho Blue markets from GraphQL API...")
        data = self._query_morpho_api(query)

        markets_data = data.get("markets", {}).get("items", [])
        logger.info(f"Found {len(markets_data)} Morpho markets on Base mainnet")

        pools = []

        for market in markets_data:
            try:
                loan_asset = market.get("loanAsset", {})
                collateral_asset = market.get("collateralAsset", {})
                state = market.get("state", {})

                token_symbol = loan_asset.get("symbol", "UNKNOWN")
                collateral_symbol = collateral_asset.get("symbol", "UNKNOWN")

                # Filter: Skip markets with unsupported loan assets (no Chainlink feed)
                if token_symbol not in self.supported_tokens:
                    logger.debug(
                        f"Skipping Morpho {token_symbol}/{collateral_symbol} market "
                        f"(token not in supported list)"
                    )
                    continue

                # Get APY from API (already in percentage)
                supply_apy = Decimal(str(state.get("supplyApy", 0)))
                borrow_apy = Decimal(str(state.get("borrowApy", 0)))

                # Calculate TVL from supply assets
                supply_assets = Decimal(str(state.get("supplyAssets", 0)))
                decimals = int(loan_asset.get("decimals", 18))
                tvl_tokens = supply_assets / Decimal(10**decimals)

                # Get USD price for TVL
                token_price_usd = await self.price_oracle.get_price(token_symbol)
                tvl_usd = tvl_tokens * token_price_usd

                # Get utilization
                utilization = Decimal(str(state.get("utilization", 0)))

                # Create pool
                pool_id = f"morpho-{token_symbol.lower()}-{collateral_symbol.lower()}"
                pool = ProtocolPool(
                    pool_id=pool_id,
                    name=f"{token_symbol} Lending (Collateral: {collateral_symbol})",
                    tokens=[token_symbol],
                    apy=supply_apy,
                    tvl=tvl_usd,
                    metadata={
                        "market_id": market.get("uniqueKey", ""),
                        "loan_asset": loan_asset.get("address", ""),
                        "collateral_asset": collateral_asset.get("address", ""),
                        "borrow_apy": borrow_apy,
                        "utilization": utilization,
                        "lltv": market.get("lltv", 0),
                        "oracle": market.get("oracleAddress", ""),
                        "irm": market.get("irmAddress", ""),
                        "protocol_version": "blue",
                        "risk_tier": "low" if utilization < Decimal("0.8") else "medium",
                    },
                )

                pools.append(pool)
                logger.info(
                    f"Morpho {token_symbol}/{collateral_symbol}: {supply_apy:.2f}% APY, "
                    f"${tvl_usd:,.0f} TVL"
                )

            except Exception as e:
                logger.warning(f"Failed to parse Morpho market: {e}")
                continue

        logger.info(f"Successfully fetched {len(pools)} Morpho markets from Base mainnet")
        return pools

    def _get_mock_pools(self) -> List[ProtocolPool]:
        """Generate realistic mock lending markets.

        Based on typical Morpho Blue market characteristics:
        - Supply APYs: 2-8% for stablecoins, 1-5% for ETH
        - TVL: $100k - $10M per market
        - Utilization: 60-85% typical

        Returns:
            List of mock Morpho lending markets
        """
        mock_pools = [
            ProtocolPool(
                pool_id="morpho-usdc-market-1",
                name="USDC Lending Market",
                tokens=["USDC"],
                apy=Decimal("4.5"),
                tvl=Decimal("1200000"),  # $1.2M TVL
                metadata={
                    "contract_address": self.contracts.get("morpho_chainlink_oracle_v2", ""),
                    "borrow_apy": Decimal("6.2"),
                    "utilization": Decimal("0.75"),
                    "collateral_factor": Decimal("0.80"),
                    "total_supply": Decimal("1200000"),
                    "total_borrow": Decimal("900000"),
                    "oracle_type": "Chainlink",
                    "risk_tier": "low",
                },
            ),
            ProtocolPool(
                pool_id="morpho-weth-market-1",
                name="WETH Lending Market",
                tokens=["WETH"],
                apy=Decimal("3.2"),
                tvl=Decimal("2500000"),  # $2.5M TVL
                metadata={
                    "contract_address": self.contracts.get("morpho_chainlink_oracle_v2", ""),
                    "borrow_apy": Decimal("4.8"),
                    "utilization": Decimal("0.68"),
                    "collateral_factor": Decimal("0.75"),
                    "total_supply": Decimal("2500000"),
                    "total_borrow": Decimal("1700000"),
                    "oracle_type": "Chainlink",
                    "risk_tier": "low",
                },
            ),
            ProtocolPool(
                pool_id="morpho-dai-market-1",
                name="DAI Lending Market",
                tokens=["DAI"],
                apy=Decimal("5.1"),
                tvl=Decimal("800000"),  # $800k TVL
                metadata={
                    "contract_address": self.contracts.get("morpho_chainlink_oracle_v2", ""),
                    "borrow_apy": Decimal("7.3"),
                    "utilization": Decimal("0.82"),
                    "collateral_factor": Decimal("0.80"),
                    "total_supply": Decimal("800000"),
                    "total_borrow": Decimal("656000"),
                    "oracle_type": "Chainlink",
                    "risk_tier": "low",
                },
            ),
            ProtocolPool(
                pool_id="morpho-usdc-high-yield",
                name="USDC High Yield Market",
                tokens=["USDC"],
                apy=Decimal("7.8"),
                tvl=Decimal("350000"),  # $350k TVL (smaller, higher yield)
                metadata={
                    "contract_address": self.contracts.get("morpho_chainlink_oracle_v2", ""),
                    "borrow_apy": Decimal("11.5"),
                    "utilization": Decimal("0.89"),
                    "collateral_factor": Decimal("0.70"),
                    "total_supply": Decimal("350000"),
                    "total_borrow": Decimal("311500"),
                    "oracle_type": "Chainlink",
                    "risk_tier": "medium",
                },
            ),
        ]

        logger.info(f"Generated {len(mock_pools)} mock Morpho lending markets")
        return mock_pools

    async def get_pool_apy(self, pool_id: str) -> Decimal:
        """Get current supply APY for a Morpho market.

        Args:
            pool_id: Market identifier

        Returns:
            Current supply APY as Decimal
        """
        # Log APY query
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {"protocol": "Morpho", "pool_id": pool_id, "action": "get_pool_apy"},
        )

        # Get all pools and find the requested one
        pools = await self.get_pools()
        for pool in pools:
            if pool.pool_id == pool_id:
                logger.info(f"Morpho market {pool_id}: {pool.apy}% APY")
                return pool.apy

        logger.warning(f"Morpho market {pool_id} not found")
        return Decimal("0")

    async def deposit(
        self,
        pool_id: str,
        token: str,
        amount: Decimal,
    ) -> str:
        """Supply tokens to a Morpho lending market.

        Phase 3 Sprint 1: Read-only mode - builds transaction without executing.

        Args:
            pool_id: Target market identifier
            token: Token to supply
            amount: Amount to supply

        Returns:
            Transaction data (dict as string) in read-only mode
            Transaction hash when execution is implemented

        Raises:
            NotImplementedError: If called in non-read-only mode
        """
        if self.read_only:
            logger.info(
                f"🔒 Read-only mode: Building deposit tx for {amount} {token} "
                f"to Morpho market {pool_id} (not executing)"
            )

            # Log the deposit intent
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_INITIATED,
                AuditSeverity.INFO,
                {
                    "protocol": "Morpho",
                    "operation": "deposit",
                    "pool_id": pool_id,
                    "token": token,
                    "amount": str(amount),
                    "read_only": True,
                },
            )

            # Return mock transaction data
            return str({
                "to": self.contracts.get("morpho_chainlink_oracle_v2", ""),
                "data": "0x...",  # Mock transaction data
                "value": 0,
                "operation": "deposit",
                "pool_id": pool_id,
                "token": token,
                "amount": str(amount),
            })

        raise NotImplementedError(
            "Morpho deposit execution not yet implemented (Sprint 3-4)"
        )

    async def withdraw(
        self,
        pool_id: str,
        token: str,
        amount: Decimal,
    ) -> str:
        """Withdraw tokens from a Morpho lending market.

        Phase 3 Sprint 1: Read-only mode - builds transaction without executing.

        Args:
            pool_id: Source market identifier
            token: Token to withdraw
            amount: Amount to withdraw

        Returns:
            Transaction data (dict as string) in read-only mode
            Transaction hash when execution is implemented

        Raises:
            NotImplementedError: If called in non-read-only mode
        """
        if self.read_only:
            logger.info(
                f"🔒 Read-only mode: Building withdraw tx for {amount} {token} "
                f"from Morpho market {pool_id} (not executing)"
            )

            # Log the withdrawal intent
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_INITIATED,
                AuditSeverity.INFO,
                {
                    "protocol": "Morpho",
                    "operation": "withdraw",
                    "pool_id": pool_id,
                    "token": token,
                    "amount": str(amount),
                    "read_only": True,
                },
            )

            # Return mock transaction data
            return str({
                "to": self.contracts.get("morpho_chainlink_oracle_v2", ""),
                "data": "0x...",  # Mock transaction data
                "value": 0,
                "operation": "withdraw",
                "pool_id": pool_id,
                "token": token,
                "amount": str(amount),
            })

        raise NotImplementedError(
            "Morpho withdraw execution not yet implemented (Sprint 3-4)"
        )

    async def get_user_balance(self, pool_id: str, user_address: str) -> Decimal:
        """Get user's supplied balance in a Morpho market.

        Args:
            pool_id: Market identifier
            user_address: User's wallet address

        Returns:
            User's supplied balance in the market
        """
        # Log balance query
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {
                "protocol": "Morpho",
                "pool_id": pool_id,
                "user_address": user_address,
                "action": "get_user_balance",
            },
        )

        # Phase 3 Sprint 1: Return mock balance
        if self.use_mock_data:
            logger.info(f"Mock balance query for {user_address} in {pool_id}")
            return Decimal("0")  # No positions yet in development

        # Future: Query real balance from contract
        raise NotImplementedError("Morpho balance queries not yet implemented")

    async def estimate_gas(self, operation: str, params: Dict[str, Any]) -> int:
        """Estimate gas for Morpho operations.

        Args:
            operation: Operation type ('deposit', 'withdraw')
            params: Operation parameters

        Returns:
            Estimated gas units
        """
        # Log gas estimation
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {
                "protocol": "Morpho",
                "operation": operation,
                "action": "estimate_gas",
            },
        )

        # Phase 3 Sprint 1: Return realistic gas estimates
        # Based on typical Morpho Blue transaction costs
        gas_estimates = {
            "deposit": 150000,  # ~150k gas for supply
            "withdraw": 120000,  # ~120k gas for withdraw
            "borrow": 180000,   # ~180k gas for borrow
            "repay": 130000,    # ~130k gas for repay
        }

        estimated_gas = gas_estimates.get(operation, 200000)
        logger.info(f"Estimated {estimated_gas} gas for Morpho {operation}")
        return estimated_gas

    @property
    def safety_score(self) -> int:
        """Calculate protocol safety score.

        Based on:
        - Audit status (Morpho is well-audited)
        - TVL (Morpho has significant TVL)
        - Age (Morpho launched 2021, mature)
        - Coinbase promotion (additional credibility)

        Returns:
            Safety score 0-100 (Morpho scores high: 90)
        """
        score = 100

        # Morpho is well-audited by multiple firms
        # No deduction for audits

        # Morpho has significant TVL ($100M+)
        # No deduction for TVL

        # Morpho is mature (3+ years)
        # No deduction for age

        # Morpho is Coinbase-promoted
        # Bonus for institutional backing (already at 100)

        # Final score: 90 (very safe, but not perfect like native protocols)
        return 90

    def __repr__(self) -> str:
        """String representation of MorphoProtocol.

        Returns:
            Protocol details string
        """
        data_source = "mock" if self.use_mock_data else "base-mainnet-api"
        return (
            f"MorphoProtocol(network={self.network}, "
            f"read_only={self.read_only}, "
            f"data_source={data_source}, "
            f"safety_score={self.safety_score})"
        )
