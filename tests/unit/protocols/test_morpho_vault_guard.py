"""Tests for the disk-persisted Morpho vault guard latch and its alerting.

Regression focus (PR #26 review):
- #1 the share-price trip and high-water mark survive a restart (a new
  process / protocol instance), and only an operator reset clears them;
- #3 guard failures surface for alerting once per distinct reason;
- #6 the vault's blocking RPC walk runs off the event loop.
"""

import asyncio
import json
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.protocols.morpho_vault import MorphoVaultProtocol, VaultGuardError
from src.protocols.morpho_vault_guard import VaultGuardStore
from tests.unit.morpho_vault_fakes import MORPHO, SPEC, VAULT, WALLET, FakeWeb3


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "guard.json"


@pytest.fixture
def fake() -> FakeWeb3:
    return FakeWeb3()


def _protocol(fake: FakeWeb3, state_file) -> MorphoVaultProtocol:
    """A fresh instance = a fresh process: nothing carried over in memory."""
    oracle = MagicMock()
    oracle.get_price = AsyncMock(return_value=Decimal("1"))
    with patch("src.protocols.morpho_vault.get_web3", return_value=fake), patch(
        "src.protocols.morpho_vault.get_settings"
    ):
        return MorphoVaultProtocol(
            {
                "network": "base-mainnet",
                "price_oracle": oracle,
                "morpho_vault_guard_state_file": str(state_file),
            }
        )


def _haircut(fake: FakeWeb3, pct: int = 1) -> None:
    fake.share_price = fake.share_price * (100 - pct) // 100


# ===== #1 PERSISTENCE ACROSS RESTARTS =====


@pytest.mark.asyncio
async def test_trip_survives_restart(fake, state_file):
    await _protocol(fake, state_file).get_pools()
    _haircut(fake)
    with pytest.raises(VaultGuardError, match="share price fell"):
        await _protocol(fake, state_file).get_pools()

    # Restart (new instance), share price unchanged or even recovered: still blocked.
    fake.share_price += 10
    with pytest.raises(VaultGuardError, match="share price fell"):
        await _protocol(fake, state_file).get_pools()


@pytest.mark.asyncio
async def test_post_loss_price_never_becomes_baseline_after_restart(fake, state_file):
    """A restart must compare against the persisted pre-loss high-water mark."""
    await _protocol(fake, state_file).get_pools()  # records high-water
    _haircut(fake)
    # First read after the loss happens in a *new* process.
    with pytest.raises(VaultGuardError):
        await _protocol(fake, state_file).get_pools()


@pytest.mark.asyncio
async def test_high_water_persists_and_lag_jitter_tolerated(fake, state_file):
    await _protocol(fake, state_file).get_pools()
    fake.share_price -= 10  # stale replica, < 1bp
    await _protocol(fake, state_file).get_pools()
    record = VaultGuardStore(state_file).snapshot()[VAULT.lower()]
    assert record.high_water_share_price == fake.share_price + 10
    assert record.tripped is False


@pytest.mark.asyncio
async def test_operator_reset_clears_trip_and_rebaselines(fake, state_file):
    await _protocol(fake, state_file).get_pools()
    _haircut(fake)
    with pytest.raises(VaultGuardError):
        await _protocol(fake, state_file).get_pools()

    VaultGuardStore(state_file).reset(SPEC.address)

    pools = await _protocol(fake, state_file).get_pools()
    assert len(pools) == 1
    record = VaultGuardStore(state_file).snapshot()[VAULT.lower()]
    assert record.high_water_share_price == fake.share_price


@pytest.mark.asyncio
async def test_corrupt_state_file_fails_closed(fake, state_file):
    state_file.write_text("{not json")
    with pytest.raises(VaultGuardError, match="unreadable"):
        await _protocol(fake, state_file).get_pools()
    # The corrupt file is left for the operator to inspect, not overwritten.
    assert state_file.read_text() == "{not json"


def test_non_object_state_file_fails_closed(state_file):
    state_file.write_text(json.dumps([1, 2]))
    with pytest.raises(VaultGuardError, match="unreadable"):
        VaultGuardStore(state_file).assert_not_tripped(SPEC.address)


def test_trip_stays_latched_in_process_when_disk_write_fails(state_file, monkeypatch):
    store = VaultGuardStore(state_file)
    store.check_share_price(SPEC.address, SPEC.label, 1_000_000)
    monkeypatch.setattr(store, "_save", lambda records: None)  # disk full
    with pytest.raises(VaultGuardError):
        store.check_share_price(SPEC.address, SPEC.label, 900_000)
    assert not VaultGuardStore(state_file).snapshot()[VAULT.lower()].tripped
    with pytest.raises(VaultGuardError):
        store.assert_not_tripped(SPEC.address)


def test_manual_latch_blocks_and_replaces_corrupt_file(state_file):
    state_file.write_text("garbage")
    VaultGuardStore(state_file).latch(SPEC.address, "operator exit")
    with pytest.raises(VaultGuardError, match="operator exit"):
        VaultGuardStore(state_file).assert_not_tripped(SPEC.address)


@pytest.mark.asyncio
async def test_executor_deposit_refused_by_persisted_latch(fake, state_file):
    """Defense in depth: a latched trip blocks deposits even without a scan."""
    VaultGuardStore(state_file).latch(SPEC.address, "share price fell (test)")
    wallet = MagicMock()
    wallet.get_address = AsyncMock(return_value=WALLET)
    wallet.send_transaction = AsyncMock(return_value="0xhash")
    with patch("src.blockchain.protocol_action_executor.get_web3", return_value=fake), patch(
        "src.blockchain.protocol_action_executor.get_settings"
    ):
        ex = ProtocolActionExecutor(
            wallet,
            {
                "network": "base-mainnet",
                "dry_run_mode": False,
                "morpho_vault_guard_state_file": str(state_file),
            },
        )
    with pytest.raises(VaultGuardError, match="share price fell"):
        await ex.execute_deposit("Morpho", "USDC", Decimal("25"))
    assert fake.built == []

    # Withdrawals stay open while latched.
    fake.wallet_holds("25")
    result = await ex.execute_withdraw("Morpho", "USDC", Decimal("25"))
    assert result["success"] is True


