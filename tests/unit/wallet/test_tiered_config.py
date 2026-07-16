"""Unit tests for tiered wallet configuration.

The tiered providers themselves are parked pending the CDP MPC custody
migration, but ``tiered_config`` remains imported by the transaction validator,
spending limits, and the approval server, so its invariants are load-bearing.

Includes a documentation test for the two-distinct-``RiskLevel``-enums pitfall
that previously produced a dead cross-enum check in the validator.
"""

from decimal import Decimal

import pytest

from src.wallet.tiered_config import (
    WalletTier,
    RiskLevel as TierRiskLevel,
    TierConfig,
    TierStatus,
    TieredWalletConfig,
    DEFAULT_HOT_CONFIG,
    DEFAULT_WARM_CONFIG,
    DEFAULT_COLD_CONFIG,
)
from src.security.contract_whitelist import RiskLevel as WhitelistRiskLevel


class TestTierConfigInvariant:
    def test_max_tx_exceeding_daily_raises(self):
        with pytest.raises(ValueError):
            TierConfig(
                tier=WalletTier.HOT,
                max_balance_usd=Decimal("2000"),
                max_transaction_usd=Decimal("2000"),
                daily_limit_usd=Decimal("1000"),
            )

    def test_defaults_are_valid(self):
        assert DEFAULT_HOT_CONFIG.max_transaction_usd == Decimal("500")
        assert DEFAULT_HOT_CONFIG.daily_limit_usd == Decimal("1000")
        assert DEFAULT_WARM_CONFIG.requires_approval is True
        assert DEFAULT_COLD_CONFIG.tier == WalletTier.COLD


class TestCanTransact:
    def _status(self) -> TierStatus:
        return TierStatus(tier=WalletTier.HOT)

    def test_exactly_at_max_transaction_allowed(self):
        allowed, _ = self._status().can_transact(Decimal("500"), DEFAULT_HOT_CONFIG)
        assert allowed

    def test_one_cent_over_max_transaction_denied(self):
        allowed, reason = self._status().can_transact(Decimal("500.01"), DEFAULT_HOT_CONFIG)
        assert not allowed
        assert "max transaction" in reason.lower()

    def test_daily_limit_boundary(self):
        status = TierStatus(tier=WalletTier.HOT, daily_spent_usd=Decimal("600"))
        # 600 + 400 == 1000 daily limit -> allowed.
        allowed, _ = status.can_transact(Decimal("400"), DEFAULT_HOT_CONFIG)
        assert allowed
        # 600 + 401 > 1000 -> denied.
        allowed2, reason2 = status.can_transact(Decimal("401"), DEFAULT_HOT_CONFIG)
        assert not allowed2
        assert "daily" in reason2.lower()

    def test_weekly_limit_enforced(self):
        status = TierStatus(tier=WalletTier.HOT, weekly_spent_usd=Decimal("4900"))
        allowed, reason = status.can_transact(Decimal("200"), DEFAULT_HOT_CONFIG)
        assert not allowed
        assert "weekly" in reason.lower()

    def test_paused_wallet_denies_everything(self):
        status = TierStatus(tier=WalletTier.HOT, is_paused=True, pause_reason="limit breach")
        allowed, reason = status.can_transact(Decimal("1"), DEFAULT_HOT_CONFIG)
        assert not allowed
        assert "paused" in reason.lower()


class TestLoadFromEnv:
    def test_hot_overrides_applied_when_max_balance_set(self, monkeypatch):
        monkeypatch.setenv("HOT_WALLET_MAX_BALANCE_USD", "3000")
        monkeypatch.setenv("HOT_WALLET_MAX_TRANSACTION_USD", "250")
        cfg = TieredWalletConfig().get_config(WalletTier.HOT)
        assert cfg.max_balance_usd == Decimal("3000")
        assert cfg.max_transaction_usd == Decimal("250")

    def test_hot_auto_pause_inert_without_max_balance(self, monkeypatch):
        # HOT_WALLET_AUTO_PAUSE alone does nothing: the override block is gated
        # on HOT_WALLET_MAX_BALANCE_USD being present. Asserted to document the
        # env-gating quirk that made the flag inert in deployment.
        monkeypatch.delenv("HOT_WALLET_MAX_BALANCE_USD", raising=False)
        monkeypatch.setenv("HOT_WALLET_AUTO_PAUSE", "false")
        cfg = TieredWalletConfig().get_config(WalletTier.HOT)
        # Falls back to the default config, whose auto_pause stays True.
        assert cfg.auto_pause_on_limit is True

    def test_warm_overrides_gated_on_max_tx(self, monkeypatch):
        monkeypatch.setenv("WARM_WALLET_MAX_TRANSACTION_USD", "7500")
        cfg = TieredWalletConfig().get_config(WalletTier.WARM)
        assert cfg.max_transaction_usd == Decimal("7500")


class TestGetTierForAmount:
    def test_hot_boundary(self):
        cfg = TieredWalletConfig()
        assert cfg.get_tier_for_amount(Decimal("500")) == WalletTier.HOT

    def test_warm_range(self):
        cfg = TieredWalletConfig()
        assert cfg.get_tier_for_amount(Decimal("501")) == WalletTier.WARM
        assert cfg.get_tier_for_amount(Decimal("5000")) == WalletTier.WARM

    def test_cold_above_warm(self):
        cfg = TieredWalletConfig()
        assert cfg.get_tier_for_amount(Decimal("5001")) == WalletTier.COLD


class TestRiskLevelEnumDistinction:
    """Document that tiered_config.RiskLevel and contract_whitelist.RiskLevel
    are separate enum classes whose members are never equal or interchangeable.

    A cross-enum ``in`` check therefore always fails, which is exactly the dead
    code removed from ``TransactionValidator.validate_transaction``.
    """

    def test_enums_are_distinct_classes(self):
        assert TierRiskLevel is not WhitelistRiskLevel

    def test_members_not_equal_across_enums(self):
        assert TierRiskLevel.LOW is not WhitelistRiskLevel.LOW
        assert TierRiskLevel.LOW != WhitelistRiskLevel.LOW

    def test_cross_enum_membership_is_always_false(self):
        allowed = DEFAULT_HOT_CONFIG.allowed_risk_levels  # tiered RiskLevel members
        assert WhitelistRiskLevel.LOW not in allowed
