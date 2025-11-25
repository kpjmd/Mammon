"""Wallet management for Base network interactions.

This module handles wallet initialization, connection, and management.
Supports both CDP wallet provider and local wallet provider.
"""

from typing import Any, Dict, Optional, Union
from decimal import Decimal
from datetime import datetime
from coinbase_agentkit import (
    AgentKit,
    AgentKitConfig,
    CdpEvmWalletProvider,
    CdpEvmWalletProviderConfig,
)
from src.wallet.base_provider import WalletProvider
from src.wallet.local_wallet_provider import LocalWalletProvider
from src.security.limits import SpendingLimits
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.security.approval import ApprovalManager, ApprovalStatus
from src.utils.logger import get_logger
from src.utils.validators import is_valid_ethereum_address
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings
from src.data.oracles import PriceOracle, create_price_oracle

logger = get_logger(__name__)


class WalletManager:
    """Manages wallet operations for Base network.

    Handles wallet initialization, balance checking, and provides
    the interface for transaction signing and submission.

    Supports two wallet modes:
    1. Local Wallet (default): Uses BIP-39 seed phrase, full control
    2. CDP Wallet: Uses CDP's server-side managed wallet service

    Attributes:
        wallet_provider: Wallet provider instance (Local or CDP)
        address: Wallet address
        network: Network name (base-mainnet or base-sepolia)
        dry_run_mode: If True, simulates all transactions
        audit_logger: Audit logging instance
        spending_limits: Spending limit enforcement
        use_local_wallet: If True, uses local wallet provider
    """

    def __init__(
        self,
        config: Dict[str, Any],
        price_oracle: Optional[PriceOracle] = None,
        approval_manager: Optional[ApprovalManager] = None
    ) -> None:
        """Initialize the wallet manager.

        Args:
            config: Configuration with wallet credentials and network settings
            price_oracle: Optional price oracle for USD conversions (defaults to MockPriceOracle)
            approval_manager: Optional approval manager for transaction authorization
        """
        self.config = config
        self.use_local_wallet = config.get("use_local_wallet", True)
        self.agent_kit: Optional[AgentKit] = None
        self.wallet_provider: Optional[Union[WalletProvider, CdpEvmWalletProvider]] = None
        self.address: Optional[str] = None
        self.network = config.get("network", "base-sepolia")
        self.dry_run_mode = config.get("dry_run_mode", True)
        self.audit_logger = AuditLogger()
        self.spending_limits = SpendingLimits(config)

        # Initialize price oracle (defaults to mock for Phase 1C)
        self.price_oracle = price_oracle or create_price_oracle("mock")

        # Initialize approval manager (optional - if not provided, no approvals required)
        self.approval_manager = approval_manager

        if self.dry_run_mode:
            logger.info("🔒 WalletManager initialized in DRY RUN mode")

        wallet_type = "LOCAL" if self.use_local_wallet else "CDP"
        logger.info(f"📋 Wallet mode: {wallet_type}")

    async def initialize(self) -> None:
        """Initialize wallet using configured provider (Local or CDP).

        Raises:
            ValueError: If wallet configuration is invalid
            ConnectionError: If unable to connect to network/service
        """
        try:
            # Initialize wallet provider based on configuration
            if self.use_local_wallet:
                await self._initialize_local_wallet()
            else:
                await self._initialize_cdp_wallet()

            # Log wallet initialization in audit trail
            mode = "DRY_RUN" if self.dry_run_mode else "LIVE"
            wallet_type = "LOCAL" if self.use_local_wallet else "CDP"
            await self.audit_logger.log_event(
                AuditEventType.WALLET_INITIALIZED,
                AuditSeverity.INFO,
                f"Wallet initialized: {wallet_type} mode on {self.network}",
                metadata={
                    "wallet_address": self.address,
                    "network": self.network,
                    "mode": mode,
                    "wallet_type": wallet_type,
                },
            )

            logger.info(f"✅ Wallet initialized successfully in {mode} mode ({wallet_type})")

        except Exception as e:
            logger.error(f"Failed to initialize wallet: {e}")
            await self.audit_logger.log_event(
                AuditEventType.SECURITY_VIOLATION,
                AuditSeverity.ERROR,
                f"Wallet initialization failed: {str(e)}",
                metadata={"error": "wallet_initialization_failed", "message": str(e)},
            )
            raise

    async def _initialize_local_wallet(self) -> None:
        """Initialize local wallet from seed phrase.

        Raises:
            ValueError: If seed phrase is missing or invalid
        """
        seed_phrase = self.config.get("wallet_seed")
        if not seed_phrase:
            raise ValueError(
                "WALLET_SEED not found in configuration. "
                "Please set WALLET_SEED in .env file."
            )

        logger.info(f"Initializing local wallet for network: {self.network}")

        # Get Web3 instance for network with premium RPC support
        settings = get_settings()
        w3 = get_web3(self.network, config=settings)

        # Create local wallet provider
        self.wallet_provider = LocalWalletProvider(
            seed_phrase=seed_phrase,
            web3=w3,
            config=self.config,
        )

        # Get wallet address
        self.address = self.wallet_provider.get_address()

        logger.info(f"✅ Local wallet initialized: {self.address}")

    async def _initialize_cdp_wallet(self) -> None:
        """Initialize CDP-managed wallet using AgentKit.

        Raises:
            ValueError: If CDP credentials are invalid
        """
        # Create wallet provider configuration
        wallet_config = CdpEvmWalletProviderConfig(
            api_key_id=self.config.get("cdp_api_key"),
            api_key_secret=self.config.get("cdp_api_secret"),
            wallet_secret=self.config.get("cdp_wallet_secret"),
            network_id=self.network,
        )

        logger.info(f"Initializing CDP wallet for network: {self.network}")

        # Create wallet provider
        self.wallet_provider = CdpEvmWalletProvider(wallet_config)

        # Initialize AgentKit with wallet provider
        agentkit_config = AgentKitConfig(wallet_provider=self.wallet_provider)
        self.agent_kit = AgentKit(agentkit_config)

        # Get wallet address
        self.address = self.wallet_provider.get_address()

        logger.info(f"✅ CDP wallet initialized: {self.address}")

    async def get_balance(self, token: str = "ETH") -> Decimal:
        """Get wallet balance for a specific token.

        Args:
            token: Token symbol (default: ETH)

        Returns:
            Token balance

        Raises:
            ValueError: If wallet not initialized
        """
        if not self.wallet_provider:
            raise ValueError("Wallet not initialized. Call initialize() first.")

        try:
            # Get balance from CDP wallet provider
            # NOTE: get_balance is synchronous, not async
            balance = self.wallet_provider.get_balance(token.lower())
            balance_decimal = Decimal(str(balance))

            logger.debug(f"Balance for {token}: {balance_decimal}")
            return balance_decimal

        except Exception as e:
            logger.error(f"Failed to get balance for {token}: {e}")
            return Decimal("0")

    async def get_balances(self) -> Dict[str, Decimal]:
        """Get all token balances in the wallet.

        Returns:
            Dict mapping token symbols to balances

        Raises:
            ValueError: If wallet not initialized
        """
        if not self.wallet_provider:
            raise ValueError("Wallet not initialized. Call initialize() first.")

        try:
            # For Phase 1B, return ETH balance
            # TODO: Expand to query multiple token balances in Phase 2
            eth_balance = await self.get_balance("eth")
            balance_dict = {"eth": eth_balance}

            logger.debug(f"All balances: {balance_dict}")
            return balance_dict

        except Exception as e:
            logger.error(f"Failed to get balances: {e}")
            return {}

    async def get_address(self) -> str:
        """Get the wallet address.

        Returns:
            Wallet address

        Raises:
            ValueError: If wallet not initialized
        """
        if not self.address:
            raise ValueError("Wallet not initialized. Call initialize() first.")

        return self.address

    async def export_wallet_data(self, require_confirmation: bool = True) -> Dict[str, Any]:
        """Export wallet data for backup (CRITICAL SECURITY OPERATION).

        This operation is logged with CRITICAL severity.
        NEVER commit exported wallet data to version control!

        Args:
            require_confirmation: If True, requires user confirmation

        Returns:
            Wallet data dictionary with encrypted backup

        Raises:
            ValueError: If wallet not initialized or user cancels
        """
        if not self.wallet_provider:
            raise ValueError("Wallet not initialized. Call initialize() first.")

        # Log CRITICAL security event
        await self.audit_logger.log_event(
            AuditEventType.WALLET_EXPORT,
            AuditSeverity.CRITICAL,
            {"wallet_address": self.address, "operation": "export_attempt"},
        )

        if require_confirmation:
            print("\n" + "=" * 70)
            print("⚠️  CRITICAL SECURITY WARNING ⚠️")
            print("=" * 70)
            print("You are about to export wallet data.")
            print("This data contains sensitive information that could be used to")
            print("access your wallet and funds.")
            print("")
            print("SECURITY REQUIREMENTS:")
            print("  - NEVER share this data with anyone")
            print("  - NEVER commit this data to version control")
            print("  - Store this data in a secure, encrypted location")
            print("  - Delete exported data after secure backup")
            print("=" * 70)

            confirm = input("Type 'EXPORT' to proceed: ")
            if confirm != "EXPORT":
                logger.info("Wallet export cancelled by user")
                raise ValueError("Export cancelled by user")

        # NOTE: CDP AgentKit CdpEvmWalletProvider does not expose an export() method
        # This functionality would require direct CDP API calls
        # TODO Phase 2B: Implement wallet export via CDP REST API
        raise NotImplementedError(
            "Wallet export is not yet implemented. "
            "CDP AgentKit does not expose wallet export functionality. "
            "This requires direct CDP API integration."
        )

    async def is_connected(self) -> bool:
        """Check if wallet is connected to the network.

        Returns:
            True if connected, False otherwise
        """
        if not self.wallet_provider or not self.address:
            return False

        try:
            # Try to get balance as connectivity check
            await self.get_balance("eth")
            return True
        except Exception as e:
            logger.warning(f"Wallet connectivity check failed: {e}")
            return False

    async def _check_spending_limits(self, amount_usd: Decimal) -> bool:
        """Verify transaction doesn't exceed configured spending limits.

        This is a critical security check that must pass before building
        any transaction.

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            True if within limits, False otherwise
        """
        # Check per-transaction limit
        if not self.spending_limits.check_transaction_limit(amount_usd):
            await self.audit_logger.log_event(
                AuditEventType.LIMIT_EXCEEDED,
                AuditSeverity.WARNING,
                {
                    "amount_usd": str(amount_usd),
                    "limit_type": "per_transaction",
                    "limit_value": str(self.spending_limits.max_transaction_usd),
                },
            )
            logger.warning(
                f"Transaction exceeds per-transaction limit: "
                f"${amount_usd} > ${self.spending_limits.max_transaction_usd}"
            )
            return False

        # Check daily limit
        if not self.spending_limits.check_daily_limit(amount_usd):
            await self.audit_logger.log_event(
                AuditEventType.LIMIT_EXCEEDED,
                AuditSeverity.WARNING,
                {
                    "amount_usd": str(amount_usd),
                    "limit_type": "daily",
                    "limit_value": str(self.spending_limits.daily_limit_usd),
                },
            )
            logger.warning(
                f"Transaction exceeds daily limit: "
                f"${amount_usd} would exceed ${self.spending_limits.daily_limit_usd}"
            )
            return False

        return True

    async def _convert_to_usd(self, amount: Decimal, token: str = "ETH") -> Decimal:
        """Convert token amount to USD using price oracle.

        Args:
            amount: Token amount
            token: Token symbol

        Returns:
            Amount in USD

        Note:
            Uses price oracle for conversion. In Phase 1C, defaults to
            MockPriceOracle ($3000/ETH). Phase 2A+ will use Chainlink.
        """
        # Get current price from oracle
        price = await self.price_oracle.get_price(token.upper(), "USD")
        return amount * price

    async def estimate_gas(
        self, to: str, amount: Decimal, data: str = "", token: str = "ETH"
    ) -> int:
        """Estimate gas required with tiered safety buffers based on complexity.

        Uses eth_estimateGas to predict gas consumption, then adds a safety buffer
        that scales with transaction complexity. More complex transactions get
        larger buffers due to higher estimation uncertainty.

        Buffer Tiers:
        - Simple ETH transfer (no data): 20% buffer
        - ERC20 transfer (small data): 30% buffer
        - Simple DEX swap (medium data): 50% buffer
        - Complex multi-hop (large data): 100% buffer

        Args:
            to: Recipient address
            amount: Amount to send
            data: Transaction data (hex string)
            token: Token symbol (default: ETH)

        Returns:
            Estimated gas units (with tiered safety buffer)

        Raises:
            ValueError: If wallet not initialized or estimation fails
        """
        if not self.wallet_provider:
            raise ValueError("Wallet not initialized. Call initialize() first.")

        try:
            # Get Web3 instance for gas estimation with premium RPC support
            from src.utils.web3_provider import get_web3
            from src.utils.config import get_settings
            settings = get_settings()
            w3 = get_web3(self.network, config=settings)

            # Convert amount to wei
            if token == "ETH":
                value_wei = w3.to_wei(str(amount), "ether")
            else:
                # For ERC20 tokens, value is 0 (amount is in data)
                value_wei = 0

            # Build transaction params for estimation
            tx_params = {
                "from": self.address,
                "to": to,
                "value": value_wei,
            }

            if data and data != "0x":
                tx_params["data"] = data

            # Estimate gas
            estimated_gas = w3.eth.estimate_gas(tx_params)

            # Determine complexity tier and buffer
            data_length = len(data) if data and data != "0x" else 0

            if token == "ETH" and data_length == 0:
                # Simple ETH transfer - very accurate
                buffer_percent = 1.20  # 20%
                complexity = "simple_transfer"
            elif data_length < 100:
                # ERC20 transfer or simple contract call
                buffer_percent = 1.30  # 30%
                complexity = "simple_contract"
            elif data_length < 500:
                # DEX swap or moderate complexity
                buffer_percent = 1.50  # 50%
                complexity = "dex_swap"
            else:
                # Complex multi-hop or batch operations
                buffer_percent = 2.00  # 100%
                complexity = "complex_operation"

            gas_with_buffer = int(estimated_gas * buffer_percent)

            logger.info(
                f"Gas estimate: {estimated_gas} units "
                f"({complexity}, {int((buffer_percent-1)*100)}% buffer) "
                f"→ {gas_with_buffer} units"
            )

            return gas_with_buffer

        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            # Provide reasonable default for simple transfers
            default_gas = 21000 if token == "ETH" and not data else 100000
            logger.warning(f"Using default gas estimate: {default_gas}")
            return int(default_gas * 1.2)

    async def build_transaction(
        self, to: str, amount: Decimal, data: str = "", token: str = "ETH"
    ) -> Dict[str, Any]:
        """Build unsigned transaction with security checks (NO EXECUTION).

        This method builds a transaction but does NOT execute it.
        All spending limits are enforced before building.
        In dry-run mode, returns a simulated transaction.

        Args:
            to: Recipient address
            amount: Amount to send
            data: Optional transaction data
            token: Token symbol (default: ETH)

        Returns:
            Transaction object (unsigned in dry-run, ready in live mode)

        Raises:
            ValueError: If limits exceeded or invalid parameters
        """
        if not self.wallet_provider:
            raise ValueError("Wallet not initialized. Call initialize() first.")

        # Validate recipient address
        if not is_valid_ethereum_address(to):
            raise ValueError(f"Invalid recipient address: {to}")

        # Convert to USD for limit checking
        amount_usd = await self._convert_to_usd(amount, token)

        # Enforce spending limits
        if not await self._check_spending_limits(amount_usd):
            raise ValueError(f"Transaction exceeds spending limits: ${amount_usd}")

        # Check if approval required
        if self.approval_manager and self.approval_manager.requires_approval(amount_usd):
            logger.info(f"Transaction requires approval (${amount_usd} >= ${self.approval_manager.approval_threshold_usd})")

            # Create approval request
            approval_request = await self.approval_manager.request_approval(
                transaction_type="transfer",
                amount_usd=amount_usd,
                from_protocol=None,
                to_protocol=self.network,
                rationale=f"Transfer {amount} {token} to {to}",
            )

            # Log approval request
            await self.audit_logger.log_event(
                AuditEventType.APPROVAL_REQUESTED,
                AuditSeverity.WARNING,
                f"Approval requested for ${amount_usd} transaction",
                metadata={
                    "request_id": approval_request.request_id,
                    "amount_usd": str(amount_usd),
                    "to": to,
                    "token": token,
                }
            )

            # Wait for approval (with timeout)
            approval_status = await self.approval_manager.wait_for_approval(
                approval_request,
                timeout_seconds=3600  # 1 hour timeout
            )

            if approval_status != ApprovalStatus.APPROVED:
                # Log rejection
                await self.audit_logger.log_event(
                    AuditEventType.TRANSACTION_REJECTED,
                    AuditSeverity.WARNING,
                    f"Transaction rejected: {approval_status.value}",
                    metadata={
                        "request_id": approval_request.request_id,
                        "status": approval_status.value,
                    }
                )
                raise ValueError(f"Transaction not approved: {approval_status.value}")

            # Log approval
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_APPROVED,
                AuditSeverity.INFO,
                f"Transaction approved: ${amount_usd}",
                metadata={"request_id": approval_request.request_id}
            )

        # Build transaction data
        tx = {
            "from": self.address,
            "to": to,
            "value": str(amount),
            "token": token,
            "data": data,
            "network": self.network,
            "estimated_cost_usd": str(amount_usd),
        }

        # DRY RUN MODE HANDLING
        if self.dry_run_mode:
            logger.info("🔒 DRY RUN: Transaction that WOULD be built:")
            logger.info(f"   From: {tx['from']}")
            logger.info(f"   To: {tx['to']}")
            logger.info(f"   Amount: {amount} {token}")
            logger.info(f"   Estimated Cost: ${amount_usd} USD")

            # Log as dry-run in audit
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_INITIATED,
                AuditSeverity.INFO,
                {
                    "mode": "DRY_RUN",
                    "from": self.address,
                    "to": to,
                    "amount": str(amount),
                    "token": token,
                    "amount_usd": str(amount_usd),
                    "would_execute": False,
                },
            )

            return {
                "dry_run": True,
                "would_execute": False,
                "transaction": tx,
                "message": "Transaction built in dry-run mode - not executed",
            }

        # LIVE MODE (only if explicitly enabled)
        logger.warning("⚠️ LIVE MODE: Building real transaction")
        await self.audit_logger.log_event(
            AuditEventType.TRANSACTION_INITIATED,
            AuditSeverity.WARNING,
            {
                "mode": "LIVE",
                "from": self.address,
                "to": to,
                "amount": str(amount),
                "token": token,
                "amount_usd": str(amount_usd),
                "status": "unsigned",
            },
        )

        return tx

    async def sign_transaction(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Sign a transaction using CDP wallet provider.

        Args:
            transaction: Transaction dictionary to sign

        Returns:
            Signed transaction with signature

        Raises:
            ValueError: If wallet not initialized or signing fails
        """
        if not self.wallet_provider:
            raise ValueError("Wallet not initialized. Call initialize() first.")

        if self.dry_run_mode:
            logger.info("🔒 DRY RUN: Transaction would be signed")
            return {**transaction, "signed": False, "dry_run": True}

        try:
            # CDP wallet provider handles signing internally
            logger.info("Signing transaction via CDP wallet provider...")

            # The CDP wallet provider will sign during transaction invocation
            # We return the transaction with metadata indicating it's ready to sign
            signed_tx = {
                **transaction,
                "signed": True,
                "signer": self.address,
            }

            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_SIGNED,
                AuditSeverity.INFO,
                {
                    "from": self.address,
                    "to": transaction.get("to"),
                    "amount": transaction.get("value"),
                },
            )

            return signed_tx

        except Exception as e:
            logger.error(f"Transaction signing failed: {e}")
            await self.audit_logger.log_event(
                AuditEventType.SECURITY_VIOLATION,
                AuditSeverity.ERROR,
                {"error": "transaction_signing_failed", "message": str(e)},
            )
            raise

    async def execute_transaction(
        self,
        to: str,
        amount: Decimal,
        data: str = "",
        token: str = "ETH",
        wait_for_confirmation: bool = False,
        confirmation_blocks: int = 2,
    ) -> Dict[str, Any]:
        """Execute a transaction on the blockchain (REAL EXECUTION).

        This is the ONLY method that actually sends transactions to the network.
        All safety checks are performed before execution:
        1. Transaction simulation (detects reverts)
        2. Spending limits (atomic check-and-record)
        3. Approval requirements (if >$100)
        4. Gas price caps (rejects if too high)
        5. Gas estimation with tiered buffers
        6. Dry-run mode check

        Args:
            to: Recipient address
            amount: Amount to send
            data: Transaction data (for contract calls)
            token: Token symbol (default: ETH)
            wait_for_confirmation: If True, wait for N block confirmations (default: False)
                WARNING: Blocks agent for ~5 seconds. For high-frequency operations,
                use False and monitor separately.
            confirmation_blocks: Number of blocks to wait for if waiting (default: 2)

        Returns:
            Dict with transaction hash, status, and confirmation state:
                - success: bool
                - tx_hash: str
                - confirmed: bool (True if wait_for_confirmation=True and confirmed)
                - confirmations: int (if waited)
                - ...

        Raises:
            ValueError: If dry-run mode enabled, limits exceeded, simulation fails,
                       gas price too high, or execution fails
        """
        if self.dry_run_mode:
            logger.warning("🔒 DRY RUN MODE: Cannot execute real transactions")
            raise ValueError(
                "Cannot execute transaction in dry-run mode. "
                "Set DRY_RUN_MODE=false in .env to enable real transactions."
            )

        if not self.wallet_provider:
            raise ValueError("Wallet not initialized. Call initialize() first.")

        # Build and validate transaction (includes spending limits and approval)
        tx = await self.build_transaction(to, amount, data, token)

        # CRITICAL SAFETY: Simulate transaction before execution
        # This detects reverts BEFORE wasting gas
        from src.blockchain.transactions import TransactionBuilder
        tx_builder = TransactionBuilder(self, {"network": self.network})

        logger.info("🔍 Simulating transaction before execution...")
        simulation = await tx_builder.simulate_transaction(
            to_address=to,
            data=data,
            value=amount,
            from_address=self.address,
        )

        if not simulation["success"]:
            revert_reason = simulation["revert_reason"]
            logger.error(f"❌ Simulation failed: {revert_reason}")
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_FAILED,
                AuditSeverity.ERROR,
                f"Simulation detected revert: {revert_reason}",
                metadata={
                    "from": self.address,
                    "to": to,
                    "amount": str(amount),
                    "token": token,
                    "revert_reason": revert_reason,
                },
            )
            raise ValueError(
                f"Transaction simulation failed - would revert: {revert_reason}. "
                f"Transaction NOT executed (saved gas)."
            )

        logger.info(f"✅ Simulation successful, gas estimate: {simulation['gas_used']}")

        # Estimate gas
        gas_limit = await self.estimate_gas(to, amount, data, token)

        try:
            # Get Web3 for gas price with premium RPC support
            from src.utils.web3_provider import get_web3
            from src.utils.config import get_settings
            settings = get_settings()
            w3 = get_web3(self.network, config=settings)

            # Get current gas price (EIP-1559 for Base)
            latest_block = w3.eth.get_block("latest")
            base_fee = latest_block.get("baseFeePerGas", 0)

            # Add priority fee (1 gwei for fast confirmation)
            max_priority_fee = w3.to_wei(1, "gwei")
            max_fee_per_gas = (base_fee * 2) + max_priority_fee  # 2x base + priority

            # CRITICAL SAFETY: Check gas price cap
            max_allowed_gas_price = w3.to_wei(
                str(self.config.get("max_gas_price_gwei", 100)), "gwei"
            )
            gas_price_gwei = w3.from_wei(max_fee_per_gas, "gwei")

            if max_fee_per_gas > max_allowed_gas_price:
                max_allowed_gwei = self.config.get("max_gas_price_gwei", 100)
                logger.error(
                    f"❌ Gas price too high: {gas_price_gwei} gwei > "
                    f"max allowed {max_allowed_gwei} gwei"
                )
                await self.audit_logger.log_event(
                    AuditEventType.SECURITY_VIOLATION,
                    AuditSeverity.WARNING,
                    f"Transaction rejected: gas price {gas_price_gwei} gwei exceeds limit",
                    metadata={
                        "gas_price_gwei": str(gas_price_gwei),
                        "max_allowed_gwei": str(max_allowed_gwei),
                        "from": self.address,
                        "to": to,
                    },
                )
                raise ValueError(
                    f"Gas price too high: {gas_price_gwei} gwei exceeds maximum "
                    f"allowed {max_allowed_gwei} gwei. Transaction aborted for safety."
                )

            logger.info(f"Gas price: {gas_price_gwei} gwei (within limit)")

            # Use CDP wallet provider to send transaction
            logger.warning("⚠️ EXECUTING REAL TRANSACTION ON BLOCKCHAIN")

            # Convert amount to wei for native token
            if token == "ETH":
                value_wei = w3.to_wei(str(amount), "ether")
            else:
                value_wei = 0

            # Build transaction params
            tx_params = {
                "from": self.address,
                "to": to,
                "value": value_wei,
                "gas": gas_limit,
                "maxFeePerGas": max_fee_per_gas,
                "maxPriorityFeePerGas": max_priority_fee,
            }

            if data and data != "0x":
                tx_params["data"] = data

            # CRITICAL SAFETY: Atomic spending limit check + record
            # This prevents race conditions where multiple transactions
            # could exceed limits if checked separately
            amount_usd = await self._convert_to_usd(amount, token)
            is_allowed, reject_reason = await self.spending_limits.atomic_check_and_record(
                amount_usd
            )

            if not is_allowed:
                logger.error(f"❌ Spending limit check failed: {reject_reason}")
                await self.audit_logger.log_event(
                    AuditEventType.LIMIT_EXCEEDED,
                    AuditSeverity.WARNING,
                    f"Transaction rejected: {reject_reason}",
                    metadata={
                        "amount_usd": str(amount_usd),
                        "from": self.address,
                        "to": to,
                    },
                )
                raise ValueError(
                    f"Spending limit exceeded: {reject_reason}. "
                    f"Transaction aborted before execution."
                )

            logger.info(f"✅ Spending limits checked and recorded: ${amount_usd}")

            # Send via CDP wallet provider
            # NOTE: CDP AgentKit handles signing and sending internally
            # NOTE: send_transaction is synchronous, not async
            tx_hash_bytes = self.wallet_provider.send_transaction(tx_params)

            # Convert HexBytes to hex string for JSON serialization
            tx_hash = tx_hash_bytes.hex() if hasattr(tx_hash_bytes, 'hex') else str(tx_hash_bytes)

            logger.info(f"✅ Transaction submitted: {tx_hash}")

            # Log successful execution with comprehensive gas metrics
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_EXECUTED,
                AuditSeverity.WARNING,
                f"Transaction executed: {tx_hash}",
                metadata={
                    "tx_hash": tx_hash,
                    "from": self.address,
                    "to": to,
                    "amount": str(amount),
                    "token": token,
                    "amount_usd": str(amount_usd),
                    "gas_limit": gas_limit,
                    "max_fee_per_gas_gwei": str(float(w3.from_wei(max_fee_per_gas, "gwei"))),
                    "max_priority_fee_gwei": str(float(w3.from_wei(max_priority_fee, "gwei"))),
                    "base_fee_gwei": str(float(w3.from_wei(base_fee, "gwei"))),
                    "estimated_gas_cost_eth": str(float(w3.from_wei(gas_limit * max_fee_per_gas, "ether"))),
                    "network": self.network,
                },
            )

            # Note: Spending already recorded in atomic_check_and_record above

            # Optional: Wait for confirmation (blocks agent)
            confirmed = False
            confirmations_count = 0

            if wait_for_confirmation:
                logger.warning(
                    f"⏳ Waiting for {confirmation_blocks} block confirmations "
                    f"(will block agent for ~{confirmation_blocks * 2}s)..."
                )

                from src.blockchain.monitor import ChainMonitor

                monitor = ChainMonitor({"network": self.network}, self.address)
                confirmed = await monitor.wait_for_confirmation(
                    tx_hash, confirmations=confirmation_blocks, timeout=300
                )

                if confirmed:
                    confirmations_count = confirmation_blocks
                    logger.info(f"✅ Transaction confirmed with {confirmations_count} blocks")
                else:
                    logger.warning(f"⚠️ Transaction not confirmed within timeout")

            return {
                "success": True,
                "tx_hash": tx_hash,
                "confirmed": confirmed,
                "confirmations": confirmations_count,
                "from": self.address,
                "to": to,
                "amount": str(amount),
                "token": token,
                "network": self.network,
                "gas_limit": gas_limit,
                "waited_for_confirmation": wait_for_confirmation,
            }

        except Exception as e:
            logger.error(f"Transaction execution failed: {e}")
            await self.audit_logger.log_event(
                AuditEventType.TRANSACTION_FAILED,
                AuditSeverity.ERROR,
                {
                    "error": str(e),
                    "from": self.address,
                    "to": to,
                    "amount": str(amount),
                    "token": token,
                },
            )
            raise

    async def send_transaction(
        self,
        to: str,
        data: str = "",
        value: Decimal = Decimal("0"),
        token: str = "ETH",
    ) -> str:
        """Send a transaction (simplified interface for protocol executors).

        This is a convenience wrapper around execute_transaction() that:
        - Uses 'value' parameter name (common convention)
        - Returns just the tx_hash string (not full dict)
        - Provides simpler interface for protocol operations

        Args:
            to: Recipient address
            data: Transaction data for contract calls
            value: Amount to send (default: 0)
            token: Token symbol (default: ETH)

        Returns:
            Transaction hash as hex string

        Raises:
            ValueError: If execution fails
        """
        result = await self.execute_transaction(
            to=to,
            amount=value,
            data=data,
            token=token,
            wait_for_confirmation=False,
        )

        if not result.get("success"):
            raise ValueError(f"Transaction failed: {result.get('error')}")

        return result["tx_hash"]
