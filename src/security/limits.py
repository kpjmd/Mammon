"""Spending limit enforcement for transaction safety.

This module implements multi-layered spending limits to prevent
unauthorized or excessive transactions.
"""

from typing import Any, Dict
from decimal import Decimal
from datetime import datetime, timedelta
from enum import Enum


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
