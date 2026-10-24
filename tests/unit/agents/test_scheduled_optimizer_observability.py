"""Observability regressions found in the 3-month live MPC run.

- Strategy-level skips (APY threshold / strategy profitability) never reached
  the decisions table, so the ledger could not explain 0 rebalances.
- A hold with an active position logged "No positions and no idle capital".
- The heartbeat's total_scans stayed 0: the runner drives cycles via run_once(),
  but only _run_loop counted scans.
"""

import json
import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.agents.scheduled_optimizer import ScheduledOptimizer
from src.strategies.base_strategy import RejectedAlternative


def _optimizer(tmp_path):
    wallet = MagicMock()
    wallet.address = "0xE06860747338660a0474b81E401BE60aeCf96f91"
    opt = ScheduledOptimizer(
        config={
            "dry_run_mode": False,
            "circuit_breaker_state_file": str(tmp_path / "breaker.json"),
            "heartbeat_file": str(tmp_path / "heartbeat.json"),
        },
        yield_scanner=MagicMock(),
        optimizer=MagicMock(),
        risk_assessor=MagicMock(),
        rebalance_executor=MagicMock(),
        wallet_manager=wallet,
        profitability_calc=MagicMock(),
        audit_logger=MagicMock(),
        database=None,
        position_tracker=None,
    )
    opt.audit_logger.log_event = AsyncMock()
    opt._record_decision = AsyncMock()
    return opt


def _hold_cycle(opt):
    """Stub a cycle that ends in a hold: one position, no recs, no idle cash."""
    opt.reconcile_on_read = False
    opt._alert_stranded_intents = AsyncMock()
    opt._check_balance_cap = AsyncMock()
    opt._get_current_positions = AsyncMock(return_value={"Moonwell": Decimal("107.70")})
    opt._get_idle_capital = AsyncMock(return_value={})
    opt.optimizer.find_rebalance_opportunities = AsyncMock(return_value=[])


class TestStrategyRejectionsRecorded:
    async def test_rejections_persisted_as_rejected_rebalance(self, tmp_path):
        opt = _optimizer(tmp_path)
        rejection = RejectedAlternative(
            "Moonwell",
            "Aave V3",
            Decimal("4.1"),
            Decimal("4.3"),
            "Strategy: APY improvement 0.2000% below threshold 0.5%",
        )
        opt.optimizer.strategy.last_rejections = [rejection]

        await opt._record_strategy_rejections()

        opt._record_decision.assert_awaited_once_with(
            decision_type="rebalance",
            rationale=rejection.reason,
            from_protocol="Moonwell",
            to_protocol="Aave V3",
            approved=-1,
            expected_apy_improvement=Decimal("0.2"),
        )

    async def test_rejections_consumed_once(self, tmp_path):
        """A later cycle that never calls the strategy must not re-record them."""
        opt = _optimizer(tmp_path)
        opt.optimizer.strategy.last_rejections = [
            RejectedAlternative("Moonwell", "Aave V3", Decimal("4"), Decimal("5"), "r")
        ]

        await opt._record_strategy_rejections()
        await opt._record_strategy_rejections()

        assert opt._record_decision.await_count == 1
        assert opt.optimizer.strategy.last_rejections == []

    async def test_strategy_without_rejection_list_is_noop(self, tmp_path):
        opt = _optimizer(tmp_path)  # MagicMock strategy: attribute is not a list

        await opt._record_strategy_rejections()

        opt._record_decision.assert_not_awaited()

    async def test_cycle_records_rejections(self, tmp_path):
        opt = _optimizer(tmp_path)
        _hold_cycle(opt)
        opt.optimizer.strategy.last_rejections = [
            RejectedAlternative("Moonwell", "Aave V3", Decimal("4"), Decimal("5"), "r")
        ]

        await opt.run_once()

        assert opt._record_decision.await_args.kwargs["approved"] == -1


class TestHoldCycle:
    async def test_hold_message_names_positions(self, tmp_path, caplog):
        opt = _optimizer(tmp_path)
        _hold_cycle(opt)

        with caplog.at_level(logging.INFO):
            await opt.run_once()

        assert "No rebalance recommended for 1 position(s)" in caplog.text
        assert "No positions and no idle capital" not in caplog.text

    async def test_run_once_counts_scans_into_heartbeat(self, tmp_path):
        opt = _optimizer(tmp_path)
        _hold_cycle(opt)

        await opt.run_once()
        await opt.run_once()

        assert opt.status.total_scans == 2
        heartbeat = json.loads((tmp_path / "heartbeat.json").read_text())
        assert heartbeat["total_scans"] == 2
