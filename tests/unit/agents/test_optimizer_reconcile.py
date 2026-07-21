"""Unit tests for ScheduledOptimizer.reconcile_positions.

reconcile_positions is the only writer of the `positions` table on the live
path. It reads each in-scope pool's on-chain balance, upserts a Position row for
anything the wallet actually holds, and closes any previously tracked position
the wallet no longer holds on-chain (e.g. the source side of a rebalance).

These tests use a real on-disk PositionTracker (as in
tests/unit/data/test_position_tracker.py) plus a MagicMock yield_scanner whose
protocol objects have AsyncMock get_user_balance, exercising the write path end
to end against SQLite.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.scheduled_optimizer import ScheduledOptimizer
from src.agents.yield_scanner import YieldOpportunity
from src.data.models import Position
from src.data.position_tracker import PositionTracker

WALLET = "0xAAAA000000000000000000000000000000000001"


def _opp(protocol, pool_id, token="USDC", apy="5", tokens=None):
    return YieldOpportunity(
        protocol=protocol,
        pool_id=pool_id,
        pool_name=f"{protocol} {token}",
        apy=Decimal(apy),
        tvl=Decimal("1000000"),
        tokens=tokens if tokens is not None else [token],
    )


def _proto(name, balance):
    """A protocol mock whose get_user_balance returns `balance` (Decimal or exc)."""
    p = MagicMock()
    p.name = name
    if isinstance(balance, Exception):
        p.get_user_balance = AsyncMock(side_effect=balance)
    else:
        p.get_user_balance = AsyncMock(return_value=Decimal(str(balance)))
    return p


def _make_optimizer(tmp_path, *, opportunities, protocols, dry_run=False, price="1"):
    """Build a ScheduledOptimizer wired to a real PositionTracker + mock scanner."""
    tracker = PositionTracker(str(tmp_path / "reconcile.db"))

    scanner = MagicMock()
    scanner.protocols = protocols
    scanner.scan_all_protocols = AsyncMock(return_value=opportunities)
    scanner.price_oracle = MagicMock()
    scanner.price_oracle.get_price = AsyncMock(return_value=Decimal(price))

    wallet = MagicMock()
    wallet.address = WALLET
    wallet.get_balance = AsyncMock(return_value=Decimal("0"))

    config = {
        "dry_run_mode": dry_run,
        "circuit_breaker_state_file": str(tmp_path / "breaker.json"),
        "heartbeat_file": str(tmp_path / "heartbeat.json"),
    }

    opt = ScheduledOptimizer(
        config=config,
        yield_scanner=scanner,
        optimizer=MagicMock(),
        risk_assessor=MagicMock(),
        rebalance_executor=MagicMock(),
        wallet_manager=wallet,
        profitability_calc=MagicMock(),
        audit_logger=MagicMock(),
        database=None,
        position_tracker=tracker,
    )
    opt.audit_logger.log_event = AsyncMock()
    return opt, tracker


async def _active(tracker, wallet=WALLET):
    return await tracker.get_current_positions(wallet_address=wallet)


class TestRecord:
    async def test_records_new_target(self, tmp_path):
        opp = _opp("Moonwell", "moonwell-usdc", apy="6.5")
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=[opp], protocols=[_proto("Moonwell", "100")]
        )

        await opt.reconcile_positions(["Moonwell"])

        rows = await _active(tracker)
        assert len(rows) == 1
        row = rows[0]
        assert row.protocol == "Moonwell"
        assert row.pool_id == "moonwell-usdc"
        assert row.token == "USDC"
        assert row.amount == Decimal("100")
        assert row.value_usd == Decimal("100")
        # entry_apy is set on create from current_apy (== opp.apy).
        assert row.metadata["entry_apy"] == Decimal("6.5")

    async def test_value_uses_oracle_price(self, tmp_path):
        # Non-1:1 price → value_usd = balance * price.
        opp = _opp("Aave V3", "aave-weth", token="WETH", apy="3")
        opt, tracker = _make_optimizer(
            tmp_path,
            opportunities=[opp],
            protocols=[_proto("Aave V3", "2")],
            price="1500",
        )

        await opt.reconcile_positions(["Aave V3"])

        row = (await _active(tracker))[0]
        assert row.amount == Decimal("2")
        assert row.value_usd == Decimal("3000")

    async def test_zero_balance_not_recorded(self, tmp_path):
        opp = _opp("Moonwell", "moonwell-usdc")
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=[opp], protocols=[_proto("Moonwell", "0")]
        )

        await opt.reconcile_positions(["Moonwell"])

        assert await _active(tracker) == []

    async def test_upsert_preserves_entry_apy(self, tmp_path):
        opp = _opp("Moonwell", "moonwell-usdc", apy="5")
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=[opp], protocols=[_proto("Moonwell", "100")]
        )
        await opt.reconcile_positions(["Moonwell"])

        # Second reconcile with a DIFFERENT current APY + balance: same active
        # row updated, entry_apy unchanged (captured at first record).
        opt.yield_scanner.protocols[0].get_user_balance = AsyncMock(
            return_value=Decimal("120")
        )
        opt.yield_scanner.scan_all_protocols = AsyncMock(
            return_value=[_opp("Moonwell", "moonwell-usdc", apy="9")]
        )
        await opt.reconcile_positions(["Moonwell"])

        rows = await _active(tracker)
        assert len(rows) == 1
        assert rows[0].amount == Decimal("120")
        assert rows[0].current_apy == Decimal("9")
        assert rows[0].metadata["entry_apy"] == Decimal("5")


class TestSourceClose:
    async def test_disappeared_source_closed_at_last_value(self, tmp_path):
        # Rebalance out of Aave into Moonwell: Aave balance now 0, Moonwell > 0.
        opts = [
            _opp("Aave V3", "aave-usdc"),
            _opp("Moonwell", "moonwell-usdc"),
        ]
        protos = [_proto("Aave V3", "0"), _proto("Moonwell", "50")]
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=opts, protocols=protos
        )
        # Seed an active Aave source position at $50.
        src_id = await tracker.record_position(
            wallet_address=WALLET,
            protocol="Aave V3",
            pool_id="aave-usdc",
            token="USDC",
            amount=Decimal("50"),
            value_usd=Decimal("50"),
            current_apy=Decimal("4"),
        )

        await opt.reconcile_positions(["Aave V3", "Moonwell"])

        active = await _active(tracker)
        active_protos = {r.protocol for r in active}
        assert active_protos == {"Moonwell"}  # source closed, target open

        # Source closed at last tracked value → ROI ~0 (a move, NOT a -100% loss).
        closed = tracker.session.query(Position).get(src_id)
        assert closed.status == "closed"
        assert closed.value_usd == Decimal("50")

    async def test_unscanned_position_not_closed(self, tmp_path):
        # A tracked position whose pool is ABSENT from the scan (transient scan
        # / RPC failure for its protocol) must stay active, not be falsely
        # closed — we only close balances we actually confirmed are empty.
        opts = [_opp("Moonwell", "moonwell-usdc")]
        protos = [_proto("Moonwell", "20")]
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=opts, protocols=protos
        )
        # Seed an Aave position; Aave is NOT in this cycle's scan results.
        aave_id = await tracker.record_position(
            wallet_address=WALLET,
            protocol="Aave V3",
            pool_id="aave-usdc",
            token="USDC",
            amount=Decimal("50"),
            value_usd=Decimal("50"),
            current_apy=Decimal("4"),
        )

        await opt.reconcile_positions()  # full scope, Aave absent from scan

        aave = tracker.session.query(Position).get(aave_id)
        assert aave.status == "active"  # left alone, not closed


class TestGating:
    async def test_dry_run_is_noop(self, tmp_path):
        opp = _opp("Moonwell", "moonwell-usdc")
        opt, tracker = _make_optimizer(
            tmp_path,
            opportunities=[opp],
            protocols=[_proto("Moonwell", "100")],
            dry_run=True,
        )

        await opt.reconcile_positions(["Moonwell"])

        assert await _active(tracker) == []
        opt.yield_scanner.protocols[0].get_user_balance.assert_not_called()

    async def test_no_wallet_is_noop(self, tmp_path):
        opp = _opp("Moonwell", "moonwell-usdc")
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=[opp], protocols=[_proto("Moonwell", "100")]
        )
        opt.wallet_manager.address = None

        await opt.reconcile_positions(["Moonwell"])

        assert await _active(tracker) == []

    async def test_no_tracker_is_noop(self, tmp_path):
        opp = _opp("Moonwell", "moonwell-usdc")
        opt, _ = _make_optimizer(
            tmp_path, opportunities=[opp], protocols=[_proto("Moonwell", "100")]
        )
        opt.position_tracker = None
        # Should return without touching the scanner.
        await opt.reconcile_positions(["Moonwell"])
        opt.yield_scanner.scan_all_protocols.assert_not_called()


class TestResilience:
    async def test_protocol_error_isolated(self, tmp_path):
        # One protocol's get_user_balance raises; the other still records.
        opts = [
            _opp("Aave V3", "aave-usdc"),
            _opp("Moonwell", "moonwell-usdc"),
        ]
        protos = [
            _proto("Aave V3", RuntimeError("rpc down")),
            _proto("Moonwell", "75"),
        ]
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=opts, protocols=protos
        )

        await opt.reconcile_positions(["Aave V3", "Moonwell"])

        rows = await _active(tracker)
        assert {r.protocol for r in rows} == {"Moonwell"}
        assert rows[0].amount == Decimal("75")

    async def test_record_failure_does_not_raise(self, tmp_path):
        opp = _opp("Moonwell", "moonwell-usdc")
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=[opp], protocols=[_proto("Moonwell", "100")]
        )
        tracker.record_position = AsyncMock(side_effect=RuntimeError("db boom"))

        # Best-effort contract: must not propagate.
        await opt.reconcile_positions(["Moonwell"])

    async def test_full_scope_when_protocols_none(self, tmp_path):
        # protocols=None → reconcile every scanned pool via scan_all_protocols.
        opts = [
            _opp("Aave V3", "aave-usdc"),
            _opp("Moonwell", "moonwell-usdc"),
        ]
        protos = [_proto("Aave V3", "10"), _proto("Moonwell", "20")]
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=opts, protocols=protos
        )

        await opt.reconcile_positions()

        rows = await _active(tracker)
        assert {r.protocol for r in rows} == {"Aave V3", "Moonwell"}
        opt.yield_scanner.scan_all_protocols.assert_awaited()


class TestRetryOnLag:
    async def test_retries_then_records_target(self, tmp_path):
        # Target reads a stale 0 (RPC lag) then the real balance → recorded.
        opp = _opp("Moonwell", "moonwell-usdc", apy="6")
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=[opp], protocols=[_proto("Moonwell", "0")]
        )
        gub = AsyncMock(side_effect=[Decimal("0"), Decimal("25")])
        opt.yield_scanner.protocols[0].get_user_balance = gub

        await opt.reconcile_positions(
            ["Moonwell"], expect_nonzero=["Moonwell"], retries=3, retry_delay_s=0
        )

        rows = await _active(tracker)
        assert len(rows) == 1 and rows[0].value_usd == Decimal("25")
        assert gub.call_count == 2  # first 0, retry got 25

    async def test_no_retry_without_expect_nonzero(self, tmp_path):
        # retries is ignored unless the protocol is in expect_nonzero.
        opp = _opp("Moonwell", "moonwell-usdc")
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=[opp], protocols=[_proto("Moonwell", "0")]
        )
        gub = AsyncMock(side_effect=[Decimal("0"), Decimal("25")])
        opt.yield_scanner.protocols[0].get_user_balance = gub

        await opt.reconcile_positions(["Moonwell"], retries=3, retry_delay_s=0)

        assert await _active(tracker) == []
        assert gub.call_count == 1  # read once, not retried

    async def test_gives_up_after_retries(self, tmp_path):
        # Persistent 0 → not recorded, read exactly retries+1 times.
        opp = _opp("Moonwell", "moonwell-usdc")
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=[opp], protocols=[_proto("Moonwell", "0")]
        )
        gub = AsyncMock(return_value=Decimal("0"))
        opt.yield_scanner.protocols[0].get_user_balance = gub

        await opt.reconcile_positions(
            ["Moonwell"], expect_nonzero=["Moonwell"], retries=2, retry_delay_s=0
        )

        assert await _active(tracker) == []
        assert gub.call_count == 3  # 1 initial + 2 retries


class TestCycleIntegration:
    async def test_reconciled_target_visible_to_read_path(self, tmp_path):
        # After reconcile, _get_current_positions() aggregates the target by
        # protocol (target-token filtered) — the whole point of the fix.
        opp = _opp("Moonwell", "moonwell-usdc", apy="6")
        opt, tracker = _make_optimizer(
            tmp_path, opportunities=[opp], protocols=[_proto("Moonwell", "100")]
        )

        await opt.reconcile_positions(["Moonwell"])
        positions = await opt._get_current_positions()

        assert positions == {"Moonwell": Decimal("100")}
