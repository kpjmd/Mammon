"""Tiered wallet configuration for MAMMON security architecture.

Defines three wallet tiers with different security levels:
- HOT: Autonomous operations with strict limits ($500/tx, $1000/day)
- WARM: Manual approval required via web dashboard ($5000/tx)
- COLD: Hardware wallet (Ledger) - manual only (future)

Security Note: Seed phrases should NEVER be stored in filesystem.
Use environment variable injection at runtime.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional
import os


class WalletTier(Enum):
    """Wallet security tiers."""

    HOT = "hot"      # Tier 1: Autonomous, strict limits
    WARM = "warm"    # Tier 2: Requires manual approval
    COLD = "cold"    # Tier 3: Hardware wallet (Ledger)


class RiskLevel(Enum):
    """Risk levels for contracts and operations."""

    LOW = "low"           # Well-known, audited contracts
    MEDIUM = "medium"     # Less established but verified
    HIGH = "high"         # New or complex contracts
    CRITICAL = "critical" # Requires extra scrutiny


@dataclass
class TierConfig:
    """Configuration for a specific wallet tier.

    Attributes:
        tier: The wallet tier this config applies to
        max_balance_usd: Maximum allowed balance in this wallet
        max_transaction_usd: Maximum single transaction value
        daily_limit_usd: Maximum daily spending
        weekly_limit_usd: Maximum weekly spending (optional)
        monthly_limit_usd: Maximum monthly spending (optional)
        requires_approval: Whether transactions need manual approval
        approval_timeout_hours: How long to wait for approval
        auto_pause_on_limit: Automatically pause wallet when limits hit
        allowed_risk_levels: Which contract risk levels are allowed
    """

    tier: WalletTier
    max_balance_usd: Decimal
    max_transaction_usd: Decimal
    daily_limit_usd: Decimal
    weekly_limit_usd: Optional[Decimal] = None
    monthly_limit_usd: Optional[Decimal] = None
    requires_approval: bool = False
    approval_timeout_hours: int = 24
    auto_pause_on_limit: bool = True
    allowed_risk_levels: tuple = field(default_factory=lambda: (RiskLevel.LOW, RiskLevel.MEDIUM))

    def __post_init__(self):
        """Validate configuration values."""
        if self.max_transaction_usd > self.daily_limit_usd:
            raise ValueError(
                f"max_transaction_usd ({self.max_transaction_usd}) cannot exceed "
                f"daily_limit_usd ({self.daily_limit_usd})"
            )
        if self.max_balance_usd < self.daily_limit_usd:
            # Warning but not error - balance can be less than daily limit
            pass


# Default tier configurations
DEFAULT_HOT_CONFIG = TierConfig(
    tier=WalletTier.HOT,
    max_balance_usd=Decimal("2000"),
    max_transaction_usd=Decimal("500"),
    daily_limit_usd=Decimal("1000"),
    weekly_limit_usd=Decimal("5000"),
    monthly_limit_usd=Decimal("15000"),
    requires_approval=False,
    approval_timeout_hours=0,  # No approval needed
    auto_pause_on_limit=True,
    allowed_risk_levels=(RiskLevel.LOW,),  # Only low-risk contracts
)

DEFAULT_WARM_CONFIG = TierConfig(
    tier=WalletTier.WARM,
    max_balance_usd=Decimal("50000"),
    max_transaction_usd=Decimal("5000"),
    daily_limit_usd=Decimal("10000"),
    weekly_limit_usd=Decimal("30000"),
    monthly_limit_usd=Decimal("100000"),
    requires_approval=True,
    approval_timeout_hours=24,
    auto_pause_on_limit=False,
    allowed_risk_levels=(RiskLevel.LOW, RiskLevel.MEDIUM),
)

DEFAULT_COLD_CONFIG = TierConfig(
    tier=WalletTier.COLD,
    max_balance_usd=Decimal("999999999"),  # Unlimited
    max_transaction_usd=Decimal("999999999"),
    daily_limit_usd=Decimal("999999999"),
    requires_approval=True,
    approval_timeout_hours=168,  # 1 week
    auto_pause_on_limit=False,
    allowed_risk_levels=(RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH),
)


@dataclass
class TierStatus:
    """Current status of a wallet tier.

    Attributes:
        tier: The wallet tier
        is_paused: Whether the wallet is currently paused
        current_balance_usd: Current balance in USD
        daily_spent_usd: Amount spent today
        weekly_spent_usd: Amount spent this week
        monthly_spent_usd: Amount spent this month
        transactions_today: Number of transactions today
        last_transaction_at: Timestamp of last transaction
        pause_reason: Reason for pause if paused
    """

    tier: WalletTier
    is_paused: bool = False
    current_balance_usd: Decimal = Decimal("0")
    daily_spent_usd: Decimal = Decimal("0")
    weekly_spent_usd: Decimal = Decimal("0")
    monthly_spent_usd: Decimal = Decimal("0")
    transactions_today: int = 0
    last_transaction_at: Optional[str] = None
    pause_reason: Optional[str] = None

    def can_transact(self, amount_usd: Decimal, config: TierConfig) -> tuple[bool, str]:
        """Check if a transaction of given amount is allowed.

        Args:
            amount_usd: Transaction amount in USD
            config: Tier configuration to check against

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        if self.is_paused:
            return False, f"Wallet is paused: {self.pause_reason or 'Unknown reason'}"

        if amount_usd > config.max_transaction_usd:
            return False, f"Amount ${amount_usd} exceeds max transaction ${config.max_transaction_usd}"

        new_daily_total = self.daily_spent_usd + amount_usd
        if new_daily_total > config.daily_limit_usd:
            return False, f"Would exceed daily limit: ${new_daily_total} > ${config.daily_limit_usd}"

        if config.weekly_limit_usd:
            new_weekly_total = self.weekly_spent_usd + amount_usd
            if new_weekly_total > config.weekly_limit_usd:
                return False, f"Would exceed weekly limit: ${new_weekly_total} > ${config.weekly_limit_usd}"

        if config.monthly_limit_usd:
            new_monthly_total = self.monthly_spent_usd + amount_usd
            if new_monthly_total > config.monthly_limit_usd:
                return False, f"Would exceed monthly limit: ${new_monthly_total} > ${config.monthly_limit_usd}"

        return True, "Transaction allowed"


