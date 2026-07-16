"""Unit tests for WalletManager auto-pause (WS2).

Verifies that a cumulative spending-limit breach latches the wallet, that a
paused wallet blocks execution until an explicit resume, and that disabling
auto-pause reverts to plain gating (breach still rejected, wallet not latched).
"""

from decimal import Decimal

import pytest

from src.blockchain.wallet import WalletManager, WalletPausedError


@pytest.fixture(autouse=True)
def _no_pause_notifications(monkeypatch):
    """Stub the fire-and-forget audit/alert dispatch.

    These tests exercise the pause *latch*, not notification I/O; stubbing the
    scheduler keeps them free of audit-log writes and stray un-awaited tasks.
    """
    monkeypatch.setattr(WalletManager, "_schedule_pause_notifications", lambda self, reason: None)


def _config(**overrides):
    cfg = {
        "use_local_wallet": True,
        "network": "base-sepolia",
        "dry_run_mode": False,
        "max_transaction_value_usd": "100",
        "daily_spending_limit_usd": "200",
        "weekly_spending_limit_usd": "1000",
        "monthly_spending_limit_usd": "5000",
        "wallet_auto_pause": True,
    }
    cfg.update(overrides)
    return cfg


class TestPauseWiring:
    def test_callback_wired_when_enabled(self):
        wm = WalletManager(_config())
        assert wm.spending_limits._auto_pause_callback == wm._on_limit_breach

    def test_callback_not_wired_when_disabled(self):
        wm = WalletManager(_config(wallet_auto_pause=False))
        assert wm.spending_limits._auto_pause_callback is None


class TestLatchAndResume:
    def test_on_limit_breach_latches(self):
        wm = WalletManager(_config())
        assert not wm.is_paused()
        wm._on_limit_breach("daily limit reached")
        assert wm.is_paused()
        assert "daily limit" in wm._pause_reason

    def test_latch_is_idempotent_keeps_first_reason(self):
        wm = WalletManager(_config())
        wm._on_limit_breach("first")
        wm._on_limit_breach("second")
        assert wm._pause_reason == "first"

    async def test_resume_clears_latch(self):
        wm = WalletManager(_config())
        wm._on_limit_breach("breach")
        assert wm.is_paused()
        await wm.resume()
        assert not wm.is_paused()
        assert wm._pause_reason is None


class TestExecutionGate:
    async def test_paused_wallet_blocks_execution(self):
        wm = WalletManager(_config())
        wm._paused = True
        wm._pause_reason = "limit breach"
        # dry_run is False, so execution proceeds past the dry-run guard and hits
        # the pause gate before any provider/network interaction.
        with pytest.raises(WalletPausedError):
            await wm.execute_transaction(
                to="0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
                amount=Decimal("1"),
                token="USDC",
            )


class TestCumulativeBreachBehavior:
    async def test_daily_breach_latches_when_enabled(self):
        wm = WalletManager(_config())
        # Amount within per-tx ($100) but over daily ($200): first spend 150...
        wm.spending_limits.record_transaction(Decimal("150"))
        allowed = await wm._check_spending_limits(Decimal("90"))  # 150+90 > 200
        assert allowed is False
        assert wm.is_paused()

    async def test_daily_breach_gates_without_latch_when_disabled(self):
        wm = WalletManager(_config(wallet_auto_pause=False))
        wm.spending_limits.record_transaction(Decimal("150"))
        allowed = await wm._check_spending_limits(Decimal("90"))
        assert allowed is False
        assert not wm.is_paused()  # rejected, but wallet not latched

    async def test_oversized_single_tx_gates_without_latch(self):
        wm = WalletManager(_config())
        # Over per-tx limit ($100) but no cumulative breach -> gate only.
        allowed = await wm._check_spending_limits(Decimal("150"))
        assert allowed is False
        assert not wm.is_paused()
