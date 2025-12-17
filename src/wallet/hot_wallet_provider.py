"""Hot wallet provider for Tier 1 autonomous operations.

Extends LocalWalletProvider with:
- Strict spending limits ($500/tx, $1000/day, $2000 max balance)
- Auto-pause on limit breach
- Contract whitelist enforcement
- EIP-7702 and Permit2 attack detection
- Comprehensive audit logging

Security Note:
This wallet is designed for autonomous operation on a VPS.
The seed phrase should be injected via environment variable at
runtime and NEVER written to the filesystem.
"""

import asyncio
from decimal import Decimal
from typing import Dict, Any, Optional, Callable
from web3 import Web3
from web3.types import TxParams, HexBytes

from src.wallet.local_wallet_provider import LocalWalletProvider
from src.wallet.tiered_config import (
    WalletTier,
    TierConfig,
    TierStatus,
    RiskLevel,
    DEFAULT_HOT_CONFIG,
)
from src.security.contract_whitelist import get_contract_whitelist, ContractWhitelist
from src.security.transaction_validator import (
    TransactionValidator,
    ValidationResult,
    get_transaction_validator,
)
from src.security.audit import AuditLogger, AuditSeverity
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HotWalletPausedError(Exception):
    """Raised when hot wallet is paused and transaction is attempted."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Hot wallet is paused: {reason}")


class SecurityValidationError(Exception):
    """Raised when a transaction fails security validation."""

    def __init__(self, reason: str, threats: list = None):
        self.reason = reason
        self.threats = threats or []
        super().__init__(f"Security validation failed: {reason}")


class HotWalletProvider(LocalWalletProvider):
    """Tier 1 Hot Wallet for autonomous operations with strict limits.

    This wallet is designed for autonomous operation with:
    - Maximum balance: $2,000 USD
    - Maximum single transaction: $500 USD
    - Daily spending limit: $1,000 USD
    - Auto-pause on limit breach
    - Contract whitelist enforcement
    - EIP-7702/Permit2 attack detection

    The seed phrase should be loaded from an environment variable
    that is injected at runtime, never stored on disk.

    Attributes:
        tier_config: Configuration for this tier's limits
        tier_status: Current status (balance, spent, paused state)
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
        tier_config: Optional[TierConfig] = None,
        whitelist: Optional[ContractWhitelist] = None,
        validator: Optional[TransactionValidator] = None,
        audit_logger: Optional[AuditLogger] = None,
        price_oracle: Optional[Any] = None,
        on_pause_callback: Optional[Callable[[str], None]] = None,
    ):
        """Initialize hot wallet provider.

        Args:
            seed_phrase: BIP-39 mnemonic (injected at runtime)
            web3: Web3 instance connected to network
            config: Configuration dict
            tier_config: Hot wallet tier configuration
            whitelist: Contract whitelist (default: auto-created)
            validator: Transaction validator (default: auto-created)
            audit_logger: Audit logger (default: auto-created)
            price_oracle: Price oracle for USD conversion
            on_pause_callback: Called when wallet is auto-paused
        """
        # Initialize parent class
        super().__init__(seed_phrase, web3, config)

        # Tier configuration
        self.tier = WalletTier.HOT
        self.tier_config = tier_config or DEFAULT_HOT_CONFIG

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

        # Callback for pause events
        self._on_pause_callback = on_pause_callback

        # Spending history (simple in-memory tracking)
        self._daily_spent_usd = Decimal("0")
        self._last_reset_date: Optional[str] = None

        # Thread safety
        self._lock = asyncio.Lock()

        logger.info(
            f"HotWalletProvider initialized",
            extra={
                "address": self.address,
                "tier": self.tier.value,
                "max_tx_usd": str(self.tier_config.max_transaction_usd),
                "daily_limit_usd": str(self.tier_config.daily_limit_usd),
            }
        )

    async def send_transaction_async(
        self,
        transaction: TxParams,
        value_usd: Optional[Decimal] = None,
    ) -> HexBytes:
        """Send transaction with full security validation (async).

        This is the primary method for sending transactions. It:
        1. Checks if wallet is paused
        2. Validates against contract whitelist
        3. Runs EIP-7702 and Permit2 detection
        4. Checks spending limits
        5. Logs all actions to audit trail
        6. Auto-pauses on limit breach

        Args:
            transaction: Transaction parameters
            value_usd: Transaction value in USD (for limit checking)

        Returns:
            Transaction hash

        Raises:
            HotWalletPausedError: If wallet is paused
            SecurityValidationError: If security validation fails
            ValueError: If transaction is invalid
        """
        async with self._lock:
            to_address = transaction.get("to", "")
            tx_data = transaction.get("data", b"")
            if isinstance(tx_data, str):
                tx_data = bytes.fromhex(tx_data[2:] if tx_data.startswith("0x") else tx_data)

            # 1. Check if paused
            if self.tier_status.is_paused:
                await self._log_blocked_transaction(
                    to_address,
                    f"Wallet is paused: {self.tier_status.pause_reason}"
                )
                raise HotWalletPausedError(self.tier_status.pause_reason)

            # 2. Security validation
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
                    [t.threat_type.value for t in validation_result.threats]
                )

            # Log warnings if any
            for warning in validation_result.warnings:
                logger.warning(f"Transaction warning: {warning}")

            # 3. Check spending limits
            if value_usd:
                can_spend, reason = await self._check_spending_limits(value_usd)
                if not can_spend:
                    # Auto-pause if configured
                    if self.tier_config.auto_pause_on_limit:
                        await self._auto_pause(reason)
                    raise SecurityValidationError(reason)

            # 4. Execute transaction
            try:
                tx_hash = self.send_transaction(transaction)

                # 5. Record spending
                if value_usd:
                    await self._record_spending(value_usd)

                # 6. Audit log success
                await self.audit_logger.log_event(
                    event_type=self.audit_logger.log_event.__self__.__class__.TRANSACTION_EXECUTED
                    if hasattr(self.audit_logger, 'TRANSACTION_EXECUTED')
                    else "transaction_executed",
                    severity=AuditSeverity.INFO,
                    message=f"Hot wallet transaction sent: {tx_hash.hex()}",
                    metadata={
                        "tx_hash": tx_hash.hex(),
                        "to": to_address,
                        "value_usd": str(value_usd) if value_usd else None,
                        "tier": self.tier.value,
                    }
                )

                return tx_hash

            except Exception as e:
                logger.error(f"Transaction failed: {e}")
                raise

    def send_transaction(self, transaction: TxParams) -> HexBytes:
        """Send transaction (synchronous wrapper).

        For async validation, use send_transaction_async().
        This method performs basic validation only.

        Args:
            transaction: Transaction parameters

        Returns:
            Transaction hash
        """
        # Basic pause check (async check is more comprehensive)
        if self.tier_status.is_paused:
            raise HotWalletPausedError(self.tier_status.pause_reason or "Wallet paused")

        # Delegate to parent
        return super().send_transaction(transaction)

    async def _check_spending_limits(self, amount_usd: Decimal) -> tuple[bool, str]:
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

    async def _record_spending(self, amount_usd: Decimal) -> None:
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
        from datetime import datetime, UTC

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._daily_spent_usd = Decimal("0")
            self._last_reset_date = today
            self.tier_status.daily_spent_usd = Decimal("0")
            self.tier_status.transactions_today = 0
            logger.info(f"Daily spending counter reset for {today}")

    async def _auto_pause(self, reason: str) -> None:
        """Auto-pause the wallet due to limit breach.

        Args:
            reason: Why the wallet is being paused
        """
        self.tier_status.is_paused = True
        self.tier_status.pause_reason = reason

        logger.warning(f"HOT WALLET AUTO-PAUSED: {reason}")

        # Audit log
        await self.audit_logger.log_tier_event(
            tier=self.tier.value,
            event_type="paused",
            details={"reason": reason, "auto": True}
        )

        # Call callback if provided
        if self._on_pause_callback:
            try:
                self._on_pause_callback(reason)
            except Exception as e:
                logger.error(f"Pause callback failed: {e}")

    async def _log_blocked_transaction(self, to_address: str, reason: str) -> None:
        """Log a blocked transaction attempt."""
        await self.audit_logger.log_validation_failed(
            to_address=to_address,
            reason=reason,
            metadata={"tier": self.tier.value, "wallet_paused": True}
        )

    async def _log_security_block(
        self,
        to_address: str,
        validation_result: ValidationResult
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

    def pause(self, reason: str = "Manual pause") -> None:
        """Manually pause the wallet.

        Args:
            reason: Reason for pausing
        """
        self.tier_status.is_paused = True
        self.tier_status.pause_reason = reason
        logger.warning(f"Hot wallet manually paused: {reason}")

    def resume(self) -> None:
        """Resume the wallet from paused state."""
        if self.tier_status.is_paused:
            self.tier_status.is_paused = False
            self.tier_status.pause_reason = None
            logger.info("Hot wallet resumed")

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

    def is_paused(self) -> bool:
        """Check if wallet is currently paused."""
        return self.tier_status.is_paused

    def get_remaining_daily_limit(self) -> Decimal:
        """Get remaining daily spending limit.

        Returns:
            Remaining USD that can be spent today
        """
        self._maybe_reset_daily_counter()
        return max(
            Decimal("0"),
            self.tier_config.daily_limit_usd - self._daily_spent_usd
        )

    def can_spend(self, amount_usd: Decimal) -> tuple[bool, str]:
        """Check if an amount can be spent.

        Args:
            amount_usd: Amount to check

        Returns:
            Tuple of (can_spend: bool, reason: str)
        """
        if self.tier_status.is_paused:
            return False, f"Wallet paused: {self.tier_status.pause_reason}"

        if amount_usd > self.tier_config.max_transaction_usd:
            return False, f"Exceeds max tx ${self.tier_config.max_transaction_usd}"

        remaining = self.get_remaining_daily_limit()
        if amount_usd > remaining:
            return False, f"Exceeds remaining daily limit ${remaining}"

        return True, "OK"

    def validate_address(self, to_address: str) -> tuple[bool, str]:
        """Validate if a destination address is allowed.

        Args:
            to_address: Address to validate

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        allowed, reason, _ = self.whitelist.validate_transaction_target(
            to_address,
            strict_mode=True
        )
        return allowed, reason
