"""Unit tests for ScheduledOptimizer resilience (WS3).

Covers the circuit breaker (trip after N failed cycles, subsequent cycles
skipped with one alert, heartbeat written) and the stranded-funds recovery
bypass of the minimum-profit gate.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.scheduled_optimizer import ScheduledOptimizer
from src.strategies.base_strategy import RebalanceRecommendation


def _optimizer(tmp_path, **config_overrides):
    config = {
        "dry_run_mode": True,
        "circuit_breaker_consecutive_failures": 2,
        "circuit_breaker_max_failures_per_day": 10,
        "circuit_breaker_state_file": str(tmp_path / "breaker.json"),
        "heartbeat_file": str(tmp_path / "heartbeat.json"),
        "max_wallet_balance_usd": "100000",
        "recovery_max_gas_usd": "1",
    }
    config.update(config_overrides)

    wallet = MagicMock()
    wallet.get_balance = AsyncMock(return_value=Decimal("0"))

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
    # Spy on alerting.
    opt._alerts = MagicMock()
    opt._alerts.warn = AsyncMock()
    opt._alerts.error = AsyncMock()
    opt._alerts.critical = AsyncMock()
    return opt


class TestCircuitBreaker:
    async def test_trips_after_consecutive_failures(self, tmp_path):
        opt = _optimizer(tmp_path)
        opt.optimizer.find_rebalance_opportunities = AsyncMock(
            side_effect=RuntimeError("scan boom")
        )

        # First two cycles fail and re-raise.
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await opt.run_once()

        assert opt.breaker.is_tripped()

        # Third cycle: breaker guard skips work and returns [] (no raise).
        result = await opt.run_once()
        assert result == []
        assert opt.status.halted is True

    async def test_alerts_once_on_trip(self, tmp_path):
        opt = _optimizer(tmp_path)
        opt.optimizer.find_rebalance_opportunities = AsyncMock(side_effect=RuntimeError("boom"))
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await opt.run_once()
        await opt.run_once()  # skipped cycle
        await opt.run_once()  # skipped cycle

        crit_titles = [c.args[0] for c in opt._alerts.critical.call_args_list]
        assert crit_titles.count("Circuit breaker tripped") == 1

    async def test_heartbeat_written_each_cycle(self, tmp_path):
        opt = _optimizer(tmp_path)
        opt.optimizer.find_rebalance_opportunities = AsyncMock(return_value=[])
        await opt.run_once()
        assert (tmp_path / "heartbeat.json").exists()

    async def test_success_does_not_trip(self, tmp_path):
        opt = _optimizer(tmp_path)
        opt.optimizer.find_rebalance_opportunities = AsyncMock(return_value=[])
        for _ in range(5):
            await opt.run_once()
        assert not opt.breaker.is_tripped()


class TestRecoveryDeployable:
    async def test_recovery_allows_low_apy_within_gas_ceiling(self, tmp_path):
        opt = _optimizer(tmp_path)
        analysis = MagicMock()
        analysis.total_cost = Decimal("0.50")  # within $1 ceiling
        opt.profitability_calc.calculate_profitability = AsyncMock(return_value=analysis)

        rec = RebalanceRecommendation(
            from_protocol=None,
            to_protocol="Moonwell",
            token="USDC",
            amount=Decimal("50"),
            expected_apy=Decimal("2.0"),  # low APY that would fail $10/yr gate
            reason="recover",
            confidence=80,
        )
        assert await opt._is_recovery_deployable(rec) is True

    async def test_recovery_rejects_when_gas_exceeds_ceiling(self, tmp_path):
        opt = _optimizer(tmp_path)
        analysis = MagicMock()
        analysis.total_cost = Decimal("5.00")  # over $1 ceiling
        opt.profitability_calc.calculate_profitability = AsyncMock(return_value=analysis)

        rec = RebalanceRecommendation(
            from_protocol=None,
            to_protocol="Moonwell",
            token="USDC",
            amount=Decimal("50"),
            expected_apy=Decimal("2.0"),
            reason="recover",
            confidence=80,
        )
        assert await opt._is_recovery_deployable(rec) is False

    async def test_recovery_rejects_zero_apy(self, tmp_path):
        opt = _optimizer(tmp_path)
        rec = RebalanceRecommendation(
            from_protocol=None,
            to_protocol="Moonwell",
            token="USDC",
            amount=Decimal("50"),
            expected_apy=Decimal("0"),
            reason="recover",
            confidence=80,
        )
        assert await opt._is_recovery_deployable(rec) is False
