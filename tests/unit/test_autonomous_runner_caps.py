"""Regression tests for the autonomous runner's per-day rail handling.

Two properties are guarded here:

1. The runner's ``run()`` loop must NOT terminate a multi-day run just because
   the cumulative lifetime totals (``total_rebalances`` / ``total_gas_spent_usd``)
   have crossed the per-day caps. Those counters are lifetime-of-run reporting
   metrics; the authoritative per-day gate lives in
   ``ScheduledOptimizer._check_daily_limits()`` (rolling 24h reset, skips a
   rebalance rather than ending the run). The old code ``break``-ed the whole
   loop on them, so a 30-day run died permanently once the total was hit.

2. The operator's ``--max-rebalances`` / ``--max-gas`` values must actually
   reach the scheduler via the config dict. If the keys are dropped the
   scheduler silently falls back to 5/day + $50/day gas, making the flags dead.
"""

import asyncio
from decimal import Decimal

import scripts.run_autonomous_optimizer as runner_module
from scripts.run_autonomous_optimizer import AutonomousRunner


class _FakeBreaker:
    def is_tripped(self) -> bool:
        return False


class _FakeRecommendation:
    from_protocol = "Aave V3"
    to_protocol = "Moonwell"
    token = "USDC"
    amount = Decimal("100")
    current_apy = Decimal("3.0")
    expected_apy = Decimal("5.0")


class _FakeExecution:
    success = True
    total_gas_cost_usd = Decimal("5")
    recommendation = _FakeRecommendation()


class _FakeScheduler:
    """Returns one successful execution per cycle and stops the run after N."""

    def __init__(self, runner: AutonomousRunner, stop_after: int) -> None:
        self.breaker = _FakeBreaker()
        self._runner = runner
        self._stop_after = stop_after
        self.calls = 0

    async def run_once(self):
        self.calls += 1
        if self.calls >= self._stop_after:
            # End the while loop on the next `if not self.running` check.
            self._runner.running = False
        return [_FakeExecution()]


def test_lifetime_total_does_not_break_run(monkeypatch):
    """The loop keeps scanning even when lifetime totals exceed the caps.

    Under the old code the first cycle would trip the ``break`` and the run
    would stop at ``total_scans == 1``. With the fix the loop runs every cycle
    until the scheduler signals completion.
    """
    runner = AutonomousRunner(
        duration_hours=100.0,  # far in the future so time never ends the loop
        scan_interval_hours=0.0001,  # ~0 sleep iterations
        max_rebalances_per_day=20,
        max_gas_per_day_usd=Decimal("2"),
        dry_run=True,
    )

    # Pre-load the lifetime totals well above BOTH caps.
    runner.total_rebalances = 999
    runner.total_gas_spent_usd = Decimal("9999")

    runner.scheduler = _FakeScheduler(runner, stop_after=3)

    # The initial/final balance blocks are wrapped in try/except; leaving these
    # as None makes them no-ops without needing wallet/oracle fakes.
    runner.wallet = None
    runner.oracle = None
    runner.position_tracker = None
    runner.performance_tracker = None

    # Avoid the summary's file write and balance fetches.
    async def _fake_summary(_initial):
        return {}

    monkeypatch.setattr(runner, "_generate_summary", _fake_summary)

    # Belt-and-suspenders: never actually sleep even if iterations are computed.
    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(runner_module.asyncio, "sleep", _no_sleep)

    asyncio.run(runner.run())

    # Ran all three cycles despite lifetime totals exceeding the caps.
    assert runner.scheduler.calls == 3
    assert runner.total_scans == 3


def test_operator_caps_propagate_to_config():
    """`--max-rebalances` / `--max-gas` land in the config the scheduler reads."""
    runner = AutonomousRunner(
        duration_hours=1.0,
        scan_interval_hours=2.0,
        max_rebalances_per_day=20,
        max_gas_per_day_usd=Decimal("2"),
        dry_run=True,
    )

    config = runner._build_config()

    assert config["max_rebalances_per_day"] == 20
    assert config["max_gas_per_day_usd"] == Decimal("2")