@pytest.mark.asyncio
async def test_executor_deposit_trips_on_drop_below_high_water(fake, state_file):
    VaultGuardStore(state_file).check_share_price(SPEC.address, SPEC.label, fake.share_price)
    _haircut(fake)
    wallet = MagicMock()
    wallet.get_address = AsyncMock(return_value=WALLET)
    with patch("src.blockchain.protocol_action_executor.get_web3", return_value=fake), patch(
        "src.blockchain.protocol_action_executor.get_settings"
    ):
        ex = ProtocolActionExecutor(
            wallet, {"network": "base-mainnet", "morpho_vault_guard_state_file": str(state_file)}
        )
    with pytest.raises(VaultGuardError, match="share price fell"):
        await ex.execute_deposit("Morpho", "USDC", Decimal("25"))
    assert VaultGuardStore(state_file).snapshot()[VAULT.lower()].tripped


# ===== #3 ALERT DEDUPLICATION =====


@pytest.mark.asyncio
async def test_guard_failure_alerts_once_per_reason(fake, state_file):
    proto = _protocol(fake, state_file)
    await proto.get_pools()
    assert proto.pop_guard_alerts() == []

    fake.set_vault(curator="0x000000000000000000000000000000000000dEaD")
    for _ in range(3):
        with pytest.raises(VaultGuardError):
            await proto.get_pools()
    first = proto.pop_guard_alerts()
    assert len(first) == 1 and "curator" in first[0]
    assert proto.pop_guard_alerts() == []

    # Dedupe survives a restart.
    restarted = _protocol(fake, state_file)
    with pytest.raises(VaultGuardError):
        await restarted.get_pools()
    assert restarted.pop_guard_alerts() == []

    # Recovery clears the dedupe, so a later trip alerts again.
    fake.set_vault(curator=SPEC.curator)
    await restarted.get_pools()
    assert restarted.pop_guard_alerts() == []
    fake.set_vault(fee=10**17)
    with pytest.raises(VaultGuardError):
        await restarted.get_pools()
    again = restarted.pop_guard_alerts()
    assert len(again) == 1 and "fee" in again[0]


@pytest.mark.asyncio
async def test_rpc_failure_is_not_a_guard_alert(fake, state_file):
    proto = _protocol(fake, state_file)
    fake.state[MORPHO]["market"] = ConnectionError("rpc down")
    with pytest.raises(ConnectionError):
        await proto.get_pools()
    assert proto.pop_guard_alerts() == []


@pytest.mark.asyncio
async def test_scheduler_sends_critical_alert_once(fake, state_file, tmp_path):
    from tests.unit.agents.test_optimizer_reconcile import _make_optimizer

    proto = _protocol(fake, state_file)
    opt, _ = _make_optimizer(tmp_path, opportunities=[], protocols=[proto])
    opt._alerts = MagicMock()
    opt._alerts.critical = AsyncMock(return_value=True)

    fake.set_vault(owner="0x000000000000000000000000000000000000dEaD")
    for _ in range(2):
        with pytest.raises(VaultGuardError):
            await proto.get_pools()
        await opt._alert_vault_guards()

    opt._alerts.critical.assert_awaited_once()
    title, message = opt._alerts.critical.await_args.args
    assert title == "Morpho vault guard tripped"
    assert "owner" in message and "morpho_vault_exit.py" in message


@pytest.mark.asyncio
async def test_scheduler_alert_tolerates_plain_protocols(tmp_path):
    from tests.unit.agents.test_optimizer_reconcile import _make_optimizer, _proto

    opt, _ = _make_optimizer(tmp_path, opportunities=[], protocols=[_proto("Aave V3", "0")])
    opt._alerts = MagicMock()
    opt._alerts.critical = AsyncMock()
    await opt._alert_vault_guards()
    opt._alerts.critical.assert_not_awaited()


# ===== #6 RPC WALK OFF THE EVENT LOOP =====


@pytest.mark.asyncio
async def test_vault_scan_does_not_block_event_loop(fake, state_file):
    """Blocking web3 calls must not stall concurrent scans (or wait_for).

    Deterministic: the blocking call waits for an event only the event loop
    can set. If the scan ran on the loop thread, the loop could never set it
    and the call would time out.
    """
    import threading

    markets = fake.state[MORPHO]["market"]
    loop_ran = threading.Event()
    blocked = []

    def slow_market(mid):
        if not loop_ran.wait(timeout=5):
            blocked.append(mid)
        return markets(mid)

    fake.state[MORPHO]["market"] = slow_market

    async def ticker():
        while True:
            await asyncio.sleep(0)
            loop_ran.set()

    task = asyncio.create_task(ticker())
    try:
        await _protocol(fake, state_file).get_pools()
    finally:
        task.cancel()
    assert blocked == [], "event loop was blocked during the vault scan"


@pytest.mark.asyncio
async def test_vault_scan_honours_wait_for_timeout(fake, state_file):
    import threading

    release = threading.Event()
    fake.state[MORPHO]["market"] = lambda mid: release.wait(timeout=10)
    proto = _protocol(fake, state_file)
    start = time.monotonic()
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(proto.get_pools(), timeout=0.1)
        assert time.monotonic() - start < 5
    finally:
        release.set()  # let the worker thread finish
