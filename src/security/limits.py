"""Spending limit enforcement for transaction safety.

This module implements multi-layered spending limits to prevent
unauthorized or excessive transactions.

Supports both legacy flat config dicts and TierConfig objects for
tier-aware limit enforcement.
"""

from typing import Any, Callable, Dict, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from enum import Enum
import asyncio

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Optional import for TierConfig (avoid circular imports)
try:
    from src.wallet.tiered_config import TierConfig, WalletTier
except ImportError:
    TierConfig = None  # type: ignore
    WalletTier = None  # type: ignore


class LimitType(Enum):
    """Types of spending limits."""

    PER_TRANSACTION = "per_transaction"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class SpendingLimits:
    """Enforces spending limits at multiple levels.

    Tracks spending over different time periods and enforces
    maximum transaction values for safety.

    Attributes:
        max_transaction_usd: Maximum single transaction value
        daily_limit_usd: Maximum daily spending
        weekly_limit_usd: Maximum weekly spending
        monthly_limit_usd: Maximum monthly spending
        spending_history: Transaction history for limit tracking
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        tier_config: Optional["TierConfig"] = None,
        auto_pause_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize spending limits.

        Supports both legacy flat config dict and TierConfig for tier-aware limits.

        Args:
            config: Legacy flat config dict (deprecated, use tier_config)
            tier_config: TierConfig with tier-specific limits (preferred)
            auto_pause_callback: Called when limits are breached (for hot wallet auto-pause)

        Raises:
            ValueError: If neither config nor tier_config is provided
        """
        if tier_config is not None:
            # Use TierConfig (preferred approach)
            self.max_transaction_usd = tier_config.max_transaction_usd
            self.daily_limit_usd = tier_config.daily_limit_usd
            self.weekly_limit_usd = tier_config.weekly_limit_usd or Decimal("999999999")
            self.monthly_limit_usd = tier_config.monthly_limit_usd or Decimal("999999999")
            self.tier = tier_config.tier if hasattr(tier_config, 'tier') else None
            logger.info(
                f"SpendingLimits initialized from TierConfig",
                extra={
                    "tier": self.tier.value if self.tier else "unknown",
                    "max_tx": str(self.max_transaction_usd),
                    "daily": str(self.daily_limit_usd),
                    "weekly": str(self.weekly_limit_usd),
                }
            )
        elif config is not None:
            # Legacy config dict (backward compatibility)
            self.max_transaction_usd = Decimal(config.get("max_transaction_value_usd", "1000"))
            self.daily_limit_usd = Decimal(config.get("daily_spending_limit_usd", "5000"))
            self.weekly_limit_usd = Decimal(config.get("weekly_spending_limit_usd", "20000"))
            self.monthly_limit_usd = Decimal(config.get("monthly_spending_limit_usd", "50000"))
            self.tier = None
        else:
            raise ValueError("Must provide either config or tier_config")

        self.spending_history: list[tuple[datetime, Decimal]] = []

        # CRITICAL: Lock for preventing race conditions in concurrent transactions
        self._lock = asyncio.Lock()

        # Optional callback for auto-pause on limit breach
        self._auto_pause_callback = auto_pause_callback

    def check_transaction_limit(self, amount_usd: Decimal) -> bool:
        """Check if transaction is within single transaction limit.

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            True if within limit, False otherwise
        """
        return amount_usd <= self.max_transaction_usd

    def check_daily_limit(self, amount_usd: Decimal) -> bool:
        """Check if transaction would exceed daily limit.

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            True if within limit, False otherwise
        """
        # Calculate spending in last 24 hours
        now = datetime.now()
        yesterday = now - timedelta(days=1)

        daily_spending = sum(
            amount for timestamp, amount in self.spending_history
            if timestamp >= yesterday
        )

        total_with_transaction = daily_spending + amount_usd
        return total_with_transaction <= self.daily_limit_usd

    def check_weekly_limit(self, amount_usd: Decimal) -> bool:
        """Check if transaction would exceed weekly limit.

        Uses a 7-day rolling window from current time.

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            True if within limit, False otherwise
        """
        now = datetime.now()
        week_ago = now - timedelta(days=7)

        weekly_spending = sum(
            amount for timestamp, amount in self.spending_history
            if timestamp >= week_ago
        )

        total_with_transaction = weekly_spending + amount_usd
        return total_with_transaction <= self.weekly_limit_usd

    def check_monthly_limit(self, amount_usd: Decimal) -> bool:
        """Check if transaction would exceed monthly limit.

        Uses a 30-day rolling window from current time.

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            True if within limit, False otherwise
        """
        now = datetime.now()
        month_ago = now - timedelta(days=30)

        monthly_spending = sum(
            amount for timestamp, amount in self.spending_history
            if timestamp >= month_ago
        )

        total_with_transaction = monthly_spending + amount_usd
        return total_with_transaction <= self.monthly_limit_usd

    def check_all_limits(self, amount_usd: Decimal) -> tuple[bool, str]:
        """Check all spending limits comprehensively.

        Checks in order: per-transaction, daily, weekly, monthly.
        Returns on first failure with specific reason.

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            Tuple of (is_allowed: bool, reason: str)
            - (True, "") if all limits pass
            - (False, reason) if any limit exceeded
        """
        now = datetime.now()

        # 1. Per-transaction limit
        if not self.check_transaction_limit(amount_usd):
            return (
                False,
                f"Exceeds per-transaction limit: ${amount_usd} > ${self.max_transaction_usd}"
            )

        # 2. Daily limit (24-hour rolling window)
        if not self.check_daily_limit(amount_usd):
            yesterday = now - timedelta(days=1)
            daily_spending = sum(
                amount for timestamp, amount in self.spending_history
                if timestamp >= yesterday
            )
            return (
                False,
                f"Exceeds daily limit: ${daily_spending} + ${amount_usd} > ${self.daily_limit_usd}"
            )

        # 3. Weekly limit (7-day rolling window)
        if not self.check_weekly_limit(amount_usd):
            week_ago = now - timedelta(days=7)
            weekly_spending = sum(
                amount for timestamp, amount in self.spending_history
                if timestamp >= week_ago
            )
            return (
                False,
                f"Exceeds weekly limit: ${weekly_spending} + ${amount_usd} > ${self.weekly_limit_usd}"
            )

        # 4. Monthly limit (30-day rolling window)
        if not self.check_monthly_limit(amount_usd):
            month_ago = now - timedelta(days=30)
            monthly_spending = sum(
                amount for timestamp, amount in self.spending_history
                if timestamp >= month_ago
            )
            return (
                False,
                f"Exceeds monthly limit: ${monthly_spending} + ${amount_usd} > ${self.monthly_limit_usd}"
            )

        return (True, "")

    def record_transaction(self, amount_usd: Decimal) -> None:
        """Record a transaction for limit tracking.

        Args:
            amount_usd: Transaction amount in USD
        """
        self.spending_history.append((datetime.now(), amount_usd))

        # Clean old entries (older than monthly tracking period)
        self.cleanup_old_history()

    def get_spending_summary(self) -> Dict[str, Decimal]:
        """Get spending summary for different time periods.

        Calculates spending and remaining limits for daily, weekly, and monthly periods.

        Returns:
            Dict with spending summary:
            - daily_spent, daily_limit, daily_remaining
            - weekly_spent, weekly_limit, weekly_remaining
            - monthly_spent, monthly_limit, monthly_remaining
            - max_transaction
        """
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        daily_spending = sum(
            amount for timestamp, amount in self.spending_history
            if timestamp >= yesterday
        )

        weekly_spending = sum(
            amount for timestamp, amount in self.spending_history
            if timestamp >= week_ago
        )

        monthly_spending = sum(
            amount for timestamp, amount in self.spending_history
            if timestamp >= month_ago
        )

        return {
            "max_transaction": self.max_transaction_usd,
            "daily_spent": daily_spending,
            "daily_limit": self.daily_limit_usd,
            "daily_remaining": max(Decimal("0"), self.daily_limit_usd - daily_spending),
            "weekly_spent": weekly_spending,
            "weekly_limit": self.weekly_limit_usd,
            "weekly_remaining": max(Decimal("0"), self.weekly_limit_usd - weekly_spending),
            "monthly_spent": monthly_spending,
            "monthly_limit": self.monthly_limit_usd,
            "monthly_remaining": max(Decimal("0"), self.monthly_limit_usd - monthly_spending),
        }

    def cleanup_old_history(self) -> None:
        """Remove transaction history older than monthly period."""
        cutoff = datetime.now() - timedelta(days=30)
        self.spending_history = [
            (ts, amt) for ts, amt in self.spending_history if ts > cutoff
        ]

    async def atomic_check_and_record(self, amount_usd: Decimal) -> tuple[bool, str]:
        """Atomically check ALL limits and record transaction (prevents race conditions).

        This method uses a lock to ensure that checking limits and recording
        the transaction happens atomically. This prevents race conditions where
        multiple concurrent transactions could exceed spending limits.

        Now checks: per-transaction, daily, weekly, and monthly limits.
        Triggers auto_pause_callback if limit is breached (for hot wallet auto-pause).

        Example race condition this prevents:
            T0: Thread A checks limits → $800/$1000 used ✅
            T1: Thread B checks limits → $800/$1000 used ✅
            T2: Thread A records $300 → $1100/$1000 used ❌ OVER LIMIT
            T3: Thread B records $300 → $1400/$1000 used ❌ WAY OVER

        With atomic_check_and_record:
            T0: Thread A acquires lock
            T1: Thread A checks + records → $1100/$1000 ✅ or ❌ (one check)
            T2: Thread A releases lock
            T3: Thread B acquires lock
            T4: Thread B checks → $1100/$1000 ❌ REJECTED

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            Tuple of (is_allowed: bool, reason: str)
            - (True, "") if transaction allowed and recorded
            - (False, reason) if transaction rejected
        """
        async with self._lock:
            # Check ALL limits comprehensively (per-tx, daily, weekly, monthly)
            is_allowed, reason = self.check_all_limits(amount_usd)

            if not is_allowed:
                # Trigger auto-pause callback if configured (for hot wallet)
                if self._auto_pause_callback:
                    try:
                        logger.warning(
                            f"Spending limit breached, triggering auto-pause: {reason}"
                        )
                        self._auto_pause_callback(reason)
                    except Exception as e:
                        logger.error(f"Auto-pause callback failed: {e}")

                return (False, reason)

            # All checks passed - record transaction
            self.record_transaction(amount_usd)
            return (True, "")
