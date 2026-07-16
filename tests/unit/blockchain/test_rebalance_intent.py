"""Unit tests for rebalance intent tracking (WS3).

Verifies that a live rebalance records an intent, that a full success marks it
completed, that a withdraw-succeeded/deposit-failed run marks it 'stranded'
(and raises), and that dry-run creates no intent rows.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.blockchain.rebalance_executor import (
    RebalanceExecutor,
    RebalanceExecution,
    RebalanceStep,
    StepResult,
)
from src.data.database import Database
from src.data.models import RebalanceIntent
from src.strategies.base_strategy import RebalanceRecommendation


@pytest.fixture
def db(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/intent.db")
    database.create_all_tables()
    return database


def _executor(db, dry_run=False):
    ex = RebalanceExecutor(
        wallet_manager=MagicMock(),
        protocol_executor=MagicMock(),
        gas_estimator=MagicMock(),
        price_oracle=MagicMock(),
        config={
            "dry_run_mode": dry_run,
            "max_transaction_value_usd": "1000",
            "daily_spending_limit_usd": "5000",
        },
        database=db,
    )
    ex.audit_logger = MagicMock()
    ex.audit_logger.log_event = AsyncMock()
    return ex


def _rec(from_protocol="Aave V3", to_protocol="Moonwell"):
    return RebalanceRecommendation(
        from_protocol=from_protocol,
        to_protocol=to_protocol,
        token="USDC",
        amount=Decimal("50"),
        expected_apy=Decimal("5.0"),
        reason="test",
        confidence=80,
        current_apy=Decimal("3.0"),
    )


def _intents(db):
    import asyncio

    async def _q():
        async with db.get_session() as session:
            return session.query(RebalanceIntent).all()

    return asyncio.get_event_loop().run_until_complete(_q())


class TestClassificationHelpers:
    def test_is_stranded_true_when_withdraw_ok_deposit_missing(self):
        ex_result = RebalanceExecution(recommendation=_rec())
        ex_result.add_step_result(StepResult(step=RebalanceStep.WITHDRAW, success=True))
        assert RebalanceExecutor._is_stranded(ex_result) is True

    def test_is_stranded_false_when_deposit_succeeded(self):
        ex_result = RebalanceExecution(recommendation=_rec())
        ex_result.add_step_result(StepResult(step=RebalanceStep.WITHDRAW, success=True))
        ex_result.add_step_result(StepResult(step=RebalanceStep.DEPOSIT, success=True))
        assert RebalanceExecutor._is_stranded(ex_result) is False

    def test_is_stranded_false_when_no_withdraw(self):
        ex_result = RebalanceExecution(recommendation=_rec(from_protocol=None))
        assert RebalanceExecutor._is_stranded(ex_result) is False

    def test_step_tx_hash(self):
        ex_result = RebalanceExecution(recommendation=_rec())
        ex_result.add_step_result(
            StepResult(step=RebalanceStep.WITHDRAW, success=True, tx_hash="0xabc")
        )
        assert RebalanceExecutor._step_tx_hash(ex_result, RebalanceStep.WITHDRAW) == "0xabc"
        assert RebalanceExecutor._step_tx_hash(ex_result, RebalanceStep.DEPOSIT) is None


class TestIntentPersistence:
    async def test_create_and_finalize_stranded(self, db):
        ex = _executor(db)
        intent_id = await ex._create_intent(_rec())
        assert intent_id is not None

        execution = RebalanceExecution(recommendation=_rec())
        execution.add_step_result(
            StepResult(step=RebalanceStep.WITHDRAW, success=True, tx_hash="0xw")
        )
        await ex._finalize_failed_intent(intent_id, execution, "deposit reverted", stranded=True)

        async with db.get_session() as session:
            intent = session.query(RebalanceIntent).filter_by(id=intent_id).one()
            assert intent.status == "stranded"
            assert intent.error == "deposit reverted"
            assert intent.withdraw_tx_hash == "0xw"

    async def test_update_marks_completed(self, db):
        ex = _executor(db)
        intent_id = await ex._create_intent(_rec())
        await ex._update_intent(intent_id, status="completed")
        async with db.get_session() as session:
            intent = session.query(RebalanceIntent).filter_by(id=intent_id).one()
            assert intent.status == "completed"

    async def test_no_database_is_noop(self):
        ex = _executor(None)
        ex.database = None
        assert await ex._create_intent(_rec()) is None  # does not raise


class TestFullFlow:
    async def _patch_steps(self, ex, *, deposit_fails: bool):
        ex._validate_recommendation = AsyncMock()
        ex._check_initial_balances = AsyncMock()
        ex._verify_final_balances = AsyncMock()
        ex._calculate_actual_costs = AsyncMock()
        ex._persist_transactions = AsyncMock()
        ex._requires_swap = MagicMock(return_value=False)

        async def _withdraw(rec, execution):
            execution.add_step_result(
                StepResult(step=RebalanceStep.WITHDRAW, success=True, tx_hash="0xw")
            )

        async def _approve(rec, execution):
            execution.add_step_result(
                StepResult(step=RebalanceStep.APPROVE_DEPOSIT, success=True, tx_hash="0xa")
            )

        async def _deposit(rec, execution):
            if deposit_fails:
                raise RuntimeError("deposit reverted")
            execution.add_step_result(
                StepResult(step=RebalanceStep.DEPOSIT, success=True, tx_hash="0xd")
            )

        ex._execute_withdraw_step = _withdraw
        ex._execute_approve_deposit_step = _approve
        ex._execute_deposit_step = _deposit

    async def test_success_marks_intent_completed(self, db):
        ex = _executor(db)
        await self._patch_steps(ex, deposit_fails=False)
        execution = await ex.execute_rebalance(_rec())
        assert execution.success
        intents = _intents(db)
        assert len(intents) == 1
        assert intents[0].status == "completed"
        assert intents[0].deposit_tx_hash == "0xd"

    async def test_deposit_failure_marks_stranded_and_raises(self, db):
        ex = _executor(db)
        await self._patch_steps(ex, deposit_fails=True)
        with pytest.raises(RuntimeError):
            await ex.execute_rebalance(_rec())
        intents = _intents(db)
        assert len(intents) == 1
        assert intents[0].status == "stranded"
        assert intents[0].withdraw_tx_hash == "0xw"

    async def test_dry_run_creates_no_intent(self, db):
        ex = _executor(db, dry_run=True)
        ex._validate_recommendation = AsyncMock()
        ex._check_initial_balances = AsyncMock()
        execution = await ex.execute_rebalance(_rec())
        assert execution.success
        assert _intents(db) == []
