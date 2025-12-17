"""Warm wallet provider for Tier 2 operations requiring manual approval.

Extends LocalWalletProvider with:
- Higher limits than hot wallet ($5000/tx, $10000/day)
- Manual approval requirement for all transactions
- 24-hour approval timeout (configurable)
- Contract whitelist enforcement (LOW + MEDIUM risk)
- EIP-7702 and Permit2 attack detection
- Comprehensive audit logging

The approval workflow:
1. send_transaction_async() creates pending approval
2. Waits for approval via ApprovalManager (event-driven, no polling)
3. On approval: executes transaction
4. On rejection/timeout: raises exception

Security Note:
This wallet is designed for larger transactions that exceed hot wallet
limits but don't require cold wallet security. All transactions require
explicit human approval via the approval server web interface.
"""

import asyncio
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any, Dict, Optional

from web3 import Web3
from web3.types import HexBytes, TxParams

from src.security.approval import ApprovalManager, ApprovalStatus
from src.security.audit import AuditEventType, AuditLogger, AuditSeverity
from src.security.contract_whitelist import ContractWhitelist, get_contract_whitelist
from src.security.transaction_validator import (
    TransactionValidator,
    ValidationResult,
    get_transaction_validator,
)
from src.utils.logger import get_logger
from src.wallet.hot_wallet_provider import SecurityValidationError
from src.wallet.local_wallet_provider import LocalWalletProvider
from src.wallet.tiered_config import (
    DEFAULT_WARM_CONFIG,
    TierConfig,
    TierStatus,
    WalletTier,
)

logger = get_logger(__name__)


class ApprovalTimeoutError(Exception):
    """Raised when approval request times out."""

    def __init__(self, request_id: str, timeout_hours: int):
        self.request_id = request_id
        self.timeout_hours = timeout_hours
        super().__init__(
            f"Approval request {request_id} timed out after {timeout_hours} hours"
        )


class ApprovalRejectedError(Exception):
    """Raised when approval request is rejected."""

    def __init__(self, request_id: str, reason: Optional[str] = None):
        self.request_id = request_id
        self.reason = reason
        message = f"Approval request {request_id} was rejected"
        if reason:
            message += f": {reason}"
        super().__init__(message)