class TieredWalletConfig:
    """Manager for tiered wallet configurations.

    Loads configuration from environment variables or uses defaults.
    """

    def __init__(self):
        """Initialize with default configurations."""
        self._configs: Dict[WalletTier, TierConfig] = {
            WalletTier.HOT: DEFAULT_HOT_CONFIG,
            WalletTier.WARM: DEFAULT_WARM_CONFIG,
            WalletTier.COLD: DEFAULT_COLD_CONFIG,
        }
        self._load_from_env()

    def _load_from_env(self) -> None:
        """Load tier-specific settings from environment variables."""
        # Hot wallet overrides
        if hot_max_balance := os.getenv("HOT_WALLET_MAX_BALANCE_USD"):
            self._configs[WalletTier.HOT] = TierConfig(
                tier=WalletTier.HOT,
                max_balance_usd=Decimal(hot_max_balance),
                max_transaction_usd=Decimal(os.getenv("HOT_WALLET_MAX_TRANSACTION_USD", "500")),
                daily_limit_usd=Decimal(os.getenv("HOT_WALLET_DAILY_LIMIT_USD", "1000")),
                weekly_limit_usd=Decimal(os.getenv("HOT_WALLET_WEEKLY_LIMIT_USD", "5000")) if os.getenv("HOT_WALLET_WEEKLY_LIMIT_USD") else None,
                monthly_limit_usd=Decimal(os.getenv("HOT_WALLET_MONTHLY_LIMIT_USD", "15000")) if os.getenv("HOT_WALLET_MONTHLY_LIMIT_USD") else None,
                requires_approval=False,
                approval_timeout_hours=0,
                auto_pause_on_limit=os.getenv("HOT_WALLET_AUTO_PAUSE", "true").lower() == "true",
                allowed_risk_levels=(RiskLevel.LOW,),
            )

        # Warm wallet overrides
        if warm_max_tx := os.getenv("WARM_WALLET_MAX_TRANSACTION_USD"):
            self._configs[WalletTier.WARM] = TierConfig(
                tier=WalletTier.WARM,
                max_balance_usd=Decimal(os.getenv("WARM_WALLET_MAX_BALANCE_USD", "50000")),
                max_transaction_usd=Decimal(warm_max_tx),
                daily_limit_usd=Decimal(os.getenv("WARM_WALLET_DAILY_LIMIT_USD", "10000")),
                requires_approval=True,
                approval_timeout_hours=int(os.getenv("WARM_WALLET_APPROVAL_TIMEOUT_HOURS", "24")),
                auto_pause_on_limit=False,
                allowed_risk_levels=(RiskLevel.LOW, RiskLevel.MEDIUM),
            )

    def get_config(self, tier: WalletTier) -> TierConfig:
        """Get configuration for a specific tier.

        Args:
            tier: The wallet tier

        Returns:
            TierConfig for the specified tier
        """
        return self._configs[tier]

    def get_tier_for_amount(self, amount_usd: Decimal) -> WalletTier:
        """Determine which tier should handle a transaction of given amount.

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            Appropriate WalletTier for the amount
        """
        hot_config = self._configs[WalletTier.HOT]
        warm_config = self._configs[WalletTier.WARM]

        if amount_usd <= hot_config.max_transaction_usd:
            return WalletTier.HOT
        elif amount_usd <= warm_config.max_transaction_usd:
            return WalletTier.WARM
        else:
            return WalletTier.COLD

    def validate_tier_for_amount(
        self,
        tier: WalletTier,
        amount_usd: Decimal,
        status: Optional[TierStatus] = None
    ) -> tuple[bool, str]:
        """Validate if a tier can handle a transaction amount.

        Args:
            tier: The wallet tier to validate
            amount_usd: Transaction amount in USD
            status: Optional current tier status for daily/weekly limits

        Returns:
            Tuple of (valid: bool, reason: str)
        """
        config = self._configs[tier]

        if amount_usd > config.max_transaction_usd:
            return False, f"Amount ${amount_usd} exceeds {tier.value} wallet max of ${config.max_transaction_usd}"

        if status:
            return status.can_transact(amount_usd, config)

        return True, "Transaction allowed"


def get_tiered_config() -> TieredWalletConfig:
    """Get the global tiered wallet configuration.

    Returns:
        TieredWalletConfig instance
    """
    return TieredWalletConfig()
