"""Spending limit enforcement for transaction safety.

This module implements multi-layered spending limits to prevent
unauthorized or excessive transactions.
"""

from typing import Any, Dict
from decimal import Decimal
from datetime import datetime, timedelta
from enum import Enum
import asyncio


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

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize spending limits.

        Args:
            config: Limit configuration
        """
        self.max_transaction_usd = Decimal(config.get("max_transaction_value_usd", "1000"))
        self.daily_limit_usd = Decimal(config.get("daily_spending_limit_usd", "5000"))
        self.weekly_limit_usd = Decimal(config.get("weekly_spending_limit_usd", "20000"))
        self.monthly_limit_usd = Decimal(config.get("monthly_spending_limit_usd", "50000"))
        self.spending_history: list[tuple[datetime, Decimal]] = []

        # CRITICAL: Lock for preventing race conditions in concurrent transactions
        self._lock = asyncio.Lock()

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

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            True if within limit, False otherwise
        """
        raise NotImplementedError("Weekly limit check not yet implemented")

    def check_all_limits(self, amount_usd: Decimal) -> tuple[bool, str]:
        """Check all spending limits.

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            Tuple of (is_allowed, reason)
        """
        raise NotImplementedError("Comprehensive limit check not yet implemented")

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

        Returns:
            Dict with spending by period
        """
        raise NotImplementedError("Spending summary not yet implemented")

    def cleanup_old_history(self) -> None:
        """Remove transaction history older than monthly period."""
        cutoff = datetime.now() - timedelta(days=30)
        self.spending_history = [
            (ts, amt) for ts, amt in self.spending_history if ts > cutoff
        ]

    async def atomic_check_and_record(self, amount_usd: Decimal) -> tuple[bool, str]:
        """Atomically check limits and record transaction (prevents race conditions).

        This method uses a lock to ensure that checking limits and recording
        the transaction happens atomically. This prevents race conditions where
        multiple concurrent transactions could exceed spending limits.

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
            # Check per-transaction limit
            if not self.check_transaction_limit(amount_usd):
                return (
                    False,
                    f"Transaction amount ${amount_usd} exceeds per-transaction "
                    f"limit of ${self.max_transaction_usd}",
                )

            # Check daily limit
            if not self.check_daily_limit(amount_usd):
                # Calculate current daily spending for error message
                now = datetime.now()
                yesterday = now - timedelta(days=1)
                daily_spending = sum(
                    amount
                    for timestamp, amount in self.spending_history
                    if timestamp >= yesterday
                )
                return (
                    False,
                    f"Transaction would exceed daily limit: ${daily_spending} + "
                    f"${amount_usd} > ${self.daily_limit_usd}",
                )

            # All checks passed - record transaction
            self.record_transaction(amount_usd)
            return (True, "")
