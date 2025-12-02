"""Moonwell protocol integration.

Moonwell is a Compound V2-style lending protocol on Base, Moonbeam, and Moonriver.
https://moonwell.fi/

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

# Moonwell contract addresses on Base
MOONWELL_CONTRACTS = {
    "base-mainnet": {
        "comptroller": "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C",
        # Individual mToken markets will be discovered via getAllMarkets()
    },
    "base-sepolia": {
        # For testnet transactions (read data from mainnet)
        "comptroller": "0xTBD_SEPOLIA_COMPTROLLER",
    },
}

# Minimal ABIs for reading Moonwell (Compound V2 fork) data
COMPTROLLER_ABI = [
    {
        "inputs": [],
        "name": "getAllMarkets",
        "outputs": [{"internalType": "contract MToken[]", "name": "", "type": "address[]"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# mToken (Compound cToken equivalent) ABI
# Note: Moonwell on Base uses timestamp-based rates, not block-based
MTOKEN_ABI = [
    {
        "inputs": [],
        "name": "underlying",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "supplyRatePerTimestamp",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "borrowRatePerTimestamp",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getCash",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalBorrows",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalReserves",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "balanceOfUnderlying",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "exchangeRateStored",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
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
]


class MoonwellProtocol(BaseProtocol):
    """Moonwell lending protocol integration.

    Provides access to Moonwell's Compound-style lending markets on Base.

    Phase 3 Sprint 2: Read-only mode with REAL BASE MAINNET data queries.
    Future sprints will add transaction execution.

    Attributes:
        network: Network identifier (base-mainnet or base-sepolia)
        read_only: If True, prevents any write operations (safety)
        audit_logger: Audit logging instance
        price_oracle: Price oracle for TVL calculations
        web3: Web3 instance for blockchain queries
        comptroller_contract: Moonwell Comptroller contract instance
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize Moonwell protocol integration.

        Args:
            config: Configuration including network and safety settings
        """
        super().__init__("Moonwell", "base", config)
        self.network = config.get("network", "base-sepolia")
        self.read_only = config.get("read_only", True)
        self.audit_logger = AuditLogger()

        # Get contract addresses for this network
        self.contracts = MOONWELL_CONTRACTS.get("base-mainnet", {})  # Always read from mainnet

        # Initialize Web3 for BASE MAINNET queries with premium RPC support
        settings = get_settings()
        self.web3 = get_web3("base-mainnet", config=settings)
        self.comptroller_contract = self.web3.eth.contract(
            address=self.contracts["comptroller"],
            abi=COMPTROLLER_ABI,
        )

        # Initialize price oracle for TVL calculations
        self._init_price_oracle(config)

        if self.read_only:
            logger.info("🔒 MoonwellProtocol initialized in READ-ONLY mode")
        logger.info(f"📊 MoonwellProtocol querying REAL data from Base mainnet")

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

    def _rate_per_timestamp_to_apy(self, rate_per_timestamp: int) -> Decimal:
        """Convert Moonwell rate per timestamp to APY percentage.

        Moonwell on Base uses timestamp-based interest accrual.
        Rate is per-second, scaled by 1e18.

        Formula: APY = rate_per_second * seconds_per_year * 100

        Args:
            rate_per_timestamp: Rate per second (scaled by 1e18)

        Returns:
            APY as percentage (e.g., 5.2 for 5.2%)
        """
        SECONDS_PER_YEAR = Decimal(31536000)  # 365 * 24 * 60 * 60
        RATE_SCALE = Decimal(10**18)

        if rate_per_timestamp == 0:
            return Decimal(0)

        # Convert to decimal
        rate_decimal = Decimal(rate_per_timestamp) / RATE_SCALE

        # Linear approximation: APY ≈ rate_per_second * seconds_per_year
        apy_decimal = rate_decimal * SECONDS_PER_YEAR

        # Convert to percentage
        apy_percentage = apy_decimal * Decimal(100)

        return apy_percentage

    async def get_pools(self) -> List[ProtocolPool]:
        """Fetch all available lending markets from Moonwell on Base mainnet.

        Queries the real Moonwell Comptroller to get all mToken markets.

        Returns:
            List of Moonwell lending markets
        """
        logger.info(f"📡 [MOONWELL] Fetching pools from Base mainnet...")

        # Log pool query
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {
                "protocol": "Moonwell",
                "network": "base-mainnet",
                "action": "get_pools",
                "data_source": "real_mainnet",
            },
        )

        try:
            # Get list of all mToken markets from Comptroller
            mtoken_addresses = self.comptroller_contract.functions.getAllMarkets().call()
            logger.info(f"[MOONWELL] Found {len(mtoken_addresses)} markets on Base mainnet")

            pools = []

            for mtoken_address in mtoken_addresses:
                try:
                    logger.info(f"[MOONWELL] Processing market: {mtoken_address}")

                    # Create mToken contract instance
                    mtoken_contract = self.web3.eth.contract(
                        address=mtoken_address,
                        abi=MTOKEN_ABI,
                    )

                    # Get underlying asset address (fails for native ETH markets)
                    try:
                        underlying_address = mtoken_contract.functions.underlying().call()

                        # Get underlying token info
                        token_contract = self.web3.eth.contract(
                            address=underlying_address,
                            abi=ERC20_ABI,
                        )
                        token_symbol = token_contract.functions.symbol().call()
                        decimals = token_contract.functions.decimals().call()
                    except Exception:
                        # Native ETH market (no underlying() function)
                        token_symbol = "ETH"
                        decimals = 18
                        underlying_address = "0x0000000000000000000000000000000000000000"

                    logger.info(f"[MOONWELL] Token identified: {token_symbol} (decimals={decimals})")

                    # Get market data (using timestamp-based rates on Base)
                    supply_rate = mtoken_contract.functions.supplyRatePerTimestamp().call()
                    borrow_rate = mtoken_contract.functions.borrowRatePerTimestamp().call()
                    cash = mtoken_contract.functions.getCash().call()
                    total_borrows = mtoken_contract.functions.totalBorrows().call()
                    total_reserves = mtoken_contract.functions.totalReserves().call()

                    # Convert to APY percentages
                    supply_apy = self._rate_per_timestamp_to_apy(supply_rate)
                    borrow_apy = self._rate_per_timestamp_to_apy(borrow_rate)

                    # Calculate TVL in tokens
                    tvl_tokens = Decimal(cash + total_borrows - total_reserves) / Decimal(10**decimals)
                    logger.info(f"[MOONWELL] {token_symbol} TVL: {tvl_tokens} tokens")

                    # Get USD price for TVL with fallback
                    try:
                        token_price_usd = await self.price_oracle.get_price(token_symbol)
                        logger.info(f"[MOONWELL] {token_symbol} price from oracle: ${token_price_usd}")
                    except Exception as e:
                        logger.warning(
                            f"[MOONWELL] Price oracle failed for {token_symbol}: {e}, using $1 fallback"
                        )
                        # Fallback to $1 for stablecoins, skip others
                        stablecoins = ["USDC", "USDT", "DAI", "USDBC", "USDbC"]
                        if token_symbol.upper() in stablecoins:
                            token_price_usd = Decimal("1")
                        else:
                            # Skip non-stablecoins without prices
                            logger.warning(f"[MOONWELL] Skipping {token_symbol} (no price available)")
                            continue

                    tvl_usd = tvl_tokens * token_price_usd

                    # Calculate utilization
                    total_supply = cash + total_borrows - total_reserves
                    utilization = Decimal(total_borrows) / Decimal(total_supply) if total_supply > 0 else Decimal(0)

                    # Create pool
                    pool = ProtocolPool(
                        pool_id=f"moonwell-{token_symbol.lower()}",
                        name=f"{token_symbol} Lending",
                        tokens=[token_symbol],
                        apy=supply_apy,
                        tvl=tvl_usd,
                        metadata={
                            "mtoken_address": mtoken_address,
                            "underlying_address": underlying_address,
                            "borrow_apy": borrow_apy,
                            "utilization": utilization,
                            "supply_rate_per_timestamp": supply_rate,
                            "borrow_rate_per_timestamp": borrow_rate,
                            "cash": cash,
                            "total_borrows": total_borrows,
                            "protocol_version": "compound-v2-fork-timestamp",
                            "risk_tier": "medium",  # Moonwell is well-audited but newer
                        },
                    )

                    pools.append(pool)
                    logger.info(
                        f"✅ [MOONWELL] {token_symbol}: {supply_apy:.2f}% APY, "
                        f"${tvl_usd:,.0f} TVL, pool added successfully"
                    )

                except Exception as e:
                    logger.warning(f"Failed to fetch data for Moonwell market {mtoken_address}: {e}")
                    continue

            logger.info(f"Successfully fetched {len(pools)} Moonwell markets from Base mainnet")
            return pools

        except Exception as e:
            logger.error(f"Failed to fetch Moonwell pools from Base mainnet: {e}")
            return []

    async def get_pool_apy(self, pool_id: str) -> Decimal:
        """Get current supply APY for a Moonwell market.

        Args:
            pool_id: Market identifier

        Returns:
            Current supply APY as Decimal
        """
        # Log APY query
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {"protocol": "Moonwell", "pool_id": pool_id, "action": "get_pool_apy"},
        )

        # Get all pools and find the requested one
        pools = await self.get_pools()
        for pool in pools:
            if pool.pool_id == pool_id:
                logger.info(f"Moonwell market {pool_id}: {pool.apy}% APY")
                return pool.apy

        logger.warning(f"Moonwell market {pool_id} not found")
        return Decimal("0")

    async def deposit(
        self,
        pool_id: str,
        token: str,
        amount: Decimal,
    ) -> str:
        """Supply tokens to a Moonwell lending market.

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
                f"to Moonwell market {pool_id} (not executing)"
            )

            # Log the deposit intent
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_INITIATED,
                AuditSeverity.INFO,
                {
                    "protocol": "Moonwell",
                    "operation": "deposit",
                    "pool_id": pool_id,
                    "token": token,
                    "amount": str(amount),
                    "read_only": True,
                },
            )

            # Return mock transaction data
            return str({
                "to": "mtoken_address",  # Would be actual mToken address
                "data": "0x...",  # Mock transaction data
                "value": 0,
                "operation": "mint",
                "pool_id": pool_id,
                "token": token,
                "amount": str(amount),
            })

        raise NotImplementedError(
            "Moonwell deposit execution not yet implemented (Sprint 3-4)"
        )

    async def withdraw(
        self,
        pool_id: str,
        token: str,
        amount: Decimal,
    ) -> str:
        """Withdraw tokens from a Moonwell lending market.

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
                f"from Moonwell market {pool_id} (not executing)"
            )

            # Log the withdrawal intent
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_INITIATED,
                AuditSeverity.INFO,
                {
                    "protocol": "Moonwell",
                    "operation": "withdraw",
                    "pool_id": pool_id,
                    "token": token,
                    "amount": str(amount),
                    "read_only": True,
                },
            )

            # Return mock transaction data
            return str({
                "to": "mtoken_address",  # Would be actual mToken address
                "data": "0x...",  # Mock transaction data
                "value": 0,
                "operation": "redeem",
                "pool_id": pool_id,
                "token": token,
                "amount": str(amount),
            })

        raise NotImplementedError(
            "Moonwell withdraw execution not yet implemented (Sprint 3-4)"
        )

    async def get_user_balance(self, pool_id: str, user_address: str) -> Decimal:
        """Get user's supplied balance in a Moonwell market.

        Args:
            pool_id: Market identifier (e.g., 'moonwell-usdc')
            user_address: User's wallet address

        Returns:
            User's supplied balance in the market (underlying tokens)
        """
        # Log balance query
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            {
                "protocol": "Moonwell",
                "pool_id": pool_id,
                "user_address": user_address,
                "action": "get_user_balance",
            },
        )

        try:
            # Ensure address is checksummed
            from web3 import Web3
            user_address = Web3.to_checksum_address(user_address)

            # Extract token symbol from pool_id (e.g., 'moonwell-usdc' -> 'USDC')
            token_symbol = pool_id.replace("moonwell-", "").upper()

            # Get list of all mToken markets from Comptroller
            mtoken_addresses = self.comptroller_contract.functions.getAllMarkets().call()

            for mtoken_address in mtoken_addresses:
                try:
                    # Create mToken contract instance
                    mtoken_contract = self.web3.eth.contract(
                        address=mtoken_address,
                        abi=MTOKEN_ABI,
                    )

                    # Get underlying asset info
                    try:
                        underlying_address = mtoken_contract.functions.underlying().call()

                        # Get underlying token symbol
                        token_contract = self.web3.eth.contract(
                            address=underlying_address,
                            abi=ERC20_ABI,
                        )
                        symbol = token_contract.functions.symbol().call()
                        decimals = token_contract.functions.decimals().call()
                    except Exception:
                        # Native ETH market (no underlying() function)
                        symbol = "ETH"
                        decimals = 18

                    # Check if this is the market we're looking for
                    if symbol.upper() == token_symbol:
                        # Query user's mToken balance (fast view function)
                        mtoken_balance = mtoken_contract.functions.balanceOf(user_address).call()

                        # Early exit if no balance
                        if mtoken_balance == 0:
                            return Decimal("0")

                        # Get exchange rate (mToken to underlying, scaled by 1e18)
                        exchange_rate = mtoken_contract.functions.exchangeRateStored().call()

                        # Calculate underlying balance: (mToken_balance * exchangeRate) / 1e18
                        # Both mtoken_balance and exchange_rate are in wei, so we need to account for decimals
                        underlying_balance_wei = (mtoken_balance * exchange_rate) // (10**18)

                        # Convert to human-readable amount
                        balance = Decimal(underlying_balance_wei) / Decimal(10**decimals)

                        logger.info(
                            f"User {user_address[:8]}... has {balance} {token_symbol} in Moonwell"
                        )
                        return balance

                except Exception as e:
                    logger.warning(f"Error checking mToken {mtoken_address}: {e}")
                    continue

            # Token not found in Moonwell markets
            logger.warning(f"Token {token_symbol} not found in Moonwell markets")
            return Decimal("0")

        except Exception as e:
            logger.error(f"Failed to get user balance for {pool_id}: {e}")
            return Decimal("0")

    async def estimate_gas(self, operation: str, params: Dict[str, Any]) -> int:
        """Estimate gas for Moonwell operations.

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
                "protocol": "Moonwell",
                "operation": operation,
                "action": "estimate_gas",
            },
        )

        # Based on typical Compound-style transaction costs
        gas_estimates = {
            "deposit": 180000,  # ~180k gas for mint
            "withdraw": 160000,  # ~160k gas for redeem
            "borrow": 220000,   # ~220k gas for borrow
            "repay": 180000,    # ~180k gas for repay
        }

        estimated_gas = gas_estimates.get(operation, 200000)
        logger.info(f"Estimated {estimated_gas} gas for Moonwell {operation}")
        return estimated_gas

    @property
    def safety_score(self) -> int:
        """Calculate protocol safety score.

        Based on:
        - Audit status (Moonwell is audited by Halborn)
        - TVL (Moonwell has $100M+ TVL across chains)
        - Age (Moonwell launched 2022, relatively mature)
        - Compound V2 fork (proven architecture)

        Returns:
            Safety score 0-100 (Moonwell scores well: 85)
        """
        # Moonwell is well-audited Compound fork
        return 85

    def __repr__(self) -> str:
        """String representation of MoonwellProtocol.

        Returns:
            Protocol details string
        """
        return (
            f"MoonwellProtocol(network={self.network}, "
            f"read_only={self.read_only}, "
            f"data_source=base-mainnet, "
            f"safety_score={self.safety_score})"
        )
