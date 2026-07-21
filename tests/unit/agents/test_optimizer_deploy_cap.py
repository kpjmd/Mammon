"""Unit tests for the --max-deploy-usd idle-capital deployment cap.

`_deploy_idle_capital` normally deploys the entire idle balance. When
`max_deploy_usd` is configured, a single deployment is clamped to that USD
ceiling (the remainder is left idle for a later cycle), which lets a live test
be bounded without lowering MAX_TRANSACTION_VALUE_USD.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.scheduled_optimizer import ScheduledOptimizer


def _optimizer(tmp_path, **config_overrides):
    config = {
        "dry_run_mode": False,
        "circuit_breaker_state_file": str(tmp_path / "breaker.json"),
        "heartbeat_file": str(tmp_path / "heartbeat.json"),
    }
    config.update(config_overrides)

    wallet = MagicMock()
    wallet.address = "0xF5Fec40E1fafa9e4382C872550d7C4944b5a1e65"

    opt = ScheduledOptimizer(
        config=config,
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

    # Stub the surrounding gates so the deploy reaches execution.
    opt._stranded_recovery_tokens = AsyncMock(return_value=set())
    opt._is_deployment_profitable = AsyncMock(return_value=True)
    opt._record_decision = AsyncMock()
    opt.reconcile_positions = AsyncMock()

    best = MagicMock()
    best.protocol = "Aave V3"
    best.apy = Decimal("4")
    best.pool_id = "aave-v3-usdc"
    best.tokens = ["USDC"]
    opt.yield_scanner.find_best_yield = AsyncMock(return_value=best)

    risk = MagicMock()
    risk.risk_level.value = "LOW"
    risk.risk_score = Decimal("0.1")
    risk.recommendation = "ok"
    opt.risk_assessor.assess_rebalance_risk = AsyncMock(return_value=risk)
    opt.risk_assessor.should_proceed = MagicMock(return_value=True)

    execution = MagicMock()
    execution.success = True
    execution.total_gas_cost_usd = Decimal("0.1")
    opt.rebalance_executor.execute_rebalance = AsyncMock(return_value=execution)

    return opt


def _deployed_amount(opt):
    """The amount on the recommendation actually sent to execute_rebalance."""
    return opt.rebalance_executor.execute_rebalance.call_args.args[0].amount


class TestMaxDeployCap:
    async def test_caps_deployment_to_ceiling(self, tmp_path):
        opt = _optimizer(tmp_path, max_deploy_usd=Decimal("50"))
        await opt._deploy_idle_capital({"USDC": Decimal("77.53")})
        assert _deployed_amount(opt) == Decimal("50")
        opt.reconcile_positions.assert_awaited()  # position still recorded

    async def test_no_cap_deploys_full_balance(self, tmp_path):
        opt = _optimizer(tmp_path)  # max_deploy_usd unset
        assert opt.max_deploy_usd is None
        await opt._deploy_idle_capital({"USDC": Decimal("77.53")})
        assert _deployed_amount(opt) == Decimal("77.53")

    async def test_amount_below_cap_unchanged(self, tmp_path):
        opt = _optimizer(tmp_path, max_deploy_usd=Decimal("100"))
        await opt._deploy_idle_capital({"USDC": Decimal("40")})
        assert _deployed_amount(opt) == Decimal("40")

    async def test_amount_equal_to_cap_unchanged(self, tmp_path):
        opt = _optimizer(tmp_path, max_deploy_usd=Decimal("50"))
        await opt._deploy_idle_capital({"USDC": Decimal("50")})
        assert _deployed_amount(opt) == Decimal("50")
