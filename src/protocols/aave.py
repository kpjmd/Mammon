"""Aave V3 protocol integration.

Aave is the leading decentralized lending protocol with battle-tested security.
https://aave.com/

Phase 3 Sprint 2: Read-only implementation with REAL BASE MAINNET data.
"""

from typing import Any, Dict, List, Optional
from decimal import Decimal
from src.utils.logger import get_logger
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings
from src.data.oracles import create_price_oracle
from .base import BaseProtocol, ProtocolPool

logger = get_logger(__name__)

# Aave V3 contract addresses on Base
AAVE_V3_CONTRACTS = {
    "base-mainnet": {
        "pool": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
        "pool_data_provider": "0x2d8A3C5677189723C4cB8873CfC9C8976FDF38Ac",
        "oracle": "0x2Cc0Fc26eD4563A5ce5e8bdcfe1A2878676Ae156",
        "ui_pool_data_provider": "0x174446a6741300cD2E7C1b1A636Fee99c8F83502",
    },
    "base-sepolia": {
        # For testnet transactions (read data from mainnet)
        "pool": "0xTBD_SEPOLIA_POOL",
    },
}

# Minimal ABIs for reading Aave V3 data
AAVE_POOL_ABI = [
    {
        "inputs": [],
        "name": "getReservesList",
        "outputs": [{"internalType": "address[]", "name": "", "type": "address[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "asset", "type": "address"}],
        "name": "getReserveData",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "configuration", "type": "uint256"},
                    {"internalType": "uint128", "name": "liquidityIndex", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentLiquidityRate", "type": "uint128"},
                    {"internalType": "uint128", "name": "variableBorrowIndex", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentVariableBorrowRate", "type": "uint128"},
                    {"internalType": "uint128", "name": "currentStableBorrowRate", "type": "uint128"},
                    {"internalType": "uint40", "name": "lastUpdateTimestamp", "type": "uint40"},
                    {"internalType": "uint16", "name": "id", "type": "uint16"},
                    {"internalType": "address", "name": "aTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "stableDebtTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "variableDebtTokenAddress", "type": "address"},
                    {"internalType": "address", "name": "interestRateStrategyAddress", "type": "address"},
                    {"internalType": "uint128", "name": "accruedToTreasury", "type": "uint128"},
                    {"internalType": "uint128", "name": "unbacked", "type": "uint128"},
                    {"internalType": "uint128", "name": "isolationModeTotalDebt", "type": "uint128"},
                ],
                "internalType": "struct DataTypes.ReserveData",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

# ERC20 ABI for getting token symbols and decimals
ERC20_ABI = [
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class AaveV3Protocol(BaseProtocol):
    """Aave V3 lending protocol integration.

    Provides access to Aave's decentralized lending markets on Base.

    Phase 3 Sprint 2: Read-only mode with REAL BASE MAINNET data queries.
    Future sprints will add transaction execution.

    Attributes:
        network: Network identifier (base-mainnet or base-sepolia)
        read_only: If True, prevents any write operations (safety)
        audit_logger: Audit logging instance
        price_oracle: Price oracle for TVL calculations
        web3: Web3 instance for blockchain queries
        pool_contract: Aave Pool contract instance
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize Aave V3 protocol integration.

        Args:
            config: Configuration including network and safety settings
        """
        super().__init__("Aave V3", "base", config)
        self.network = config.get("network", "base-sepolia")
        self.read_only = config.get("read_only", True)
        self.audit_logger = AuditLogger()

        # Get contract addresses for this network
        self.contracts = AAVE_V3_CONTRACTS.get("base-mainnet", {})  # Always read from mainnet

        # Initialize Web3 for BASE MAINNET queries with premium RPC support
        settings = get_settings()
        self.web3 = get_web3("base-mainnet", config=settings)
        self.pool_contract = self.web3.eth.contract(
            address=self.contracts["pool"],
            abi=AAVE_POOL_ABI,
        )

        # Initialize price oracle for TVL calculations
        self._init_price_oracle(config)

        if self.read_only:
            logger.info("🔒 AaveV3Protocol initialized in READ-ONLY mode")
        logger.info(f"📊 AaveV3Protocol querying REAL data from Base mainnet")

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

    def _ray_to_apy(self, rate: int) -> Decimal:
        """Convert Aave ray-based rate to APY percentage.

        Aave stores rates in "ray" units (1e27). The currentLiquidityRate
        and currentVariableBorrowRate are already ANNUAL rates, not per-second.

        Formula: APY = rate / RAY * 100

        Args:
            rate: Annual rate in ray units (1e27)

        Returns:
            APY as percentage (e.g., 5.2 for 5.2%)
        """
        RAY = Decimal(10**27)

        if rate == 0:
            return Decimal(0)

        # Convert ray to decimal (rate is already annual)
        rate_decimal = Decimal(rate) / RAY

        # Convert to percentage
        apy_percentage = rate_decimal * Decimal(100)

        return apy_percentage

    async def get_pools(self) -> List[ProtocolPool]:
        """Fetch all available lending markets from Aave V3 on Base mainnet.

        Queries the real Aave V3 Pool contract to get reserve data.

        Returns:
            List of Aave lending markets
        """
        # Log pool query
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {
                "protocol": "Aave V3",
                "network": "base-mainnet",
                "action": "get_pools",
                "data_source": "real_mainnet",
            },
        )

        try:
            # Get list of all reserves (assets) from Aave
            reserve_addresses = self.pool_contract.functions.getReservesList().call()
            logger.info(f"Found {len(reserve_addresses)} Aave V3 reserves on Base mainnet")

            pools = []

            for asset_address in reserve_addresses:
                try:
                    # Get reserve data
                    reserve_data = self.pool_contract.functions.getReserveData(asset_address).call()

                    # Get token info
                    token_contract = self.web3.eth.contract(
                        address=asset_address,
                        abi=ERC20_ABI,
                    )
                    token_symbol = token_contract.functions.symbol().call()
                    decimals = token_contract.functions.decimals().call()

                    # Get aToken (interest-bearing token) info for TVL
                    atoken_address = reserve_data[8]  # aTokenAddress
                    atoken_contract = self.web3.eth.contract(
                        address=atoken_address,
                        abi=ERC20_ABI,
                    )
                    total_supply = atoken_contract.functions.totalSupply().call()

                    # Convert to human-readable amount
                    tvl_tokens = Decimal(total_supply) / Decimal(10**decimals)

                    # Get USD price for TVL
                    token_price_usd = await self.price_oracle.get_price(token_symbol)
                    tvl_usd = tvl_tokens * token_price_usd

                    # Extract rates from reserve data
                    current_liquidity_rate = reserve_data[2]  # Supply APY in ray
                    current_variable_borrow_rate = reserve_data[4]  # Borrow APY in ray

                    # Convert to APY percentages
                    supply_apy = self._ray_to_apy(current_liquidity_rate)
                    borrow_apy = self._ray_to_apy(current_variable_borrow_rate)

                    # Calculate utilization
                    # Note: This is simplified - real calculation needs total borrows
                    utilization = Decimal(0.70)  # Placeholder, needs debt token query

                    # Create pool
                    pool = ProtocolPool(
                        pool_id=f"aave-v3-{token_symbol.lower()}",
                        name=f"{token_symbol} Lending",
                        tokens=[token_symbol],
                        apy=supply_apy,
                        tvl=tvl_usd,
                        metadata={
                            "contract_address": asset_address,
                            "atoken_address": atoken_address,
                            "borrow_apy": borrow_apy,
                            "utilization": utilization,
                            "liquidity_rate": current_liquidity_rate,
                            "variable_borrow_rate": current_variable_borrow_rate,
                            "protocol_version": "v3",
                            "risk_tier": "low",  # Aave is very safe
                        },
                    )

                    pools.append(pool)
                    logger.info(
                        f"Aave V3 {token_symbol}: {supply_apy:.2f}% APY, "
                        f"${tvl_usd:,.0f} TVL"
                    )

                except Exception as e:
                    logger.warning(f"Failed to fetch data for Aave reserve {asset_address}: {e}")
                    continue

            logger.info(f"Successfully fetched {len(pools)} Aave V3 markets from Base mainnet")
            return pools

        except Exception as e:
            logger.error(f"Failed to fetch Aave V3 pools from Base mainnet: {e}")
            return []

    async def get_pool_apy(self, pool_id: str) -> Decimal:
        """Get current supply APY for an Aave market.

        Args:
            pool_id: Market identifier

        Returns:
            Current supply APY as Decimal
        """
        # Log APY query
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {"protocol": "Aave V3", "pool_id": pool_id, "action": "get_pool_apy"},
        )

        # Get all pools and find the requested one
        pools = await self.get_pools()
        for pool in pools:
            if pool.pool_id == pool_id:
                logger.info(f"Aave V3 market {pool_id}: {pool.apy}% APY")
                return pool.apy

        logger.warning(f"Aave V3 market {pool_id} not found")
        return Decimal("0")

    async def deposit(
        self,
        pool_id: str,
        token: str,
        amount: Decimal,
    ) -> str:
        """Supply tokens to an Aave V3 lending market.

        Phase 3 Sprint 2: Read-only mode - builds transaction without executing.

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
                f"to Aave V3 market {pool_id} (not executing)"
            )

            # Log the deposit intent
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_INITIATED,
                AuditSeverity.INFO,
                {
                    "protocol": "Aave V3",
                    "operation": "deposit",
                    "pool_id": pool_id,
                    "token": token,
                    "amount": str(amount),
                    "read_only": True,
                },
            )

            # Return mock transaction data
            return str({
                "to": self.contracts.get("pool", ""),
                "data": "0x...",  # Mock transaction data
                "value": 0,
                "operation": "supply",
                "pool_id": pool_id,
                "token": token,
                "amount": str(amount),
            })

        raise NotImplementedError(
            "Aave V3 deposit execution not yet implemented (Sprint 3-4)"
        )

    async def withdraw(
        self,
        pool_id: str,
        token: str,
        amount: Decimal,
    ) -> str:
        """Withdraw tokens from an Aave V3 lending market.

        Phase 3 Sprint 2: Read-only mode - builds transaction without executing.

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
                f"from Aave V3 market {pool_id} (not executing)"
            )

            # Log the withdrawal intent
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_INITIATED,
                AuditSeverity.INFO,
                {
                    "protocol": "Aave V3",
                    "operation": "withdraw",
                    "pool_id": pool_id,
                    "token": token,
                    "amount": str(amount),
                    "read_only": True,
                },
            )

            # Return mock transaction data
            return str({
                "to": self.contracts.get("pool", ""),
                "data": "0x...",  # Mock transaction data
                "value": 0,
                "operation": "withdraw",
                "pool_id": pool_id,
                "token": token,
                "amount": str(amount),
            })

        raise NotImplementedError(
            "Aave V3 withdraw execution not yet implemented (Sprint 3-4)"
        )

    async def get_user_balance(self, pool_id: str, user_address: str) -> Decimal:
        """Get user's supplied balance in an Aave market.

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
                "protocol": "Aave V3",
                "pool_id": pool_id,
                "user_address": user_address,
                "action": "get_user_balance",
            },
        )

        try:
            # Extract token symbol from pool_id (e.g., 'aave-v3-usdc' -> 'USDC')
            token_symbol = pool_id.replace("aave-v3-", "").upper()

            # Get list of all reserves to find the matching token
            reserve_addresses = self.pool_contract.functions.getReservesList().call()

            for asset_address in reserve_addresses:
                # Check if this is the token we're looking for
                token_contract = self.web3.eth.contract(
                    address=asset_address,
                    abi=ERC20_ABI,
                )
                symbol = token_contract.functions.symbol().call()

                if symbol.upper() == token_symbol:
                    # Found the matching reserve - get aToken address
                    reserve_data = self.pool_contract.functions.getReserveData(asset_address).call()
                    atoken_address = reserve_data[8]  # aTokenAddress
                    decimals = token_contract.functions.decimals().call()

                    # Query user's aToken balance
                    atoken_contract = self.web3.eth.contract(
                        address=atoken_address,
                        abi=ERC20_ABI,
                    )
                    balance_wei = atoken_contract.functions.balanceOf(user_address).call()

                    # Convert to human-readable amount
                    balance = Decimal(balance_wei) / Decimal(10**decimals)

                    logger.info(
                        f"User {user_address[:8]}... has {balance} {token_symbol} in Aave V3"
                    )
                    return balance

            # Token not found in Aave V3
            logger.warning(f"Token {token_symbol} not found in Aave V3 reserves")
            return Decimal("0")

        except Exception as e:
            logger.error(f"Failed to get user balance for {pool_id}: {e}")
            return Decimal("0")

    async def estimate_gas(self, operation: str, params: Dict[str, Any]) -> int:
        """Estimate gas for Aave V3 operations.

        Args:
            operation: Operation type ('deposit', 'withdraw', 'borrow', 'repay')
            params: Operation parameters

        Returns:
            Estimated gas units
        """
        # Log gas estimation
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {
                "protocol": "Aave V3",
                "operation": operation,
                "action": "estimate_gas",
            },
        )

        # Based on typical Aave V3 transaction costs on Base
        gas_estimates = {
            "deposit": 200000,  # ~200k gas for supply
            "withdraw": 180000,  # ~180k gas for withdraw
            "borrow": 250000,   # ~250k gas for borrow
            "repay": 200000,    # ~200k gas for repay
        }

        estimated_gas = gas_estimates.get(operation, 250000)
        logger.info(f"Estimated {estimated_gas} gas for Aave V3 {operation}")
        return estimated_gas

    @property
    def safety_score(self) -> int:
        """Calculate protocol safety score.

        Based on:
        - Audit status (Aave is extensively audited)
        - TVL (Aave has $10B+ TVL across chains)
        - Age (Aave launched 2017, very mature)
        - Battle-tested (survived multiple market crashes)

        Returns:
            Safety score 0-100 (Aave scores very high: 95)
        """
        # Aave is one of the safest DeFi protocols
        return 95

    def __repr__(self) -> str:
        """String representation of AaveV3Protocol.

        Returns:
            Protocol details string
        """
        return (
            f"AaveV3Protocol(network={self.network}, "
            f"read_only={self.read_only}, "
            f"data_source=base-mainnet, "
            f"safety_score={self.safety_score})"
        )
