"""CDP wallet management for Base network interactions.

This module handles wallet initialization, connection, and management
using Coinbase's CDP SDK (AgentKit).
"""

from typing import Any, Dict, Optional
from decimal import Decimal
from datetime import datetime
from coinbase_agentkit import (
    AgentKit,
    AgentKitConfig,
    CdpEvmWalletProvider,
    CdpEvmWalletProviderConfig,
)
from src.security.limits import SpendingLimits
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.security.approval import ApprovalManager, ApprovalStatus
from src.utils.logger import get_logger
from src.utils.validators import is_valid_ethereum_address
from src.data.oracles import PriceOracle, create_price_oracle

logger = get_logger(__name__)


class WalletManager:
    """Manages wallet operations using CDP SDK for Base network.

    Handles wallet initialization, balance checking, and provides
    the interface for transaction signing and submission.

    IMPORTANT: This uses CDP's server-side managed wallet service.
    Keys are managed by CDP, not derived locally.

    Attributes:
        wallet: CDP wallet instance (server-side managed)
        address: Wallet address
        network: Network name (base-mainnet or base-sepolia)
        dry_run_mode: If True, simulates all transactions
        audit_logger: Audit logging instance
        spending_limits: Spending limit enforcement
    """

    def __init__(
        self,
        config: Dict[str, Any],
        price_oracle: Optional[PriceOracle] = None,
        approval_manager: Optional[ApprovalManager] = None
    ) -> None:
        """Initialize the wallet manager.

        Args:
            config: Configuration with CDP credentials and network settings
            price_oracle: Optional price oracle for USD conversions (defaults to MockPriceOracle)
            approval_manager: Optional approval manager for transaction authorization
        """
        self.config = config
        self.agent_kit: Optional[AgentKit] = None
        self.wallet_provider: Optional[CdpEvmWalletProvider] = None
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

    async def initialize(self) -> None:
        """Initialize CDP-managed wallet using AgentKit.

        This creates a new CDP wallet or uses existing credentials.
        CDP/AgentKit handles all key management server-side - no local derivation.

        Raises:
            ValueError: If CDP credentials are invalid
            ConnectionError: If unable to connect to CDP service
        """
        try:
            # Create wallet provider configuration
            wallet_config = CdpEvmWalletProviderConfig(
                api_key_id=self.config.get("cdp_api_key"),
                api_key_secret=self.config.get("cdp_api_secret"),
                network_id=self.network,
            )

            logger.info(f"Initializing CDP wallet for network: {self.network}")

            # Create wallet provider
            self.wallet_provider = CdpEvmWalletProvider(wallet_config)

            # Initialize AgentKit with wallet provider
            agentkit_config = AgentKitConfig(wallet_provider=self.wallet_provider)
            self.agent_kit = AgentKit(agentkit_config)

            # Get wallet address
            self.address = await self.wallet_provider.get_address()

            logger.info(f"Wallet initialized: {self.address[:10]}...{self.address[-8:]}")

            # Log wallet initialization in audit trail
            mode = "DRY_RUN" if self.dry_run_mode else "LIVE"
            await self.audit_logger.log_event(
                AuditEventType.WALLET_INITIALIZED,
                AuditSeverity.INFO,
                {
                    "wallet_address": self.address,
                    "network": self.network,
                    "mode": mode,
                },
            )

            logger.info(f"Wallet initialized successfully in {mode} mode")

        except Exception as e:
            logger.error(f"Failed to initialize CDP wallet: {e}")
            await self.audit_logger.log_event(
                AuditEventType.SECURITY_VIOLATION,
                AuditSeverity.ERROR,
                {"error": "wallet_initialization_failed", "message": str(e)},
            )
            raise

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
            balance = await self.wallet_provider.get_balance(token.lower())
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

        try:
            # Export wallet data via CDP wallet provider
            wallet_data = await self.wallet_provider.export()

            # Log successful export
            await self.audit_logger.log_event(
                AuditEventType.WALLET_EXPORT,
                AuditSeverity.CRITICAL,
                {"wallet_address": self.address, "operation": "export_completed"},
            )

            return {
                "address": self.address,
                "network_id": self.network,
                "data": wallet_data,
                "warning": "CRITICAL: Never commit to git or share!",
                "exported_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to export wallet: {e}")
            await self.audit_logger.log_event(
                AuditEventType.SECURITY_VIOLATION,
                AuditSeverity.ERROR,
                {"error": "wallet_export_failed", "message": str(e)},
            )
            raise

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
