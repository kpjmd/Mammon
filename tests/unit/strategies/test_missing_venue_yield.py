"""A held venue with no yield data this cycle must be held, not exited.

Regression for PR #26 review #2: SimpleYieldStrategy used
`available_yields.get(current_protocol, 0)`, so any scan failure for the venue
we hold (a tripped Morpho vault guard, an RPC blip or timeout, a Moonwell
outage) read as 0% APY and recommended an exit on its own.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.scheduled_optimizer import ScheduledOptimizer
from src.strategies.base_strategy import RejectedAlternative
from src.strategies.simple_yield import SimpleYieldStrategy


def _strategy(supported=("Aave V3", "Moonwell", "Morpho")):
    calc = MagicMock()
    calc.calculate_profitability = AsyncMock()
    return SimpleYieldStrategy(
        {"supported_protocols": list(supported), "min_rebalance_amount": Decimal("10")},
        profitability_calc=calc,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("held", ["Morpho", "Moonwell", "Aave V3"])
async def test_missing_yield_for_held_venue_holds(held):
    strategy = _strategy()
    yields = {p: apy for p, apy in
              {"Aave V3": Decimal("4.8"), "Moonwell": Decimal("15"), "Morpho": Decimal("4.4")}.items()
              if p != held}

    recs = await strategy.analyze_opportunities({held: Decimal("108")}, yields)

    assert recs == []
    strategy.profitability_calc.calculate_profitability.assert_not_awaited()
    [rejection] = strategy.last_rejections
    assert rejection.from_protocol == held
    assert rejection.to_protocol == max(yields, key=yields.get)
    assert rejection.current_apy is None
    assert rejection.apy_improvement is None
    assert "no yield data" in rejection.reason


@pytest.mark.asyncio
async def test_missing_yield_without_alternatives_records_nothing():
    strategy = _strategy(supported=("Morpho",))
    recs = await strategy.analyze_opportunities({"Morpho": Decimal("108")}, {})
    assert recs == []
    assert strategy.last_rejections == []


@pytest.mark.asyncio
async def test_present_zero_yield_still_compared():
    """A venue that genuinely reports 0% is data, not missing: it may be exited."""
    strategy = _strategy()
    strategy.profitability_calc.calculate_profitability.return_value = MagicMock(
        is_profitable=True, net_gain_first_year=Decimal("5"), break_even_days=1,
        roi_on_costs=Decimal("100"), rejection_reasons=[],
    )
    recs = await strategy.analyze_opportunities(
        {"Morpho": Decimal("108")}, {"Morpho": Decimal("0"), "Moonwell": Decimal("15")}
    )
    assert [(r.from_protocol, r.to_protocol) for r in recs] == [("Morpho", "Moonwell")]


@pytest.mark.asyncio
async def test_hold_rejection_persists_with_unknown_improvement(tmp_path):
    from tests.unit.agents.test_optimizer_reconcile import _make_optimizer

    opt, _ = _make_optimizer(tmp_path, opportunities=[], protocols=[])
    opt._record_decision = AsyncMock()
    opt.optimizer.strategy = MagicMock()
    opt.optimizer.strategy.last_rejections = [
        RejectedAlternative("Morpho", "Moonwell", None, Decimal("15"), "Strategy: holding Morpho")
    ]

    await ScheduledOptimizer._record_strategy_rejections(opt)

    kwargs = opt._record_decision.await_args.kwargs
    assert kwargs["from_protocol"] == "Morpho"
    assert kwargs["approved"] == -1
    assert kwargs["expected_apy_improvement"] is None