class WarmWalletProvider(LocalWalletProvider):
    """Tier 2 Warm Wallet for operations requiring manual approval.

    This wallet requires explicit approval for ALL transactions via
    the approval server web interface. Designed for larger transactions
    that exceed hot wallet limits but don't require cold wallet security.

    Limits:
    - Max transaction: $5,000 USD
    - Daily limit: $10,000 USD
    - Approval timeout: 24 hours
    - Risk levels: LOW, MEDIUM

    The approval server must be running and accessible for transactions
    to complete. Transactions block until approved, rejected, or timed out.

    Attributes:
        tier_config: Configuration for this tier's limits
        tier_status: Current status (balance, spent, paused state)
        approval_manager: Handles approval workflow
        validator: Transaction security validator
        whitelist: Contract whitelist
        audit_logger: Audit trail logger
        price_oracle: Price oracle for USD conversion
    """

    def __init__(
        self,
        seed_phrase: str,
        web3: Web3,
        config: Dict[str, Any],
        approval_manager: ApprovalManager,
        tier_config: Optional[TierConfig] = None,
        whitelist: Optional[ContractWhitelist] = None,
        validator: Optional[TransactionValidator] = None,
        audit_logger: Optional[AuditLogger] = None,
        price_oracle: Optional[Any] = None,
    ):
        """Initialize warm wallet provider.

        Args:
            seed_phrase: BIP-39 mnemonic (injected at runtime)
            web3: Web3 instance connected to network
            config: Configuration dict
            approval_manager: ApprovalManager instance (REQUIRED)
            tier_config: Warm wallet tier configuration
            whitelist: Contract whitelist (default: auto-created)
            validator: Transaction validator (default: auto-created)
            audit_logger: Audit logger (default: auto-created)
            price_oracle: Price oracle for USD conversion

        Raises:
            ValueError: If approval_manager is not provided
        """
        # Initialize parent class
        super().__init__(seed_phrase, web3, config)

        # Approval manager is REQUIRED for warm wallet
        if approval_manager is None:
            raise ValueError("ApprovalManager is required for warm wallet")
        self.approval_manager = approval_manager

        # Tier configuration
        self.tier = WalletTier.WARM
        self.tier_config = tier_config or DEFAULT_WARM_CONFIG

        # Initialize status tracking
        self.tier_status = TierStatus(
            tier=self.tier,
            is_paused=False,
            current_balance_usd=Decimal("0"),
            daily_spent_usd=Decimal("0"),
        )

        # Security components
        self.whitelist = whitelist or get_contract_whitelist()
        self.validator = validator or get_transaction_validator(
            strict_mode=True,
            eip7702_detection=True,
            permit2_detection=True,
        )
        self.audit_logger = audit_logger or AuditLogger()

        # Optional price oracle for USD conversion
        self.price_oracle = price_oracle

        # Spending history (simple in-memory tracking)
        self._daily_spent_usd = Decimal("0")
        self._last_reset_date: Optional[str] = None

        # Thread safety
        self._lock = asyncio.Lock()

        logger.info(
            f"WarmWalletProvider initialized",
            extra={
                "address": self.address,
                "tier": self.tier.value,
                "max_tx_usd": str(self.tier_config.max_transaction_usd),
                "daily_limit_usd": str(self.tier_config.daily_limit_usd),
                "approval_timeout_hours": self.tier_config.approval_timeout_hours,
            },
        )

    async def send_transaction_async(
        self,
        transaction: TxParams,
        value_usd: Optional[Decimal] = None,
        rationale: str = "Warm wallet transaction",
    ) -> HexBytes:
        """Send transaction with approval workflow (async).

        This method:
        1. Validates against contract whitelist
        2. Runs security validation (EIP-7702, Permit2 detection)
        3. Checks spending limits
        4. Creates approval request
        5. Waits for approval (event-driven, max 24h)
        6. Executes transaction on approval
        7. Raises exception on rejection/timeout

        Args:
            transaction: Transaction parameters
            value_usd: Transaction value in USD (for limit checking)
            rationale: Human-readable explanation for the transaction

        Returns:
            Transaction hash

        Raises:
            SecurityValidationError: If security validation fails
            ApprovalTimeoutError: If approval times out
            ApprovalRejectedError: If approval is rejected
        """
        async with self._lock:
            to_address = transaction.get("to", "")
            tx_data = transaction.get("data", b"")
            if isinstance(tx_data, str):
                tx_data = bytes.fromhex(
                    tx_data[2:] if tx_data.startswith("0x") else tx_data
                )

            # 1. Security validation
            validation_result = self.validator.validate_transaction(
                to_address=to_address,
                value=transaction.get("value", 0),
                data=tx_data,
                from_address=self.address,
                tier_config=self.tier_config,
            )

            if not validation_result.is_valid:
                await self._log_security_block(to_address, validation_result)
                raise SecurityValidationError(
                    validation_result.rejection_reason,
                    [t.threat_type.value for t in validation_result.threats],
                )

            # Log warnings if any
            for warning in validation_result.warnings:
                logger.warning(f"Transaction warning: {warning}")

            # 2. Check spending limits
            if value_usd:
                can_spend, reason = self._check_spending_limits(value_usd)
                if not can_spend:
                    raise SecurityValidationError(reason)

            # 3. Create approval request
            logger.info(f"Creating approval request for ${value_usd} transaction")

            timeout_seconds = self.tier_config.approval_timeout_hours * 3600

            approval_request = await self.approval_manager.request_approval(
                transaction_type="warm_wallet_transaction",
                amount_usd=value_usd or Decimal("0"),
                from_protocol=None,
                to_protocol=to_address,
                rationale=rationale,
                timeout_seconds=timeout_seconds,
            )

            # Audit log approval request
            await self.audit_logger.log_event(
                AuditEventType.APPROVAL_REQUESTED,
                AuditSeverity.WARNING,
                f"Warm wallet approval requested: ${value_usd}",
                metadata={
                    "request_id": approval_request.request_id,
                    "amount_usd": str(value_usd),
                    "to": to_address,
                    "tier": self.tier.value,
                    "expires_at": approval_request.expires_at.isoformat(),
                },
            )

            # 4. Wait for approval (event-driven, no polling)
            logger.info(
                f"Waiting for approval (timeout: {self.tier_config.approval_timeout_hours}h)..."
            )

            approval_status = await self.approval_manager.wait_for_approval(
                approval_request, timeout_seconds=timeout_seconds
            )

            # 5. Handle approval result
            if approval_status == ApprovalStatus.EXPIRED:
                await self.audit_logger.log_tier_event(
                    tier=self.tier.value,
                    event_type="approval_timeout",
                    details={
                        "request_id": approval_request.request_id,
                        "timeout_hours": self.tier_config.approval_timeout_hours,
                    },
                )
                raise ApprovalTimeoutError(
                    approval_request.request_id,
                    self.tier_config.approval_timeout_hours,
                )

            if approval_status == ApprovalStatus.REJECTED:
                await self.audit_logger.log_event(
                    AuditEventType.TRANSACTION_REJECTED,
                    AuditSeverity.INFO,
                    f"Warm wallet transaction rejected",
                    metadata={"request_id": approval_request.request_id},
                )
                raise ApprovalRejectedError(approval_request.request_id)

            # Approved - execute transaction
            logger.info(f"Transaction approved, executing...")

            # 6. Execute transaction via parent class
            try:
                tx_hash = self.send_transaction(transaction)

                # Record spending
                if value_usd:
                    self._record_spending(value_usd)

                # Audit log success
                await self.audit_logger.log_event(
                    AuditEventType.TRANSACTION_EXECUTED,
                    AuditSeverity.INFO,
                    f"Warm wallet transaction executed: {tx_hash.hex()}",
                    metadata={
                        "tx_hash": tx_hash.hex(),
                        "to": to_address,
                        "value_usd": str(value_usd) if value_usd else None,
                        "tier": self.tier.value,
                        "approval_id": approval_request.request_id,
                    },
                )

                return tx_hash

            except Exception as e:
                logger.error(f"Transaction execution failed: {e}")
                raise

    def _check_spending_limits(self, amount_usd: Decimal) -> tuple[bool, str]:
        """Check if transaction amount is within limits.

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        # Reset daily counter if needed
        self._maybe_reset_daily_counter()

        # Check single transaction limit
        if amount_usd > self.tier_config.max_transaction_usd:
            return False, (
                f"Transaction ${amount_usd} exceeds max ${self.tier_config.max_transaction_usd}"
            )

        # Check daily limit
        new_daily_total = self._daily_spent_usd + amount_usd
        if new_daily_total > self.tier_config.daily_limit_usd:
            return False, (
                f"Would exceed daily limit: ${new_daily_total} > ${self.tier_config.daily_limit_usd}"
            )

        return True, "OK"

    def _record_spending(self, amount_usd: Decimal) -> None:
        """Record spending for limit tracking.

        Args:
            amount_usd: Amount spent in USD
        """
        self._maybe_reset_daily_counter()
        self._daily_spent_usd += amount_usd
        self.tier_status.daily_spent_usd = self._daily_spent_usd
        self.tier_status.transactions_today += 1

        logger.debug(
            f"Recorded spending: ${amount_usd}, daily total: ${self._daily_spent_usd}"
        )

    def _maybe_reset_daily_counter(self) -> None:
        """Reset daily counter if date has changed."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._daily_spent_usd = Decimal("0")
            self._last_reset_date = today
            self.tier_status.daily_spent_usd = Decimal("0")
            self.tier_status.transactions_today = 0
            logger.info(f"Daily spending counter reset for {today}")

    async def _log_security_block(
        self, to_address: str, validation_result: ValidationResult
    ) -> None:
        """Log a security-blocked transaction."""
        threat_types = [t.threat_type.value for t in validation_result.threats]

        await self.audit_logger.log_validation_failed(
            to_address=to_address,
            reason=validation_result.rejection_reason,
            threats=threat_types,
        )

        # Log individual threats
        for threat in validation_result.threats:
            await self.audit_logger.log_threat_detection(
                threat_type=threat.threat_type.value,
                description=threat.description,
                to_address=to_address,
            )

    def get_status(self) -> TierStatus:
        """Get current wallet status.

        Returns:
            Current TierStatus
        """
        # Update current balance if we have a price oracle
        try:
            eth_balance = self.get_balance("eth")
            if self.price_oracle:
                eth_price = self.price_oracle.get_eth_price()
                self.tier_status.current_balance_usd = eth_balance * eth_price
        except Exception:
            pass

        self.tier_status.daily_spent_usd = self._daily_spent_usd
        return self.tier_status

    def get_remaining_daily_limit(self) -> Decimal:
        """Get remaining daily spending limit.

        Returns:
            Remaining USD that can be spent today
        """
        self._maybe_reset_daily_counter()
        return max(
            Decimal("0"), self.tier_config.daily_limit_usd - self._daily_spent_usd
        )

    def can_spend(self, amount_usd: Decimal) -> tuple[bool, str]:
        """Check if an amount can be spent (pre-approval check).

        Note: Even if this returns True, the transaction still requires
        manual approval via the approval server.

        Args:
            amount_usd: Amount to check

        Returns:
            Tuple of (can_spend: bool, reason: str)
        """
        if amount_usd > self.tier_config.max_transaction_usd:
            return False, f"Exceeds max tx ${self.tier_config.max_transaction_usd}"

        remaining = self.get_remaining_daily_limit()
        if amount_usd > remaining:
            return False, f"Exceeds remaining daily limit ${remaining}"

        return True, "OK (approval still required)"

    def validate_address(self, to_address: str) -> tuple[bool, str]:
        """Validate if a destination address is allowed.

        Args:
            to_address: Address to validate

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        allowed, reason, _ = self.whitelist.validate_transaction_target(
            to_address, strict_mode=True
        )
        return allowed, reason

    def get_pending_approval_count(self) -> int:
        """Get count of pending approval requests.

        Returns:
            Number of pending approval requests
        """
        return len(self.approval_manager.get_pending_requests())
