"""Bad-debt auto-exit: ScheduledOptimizer._emergency_exit_tripped_vaults.

Only a SHARE_PRICE latch with an on-chain position triggers a withdrawal, via
ProtocolActionExecutor.execute_withdraw(..., emergency=True). Operator latches
and governance drift hold; an unreadable guard state alerts only. Uses the
real MorphoVaultProtocol and ProtocolActionExecutor on the fake chain, so
"broadcast" means a write recorded in FakeWeb3.built.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.data.database import Database
from src.data.models import Transaction
from src.protocols.morpho_vault import MorphoVaultProtocol, VaultGuardError
from src.protocols.morpho_vault_guard import VaultGuardStore
from tests.unit.agents.test_optimizer_reconcile import WALLET as OPT_WALLET
from tests.unit.agents.test_optimizer_reconcile import _make_optimizer
from tests.unit.morpho_vault_fakes import SPEC, VAULT, FakeWeb3, usdc


@pytest.fixture
def fake() -> FakeWeb3:
    f = FakeWeb3()
    f.wallet_holds("100")
    return f


def _protocol(fake: FakeWeb3) -> MorphoVaultProtocol:
    oracle = MagicMock()
    oracle.get_price = AsyncMock(return_value=Decimal("1"))
    with patch("src.protocols.morpho_vault.get_web3", return_value=fake), patch(
        "src.protocols.morpho_vault.get_settings"
    ):
        return MorphoVaultProtocol({"network": "base-mainnet", "price_oracle": oracle})


def _executor(fake: FakeWeb3, dry_run: bool) -> ProtocolActionExecutor:
    wallet = MagicMock()
    wallet.get_address = AsyncMock(return_value=OPT_WALLET)
    wallet.send_transaction = AsyncMock(
        side_effect=lambda to, data, value: f"0xexit{len(fake.built)}"
    )
    with patch("src.blockchain.protocol_action_executor.get_web3", return_value=fake), patch(
        "src.blockchain.protocol_action_executor.get_settings"
    ):
        ex = ProtocolActionExecutor(wallet, {"network": "base-mainnet", "dry_run_mode": dry_run})
    ex.audit_logger = MagicMock()
    ex.audit_logger.log_event = AsyncMock()
    return ex


def _setup(fake, tmp_path, dry_run=False):
    proto = _protocol(fake)
    opt, tracker = _make_optimizer(tmp_path, opportunities=[], protocols=[proto], dry_run=dry_run)
    opt.rebalance_executor = MagicMock()
    opt.rebalance_executor.protocol_executor = _executor(fake, dry_run)
    opt._alerts = MagicMock()
    opt._alerts.critical = AsyncMock(return_value=True)
    opt._record_decision = AsyncMock()
    opt._record_emergency_tx = AsyncMock()
    return opt, proto, tracker


def _trip_share_price(fake: FakeWeb3) -> None:
    store = VaultGuardStore()
    store.check_share_price(SPEC.address, SPEC.label, fake.share_price)
    with pytest.raises(VaultGuardError):
        store.check_share_price(SPEC.address, SPEC.label, fake.share_price * 98 // 100)


def _vault_writes(fake):
    return [(name, args) for to, name, args in fake.built if to == VAULT]


def _alert_messages(opt):
    return [c.args[1] for c in opt._alerts.critical.await_args_list]


# ===== WHEN TO EXIT =====


@pytest.mark.asyncio
async def test_share_price_trip_with_position_exits_once(fake, tmp_path):
    _trip_share_price(fake)
    opt, _, _ = _setup(fake, tmp_path)

    await opt._emergency_exit_tripped_vaults()

    assert [name for name, _ in _vault_writes(fake)] == ["redeem"]
    opt._record_decision.assert_awaited_once()
    kwargs = opt._record_decision.await_args.kwargs
    assert kwargs["decision_type"] == "emergency_exit" and kwargs["approved"] == 1
    assert "share price fell" in kwargs["rationale"]
    opt._record_emergency_tx.assert_awaited_once()
    [message] = _alert_messages(opt)
    assert "withdrew" in message and "0xexit" in message and "stuck" not in message

    # Next cycle, after the funds left: no second exit.
    fake.wallet_shares = 0
    await opt._emergency_exit_tripped_vaults()
    assert len(_vault_writes(fake)) == 1


@pytest.mark.asyncio
async def test_idle_deploy_next_cycle_excludes_latched_vault(fake, tmp_path):
    from src.agents.yield_scanner import YieldScannerAgent

    _trip_share_price(fake)
    with patch("src.protocols.morpho_vault.get_web3", return_value=fake):
        scanner = YieldScannerAgent({"chainlink_enabled": False, "network": "base-mainnet"})
    scanner.protocols = [_protocol(fake)]

    assert await scanner.find_best_yield("USDC", protocol_allowlist=["Morpho"]) is None
    # And the executor refuses a deposit regardless of what is recommended.
    with pytest.raises(VaultGuardError):
        await _executor(fake, dry_run=False).execute_deposit("Morpho", "USDC", Decimal("50"))


@pytest.mark.asyncio
async def test_not_tripped_does_nothing(fake, tmp_path):
    opt, _, _ = _setup(fake, tmp_path)
    await opt._emergency_exit_tripped_vaults()
    assert fake.built == []
    opt._alerts.critical.assert_not_awaited()


@pytest.mark.asyncio
async def test_operator_latch_holds(fake, tmp_path):
    VaultGuardStore().latch(SPEC.address, "operator exit via scripts/morpho_vault_exit.py")
    opt, _, _ = _setup(fake, tmp_path)
    await opt._emergency_exit_tripped_vaults()
    assert fake.built == []
    opt._alerts.critical.assert_not_awaited()


@pytest.mark.asyncio
async def test_governance_drift_holds(fake, tmp_path):
    opt, proto, _ = _setup(fake, tmp_path)
    fake.set_vault(curator="0x000000000000000000000000000000000000dEaD")
    with pytest.raises(VaultGuardError):
        await proto.get_pools()  # drift excludes the vault but never latches

    await opt._emergency_exit_tripped_vaults()

    assert fake.built == []


@pytest.mark.asyncio
async def test_unreadable_state_alerts_but_never_exits(fake, tmp_path):
    import src.protocols.morpho_vault_guard as guard_module
    from pathlib import Path

    Path(guard_module.DEFAULT_STATE_FILE).write_text("{corrupt")
    opt, _, _ = _setup(fake, tmp_path)

    await opt._emergency_exit_tripped_vaults()
    await opt._emergency_exit_tripped_vaults()

    assert fake.built == []
    [message] = _alert_messages(opt)  # deduped across cycles
    assert "unreadable" in message and "no automatic exit" in message


@pytest.mark.asyncio
async def test_dry_run_simulates_only(fake, tmp_path):
    _trip_share_price(fake)
    opt, _, _ = _setup(fake, tmp_path, dry_run=True)

    await opt._emergency_exit_tripped_vaults()

    assert fake.built == []
    opt._alerts.critical.assert_not_awaited()
    opt._record_decision.assert_not_awaited()
    opt.rebalance_executor.protocol_executor.wallet.send_transaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_dry_run_scheduler_never_calls_a_live_executor(fake, tmp_path):
    _trip_share_price(fake)
    opt, _, _ = _setup(fake, tmp_path, dry_run=True)
    opt.rebalance_executor.protocol_executor = _executor(fake, dry_run=False)

    await opt._emergency_exit_tripped_vaults()

    assert fake.built == []


# ===== LIQUIDITY =====


@pytest.mark.asyncio
async def test_partial_liquidity_withdraws_what_it_can_and_retries(fake, tmp_path):
    _trip_share_price(fake)
    fake.max_withdraw = usdc("30")
    opt, _, _ = _setup(fake, tmp_path)

    await opt._emergency_exit_tripped_vaults()

    assert _vault_writes(fake) == [("withdraw", (usdc("30"), OPT_WALLET, OPT_WALLET))]
    [message] = _alert_messages(opt)
    assert "withdrew 30" in message and "still stuck" in message

    # Next cycle retries the remainder (state unchanged in the fake).
    await opt._emergency_exit_tripped_vaults()
    assert len(_vault_writes(fake)) == 2


@pytest.mark.asyncio
async def test_no_liquidity_sends_nothing_and_alerts_once(fake, tmp_path):
    _trip_share_price(fake)
    fake.max_withdraw = 0
    opt, _, _ = _setup(fake, tmp_path)

    await opt._emergency_exit_tripped_vaults()
    await opt._emergency_exit_tripped_vaults()

    assert fake.built == []
    [message] = _alert_messages(opt)
    assert "no withdrawable liquidity" in message and "retrying" in message
    opt._record_decision.assert_awaited_once()


@pytest.mark.asyncio
async def test_reverted_withdraw_alerts_and_cycle_continues(fake, tmp_path):
    _trip_share_price(fake)
    fake.receipt_status = 0
    opt, _, _ = _setup(fake, tmp_path)

    await opt._emergency_exit_tripped_vaults()  # must not raise
    await opt._emergency_exit_tripped_vaults()

    assert [name for name, _ in _vault_writes(fake)] == ["redeem", "redeem"]  # retried
    [message] = _alert_messages(opt)  # identical outcome not re-alerted
    assert "reverted" in message
    assert opt._record_emergency_tx.await_count == 2  # every real tx is recorded


@pytest.mark.asyncio
async def test_rpc_error_during_exit_alerts(fake, tmp_path):
    _trip_share_price(fake)
    fake.set_vault(maxWithdraw=ConnectionError("rpc down"))
    opt, _, _ = _setup(fake, tmp_path)

    await opt._emergency_exit_tripped_vaults()

    assert fake.built == []
    [message] = _alert_messages(opt)
    assert "rpc down" in message


@pytest.mark.asyncio
async def test_emergency_mode_is_morpho_only(fake):
    ex = _executor(fake, dry_run=False)
    with pytest.raises(ValueError, match="only defined for Morpho"):
        await ex.execute_withdraw("Moonwell", "USDC", Decimal("1"), emergency=True)


@pytest.mark.asyncio
async def test_default_withdraw_still_refuses_short_liquidity(fake):
    fake.max_withdraw = usdc("30")
    with pytest.raises(ValueError, match="liquidity"):
        await _executor(fake, dry_run=False).execute_withdraw("Morpho", "USDC", Decimal("100"))


# ===== BOOKKEEPING =====


@pytest.mark.asyncio
async def test_reconcile_closes_row_after_exit(fake, tmp_path):
    _trip_share_price(fake)
    opt, proto, tracker = _setup(fake, tmp_path)
    await tracker.record_position(
        wallet_address=OPT_WALLET, protocol="Morpho", pool_id=SPEC.pool_id, token="USDC",
        amount=Decimal("100"), value_usd=Decimal("100"), current_apy=Decimal("4.4"),
    )

    # The redeem "lands": the wallet's shares are gone once the tx is sent.
    send = opt.rebalance_executor.protocol_executor.wallet.send_transaction
    send.side_effect = lambda to, data, value: (setattr(fake, "wallet_shares", 0) or "0xexit")

    await opt._emergency_exit_tripped_vaults()

    assert await tracker.get_current_positions(wallet_address=OPT_WALLET) == []


@pytest.mark.asyncio
async def test_emergency_tx_row_persisted(tmp_path):
    db = Database(f"sqlite:///{tmp_path}/emergency.db")
    db.create_all_tables()
    opt, _ = _make_optimizer(tmp_path, opportunities=[], protocols=[])
    opt.database = db

    await opt._record_emergency_tx(
        "USDC", Decimal("30"), {"tx_hash": "0xexit1", "success": True, "gas_used": 210000}
    )

    async with db.get_session() as session:
        [row] = session.query(Transaction).all()
        assert (row.operation, row.from_protocol, row.amount, row.status) == (
            "emergency_exit", "Morpho", Decimal("30"), "completed",
        )


# ===== GATES =====


@pytest.mark.asyncio
async def test_bypasses_daily_rebalance_cap(fake, tmp_path):
    _trip_share_price(fake)
    opt, _, _ = _setup(fake, tmp_path)
    opt.max_rebalances_per_day = 0  # daily cap exhausted
    assert opt._check_daily_limits() is False
    opt.reconcile_on_read = False
    opt._alert_stranded_intents = AsyncMock()
    opt._check_balance_cap = AsyncMock()
    opt._get_current_positions = AsyncMock(return_value={"Morpho": Decimal("100")})
    opt._get_idle_capital = AsyncMock(return_value={})
    opt.optimizer.find_rebalance_opportunities = AsyncMock(return_value=[])

    await opt._execute_optimization_cycle()

    assert [name for name, _ in _vault_writes(fake)] == ["redeem"]


# ===== NO REDEPOSIT IN THE EXIT CYCLE =====


def _cycle(opt):
    """Stub a no-recommendation cycle that has idle USDC to deploy."""
    opt.reconcile_on_read = False
    opt._alert_stranded_intents = AsyncMock()
    opt._check_balance_cap = AsyncMock()
    opt._get_current_positions = AsyncMock(return_value={})
    opt._get_idle_capital = AsyncMock(return_value={"USDC": Decimal("100")})
    opt._deploy_idle_capital = AsyncMock(return_value=[])
    opt.optimizer.find_rebalance_opportunities = AsyncMock(return_value=[])


@pytest.mark.asyncio
@pytest.mark.parametrize("liquidity", [None, "30"], ids=["full", "partial"])
async def test_exit_cycle_skips_idle_deploy(fake, tmp_path, caplog, liquidity):
    _trip_share_price(fake)
    if liquidity:
        fake.max_withdraw = usdc(liquidity)
    opt, _, _ = _setup(fake, tmp_path)
    _cycle(opt)

    with caplog.at_level("INFO"):
        await opt._execute_optimization_cycle()

    assert len(_vault_writes(fake)) == 1  # the exit tx was sent
    opt._deploy_idle_capital.assert_not_awaited()
    assert "Skipping idle deploy this cycle" in caplog.text
    opt.optimizer.find_rebalance_opportunities.assert_awaited_once()  # strategy still ran


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["no_liquidity", "reverted", "rpc_error", "dry_run"])
async def test_exit_that_sent_nothing_still_deploys(fake, tmp_path, failure):
    _trip_share_price(fake)
    if failure == "no_liquidity":
        fake.max_withdraw = 0
    elif failure == "reverted":
        fake.receipt_status = 0
    elif failure == "rpc_error":
        fake.set_vault(maxWithdraw=ConnectionError("rpc down"))
    opt, _, _ = _setup(fake, tmp_path, dry_run=(failure == "dry_run"))
    _cycle(opt)

    await opt._execute_optimization_cycle()

    opt._deploy_idle_capital.assert_awaited_once()
    assert opt._emergency_exit_sent is False


@pytest.mark.asyncio
async def test_next_cycle_deploys_normally(fake, tmp_path):
    _trip_share_price(fake)
    opt, _, _ = _setup(fake, tmp_path)
    send = opt.rebalance_executor.protocol_executor.wallet.send_transaction
    send.side_effect = lambda to, data, value: (setattr(fake, "wallet_shares", 0) or "0xexit")
    _cycle(opt)

    await opt._execute_optimization_cycle()
    opt._deploy_idle_capital.assert_not_awaited()

    await opt._execute_optimization_cycle()  # position gone: no exit this time
    opt._deploy_idle_capital.assert_awaited_once()
    assert len(_vault_writes(fake)) == 1


@pytest.mark.asyncio
async def test_exit_flag_reset_each_cycle(fake, tmp_path):
    opt, _, _ = _setup(fake, tmp_path)
    _cycle(opt)
    opt._emergency_exit_sent = True  # left over from a previous cycle

    await opt._execute_optimization_cycle()

    opt._deploy_idle_capital.assert_awaited_once()
    assert opt._emergency_exit_sent is False
