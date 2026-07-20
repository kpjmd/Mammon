"""Tests for PositionTracker close/read behavior.

Regression coverage for two bugs found during the WS7 custody migration:

1. close_position crashed when a position was closed at $0 value (a drained or
   fully-exited position) because the ROI log line formatted None, and its ROI
   calc read the entry value AFTER overwriting it (always yielding 0).
2. get_current_positions is the read that feeds rebalance decisions. When
   called without a wallet filter it returns positions for EVERY wallet, so a
   stale row for an old/other wallet would drive a real withdraw attempt on the
   current wallet.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.data.models import Position
from src.data.position_tracker import PositionTracker

WALLET_A = "0xAAAA000000000000000000000000000000000001"
WALLET_B = "0xBBBB000000000000000000000000000000000002"


@pytest.fixture
def tracker(tmp_path):
    """A PositionTracker backed by a throwaway on-disk SQLite db."""
    db = tmp_path / "test_positions.db"
    pt = PositionTracker(str(db))
    yield pt
    pt.session.close()


def _insert(
    tracker,
    *,
    wallet,
    protocol="Moonwell",
    token="USDC",
    amount="100",
    value_usd="100",
    entry_apy="5",
    status="active",
):
    """Insert a Position row directly and return its id."""
    pos = Position(
        wallet_address=wallet,
        protocol=protocol,
        pool_id=f"{protocol.lower()}-{token.lower()}",
        token=token,
        amount=Decimal(amount),
        value_usd=Decimal(value_usd),
        entry_apy=Decimal(entry_apy),
        current_apy=Decimal(entry_apy),
        status=status,
        # Normally set by record_position; a raw insert must supply it so the
        # days_held computation in close_position has a start point.
        opened_at=datetime.utcnow() - timedelta(days=2),
    )
    tracker.session.add(pos)
    tracker.session.commit()
    return pos.id


class TestCloseAtZeroValue:
    """A position closed at $0 must not crash and must record -100%."""

    def test_close_drained_position_does_not_crash(self, tracker):
        """Regression: closing at $0 previously raised TypeError on the log."""
        pid = _insert(tracker, wallet=WALLET_A, value_usd="200")

        result = asyncio.run(tracker.close_position(position_id=pid, actual_value_usd=Decimal("0")))

        assert result["final_value_usd"] == Decimal("0")
        # 200 -> 0 is a real -100% close, not an undefined ROI.
        assert result["actual_roi"] == Decimal("-100")

    def test_close_marks_row_closed(self, tracker):
        """The row is actually persisted as closed at its final value."""
        pid = _insert(tracker, wallet=WALLET_A, value_usd="200")

        asyncio.run(tracker.close_position(position_id=pid, actual_value_usd=Decimal("0")))

        row = tracker.session.query(Position).get(pid)
        assert row.status == "closed"
        assert row.value_usd == Decimal("0")
        assert row.closed_at is not None

    def test_roi_uses_entry_not_final_value(self, tracker):
        """Regression: ROI must be computed against the ENTRY value.

        Previously value_usd was overwritten before the calc read it, so ROI
        was always 0. A $100 -> $150 close must report +50%.
        """
        pid = _insert(tracker, wallet=WALLET_A, value_usd="100")

        result = asyncio.run(
            tracker.close_position(position_id=pid, actual_value_usd=Decimal("150"))
        )

        assert result["entry_value_usd"] == Decimal("100")
        assert result["actual_roi"] == Decimal("50")

    def test_explicit_roi_is_respected(self, tracker):
        """A caller-supplied ROI is not overwritten by the calc."""
        pid = _insert(tracker, wallet=WALLET_A, value_usd="100")

        result = asyncio.run(
            tracker.close_position(
                position_id=pid,
                actual_value_usd=Decimal("0"),
                actual_roi=Decimal("-12.5"),
            )
        )

        assert result["actual_roi"] == Decimal("-12.5")


class TestWalletFilter:
    """get_current_positions must be able to scope to one wallet."""

    def test_filters_to_requested_wallet(self, tracker):
        """Only the requested wallet's active positions are returned."""
        _insert(tracker, wallet=WALLET_A, protocol="Moonwell")
        _insert(tracker, wallet=WALLET_B, protocol="Aave V3")

        result = asyncio.run(tracker.get_current_positions(wallet_address=WALLET_A))

        assert len(result) == 1
        assert result[0].wallet_address == WALLET_A
        assert result[0].protocol == "Moonwell"

    def test_no_filter_returns_all_wallets(self, tracker):
        """Documents the unfiltered behavior the caller must NOT rely on.

        This is exactly why scheduled_optimizer passes the current wallet: an
        unfiltered read mixes wallets.
        """
        _insert(tracker, wallet=WALLET_A)
        _insert(tracker, wallet=WALLET_B)

        result = asyncio.run(tracker.get_current_positions())

        assert len(result) == 2

    def test_closed_positions_excluded(self, tracker):
        """Only active rows are returned, even for the right wallet."""
        _insert(tracker, wallet=WALLET_A, status="active")
        _insert(tracker, wallet=WALLET_A, status="closed")

        result = asyncio.run(tracker.get_current_positions(wallet_address=WALLET_A))

        assert len(result) == 1

    def test_other_wallet_positions_never_leak(self, tracker):
        """The core WS7 safety property: an old wallet's rows are invisible."""
        _insert(tracker, wallet=WALLET_B, value_usd="200")

        result = asyncio.run(tracker.get_current_positions(wallet_address=WALLET_A))

        assert result == []
