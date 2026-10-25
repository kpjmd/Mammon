"""Unit tests for the allowlisted Morpho vault (MetaMorpho, ERC-4626) protocol.

Chain state comes from tests/unit/morpho_vault_fakes.py: three markets (idle,
B at 4.5% supply APR, C at 7.2% supply APR) with the vault holding ~500 in B
and ~100 in C, so the allocation-weighted gross APR is ~4.95%.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.protocols.morpho_vault import (
    MORPHO_VAULTS,
    MorphoVaultProtocol,
    VaultGuardError,
    get_vault_spec,
    supply_apr_percent,
    to_assets_down,
    verify_vault_config,
)
from tests.unit.morpho_vault_fakes import (
    MORPHO,
    SPEC,
    WALLET,
    FakeWeb3,
    rate_for_apr,
    usdc,
)

APPROX = Decimal("0.0001")


def _protocol(fake: FakeWeb3, **config) -> MorphoVaultProtocol:
    oracle = MagicMock()
    oracle.get_price = AsyncMock(return_value=Decimal("1"))
    with patch("src.protocols.morpho_vault.get_web3", return_value=fake), patch(
        "src.protocols.morpho_vault.get_settings"
    ):
        return MorphoVaultProtocol({"network": "base-mainnet", "price_oracle": oracle, **config})


@pytest.fixture
def fake() -> FakeWeb3:
    return FakeWeb3()


# ===== PINNED ALLOWLIST =====


def test_allowlist_pins_gauntlet_usdc_prime():
    spec = get_vault_spec("USDC")
    assert spec.address == "0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61"
    assert spec.asset == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    assert spec.morpho == "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
    assert spec.curator == "0x9E33faAE38ff641094fa68c65c2cE600b3410585"
    assert spec.owner == "0x5a4E19842e09000a582c20A4f524C26Fb48Dd4D0"
    assert list(MORPHO_VAULTS) == ["base-mainnet"]


def test_unknown_token_or_network_has_no_vault():
    with pytest.raises(ValueError):
        get_vault_spec("WETH")
    with pytest.raises(ValueError):
        get_vault_spec("USDC", "base-sepolia")


# ===== MATH =====


def test_to_assets_down_uses_virtual_shares():
    assert to_assets_down(usdc("500") * 10**6, usdc("1000"), usdc("1000") * 10**6) == usdc("500")
    # Virtual shares dominate a tiny market: 1 share of 1 over 1 asset rounds to 0.
    assert to_assets_down(1, 1, 1) == 0
    assert to_assets_down(0, 0, 0) == 0


def test_supply_apr_applies_utilization_and_market_fee():
    apr = supply_apr_percent(rate_for_apr("10"), usdc("100"), usdc("80"), int(Decimal("0.1") * 10**18))
    assert abs(apr - Decimal("7.2")) < APPROX


def test_supply_apr_zero_for_empty_market_or_zero_rate():
    assert supply_apr_percent(rate_for_apr("5"), 0, 0, 0) == 0
    assert supply_apr_percent(0, usdc("100"), usdc("50"), 0) == 0


# ===== GUARD =====


def test_guard_passes_on_pinned_state(fake):
    snap = verify_vault_config(fake, SPEC)
    assert snap.fee == 0
    assert snap.timelock == 604800
    assert snap.total_assets == usdc("600")


@pytest.mark.parametrize("getter", ["asset", "MORPHO", "curator", "owner"])
def test_guard_rejects_changed_identity(fake, getter):
    fake.set_vault(**{getter: "0x000000000000000000000000000000000000dEaD"})
    with pytest.raises(VaultGuardError, match=getter):
        verify_vault_config(fake, SPEC)


def test_guard_rejects_short_timelock(fake):
    fake.set_vault(timelock=86400)
    with pytest.raises(VaultGuardError, match="timelock"):
        verify_vault_config(fake, SPEC)


def test_guard_rejects_fee_above_ceiling(fake):
    fake.set_vault(fee=int(Decimal("0.10") * 10**18))
    with pytest.raises(VaultGuardError, match="fee"):
        verify_vault_config(fake, SPEC, max_fee=Decimal("0.05"))


def test_guard_accepts_fee_at_ceiling(fake):
    fake.set_vault(fee=int(Decimal("0.05") * 10**18))
    assert verify_vault_config(fake, SPEC, max_fee=Decimal("0.05")).fee == Decimal("0.05")


# ===== get_pools =====


@pytest.mark.asyncio
async def test_get_pools_returns_weighted_net_apy(fake):
    pools = await _protocol(fake).get_pools()

    assert len(pools) == 1
    pool = pools[0]
    assert pool.pool_id == "morpho-vault-gtusdcp"
    assert pool.tokens == ["USDC"]
    # (4.5% * ~500 + 7.2% * ~100) / ~600
    assert abs(pool.apy - Decimal("4.95")) < Decimal("0.001")
    assert pool.tvl == Decimal("600")
    md = pool.metadata
    assert md["vault_address"] == SPEC.address
    assert md["curator"] == SPEC.curator
    # Liquidity: B min(~500, 100 free) + C min(~100, 20 free)
    assert md["liquidity"] == Decimal("120")
    # Idle market (0 assets) omitted from the allocation summary.
    assert len(md["allocations"]) == 2


@pytest.mark.asyncio
async def test_get_pools_applies_vault_fee(fake):
    fake.set_vault(fee=int(Decimal("0.02") * 10**18))
    pool = (await _protocol(fake).get_pools())[0]
    assert abs(pool.apy - Decimal("4.95") * Decimal("0.98")) < Decimal("0.001")
    assert abs(pool.metadata["gross_apy"] - Decimal("4.95")) < Decimal("0.001")


@pytest.mark.asyncio
async def test_get_pools_fails_closed_on_guard(fake):
    fake.set_vault(curator="0x000000000000000000000000000000000000dEaD")
    with pytest.raises(VaultGuardError):
        await _protocol(fake).get_pools()


@pytest.mark.asyncio
async def test_get_pools_fails_closed_on_rpc_error(fake):
    fake.state[MORPHO]["market"] = ConnectionError("rpc down")
    with pytest.raises(ConnectionError):
        await _protocol(fake).get_pools()


@pytest.mark.asyncio
async def test_get_pools_uses_configured_guard_bounds(fake):
    fake.set_vault(timelock=3 * 86400)
    proto = _protocol(fake, morpho_vault_min_timelock_seconds=2 * 86400)
    assert len(await proto.get_pools()) == 1


@pytest.mark.asyncio
async def test_oracle_failure_falls_back_to_one_dollar_tvl(fake):
    proto = _protocol(fake)
    proto.price_oracle.get_price = AsyncMock(side_effect=RuntimeError("stale"))
    assert (await proto.get_pools())[0].tvl == Decimal("600")


@pytest.mark.asyncio
async def test_mock_mode_never_touches_chain():
    with patch("src.protocols.morpho_vault.get_web3") as gw:
        proto = MorphoVaultProtocol({"use_mock_data": True, "chainlink_enabled": False})
    gw.assert_not_called()
    pools = await proto.get_pools()
    assert pools[0].metadata["mock"] is True
    assert await proto.get_user_balance(SPEC.pool_id, WALLET) == 0


# ===== SHARE-PRICE TRIPWIRE =====


@pytest.mark.asyncio
async def test_share_price_rise_and_lag_jitter_do_not_trip(fake):
    proto = _protocol(fake)
    await proto.get_pools()
    fake.share_price += 1000  # interest accrued
    await proto.get_pools()
    fake.share_price -= 10  # stale replica a few blocks behind (<1bp)
    await proto.get_pools()


@pytest.mark.asyncio
async def test_share_price_drop_trips_and_stays_tripped(fake):
    proto = _protocol(fake)
    await proto.get_pools()
    fake.share_price = fake.share_price * 99 // 100  # 1% bad-debt haircut
    with pytest.raises(VaultGuardError, match="share price fell"):
        await proto.get_pools()
    fake.share_price = fake.share_price * 2  # recovers: still blocked
    with pytest.raises(VaultGuardError, match="share price fell"):
        await proto.get_pools()


# ===== BALANCE =====


@pytest.mark.asyncio
async def test_user_balance_converts_shares_to_assets(fake):
    fake.wallet_holds("107.79")
    balance = await _protocol(fake).get_user_balance(SPEC.pool_id, WALLET)
    assert Decimal("107.79") <= balance < Decimal("107.791")


@pytest.mark.asyncio
async def test_user_balance_zero_without_shares(fake):
    assert await _protocol(fake).get_user_balance(SPEC.pool_id, WALLET) == 0


@pytest.mark.asyncio
async def test_user_balance_raises_on_rpc_error(fake):
    """A failed read must raise (reconcile = unchecked), never read as 0 (= close)."""
    fake.set_vault(balanceOf=ConnectionError("rpc down"))
    with pytest.raises(ConnectionError):
        await _protocol(fake).get_user_balance(SPEC.pool_id, WALLET)


@pytest.mark.asyncio
async def test_user_balance_rejects_unknown_pool(fake):
    with pytest.raises(ValueError):
        await _protocol(fake).get_user_balance("morpho-usdc-weth", WALLET)


# ===== MISC =====


@pytest.mark.asyncio
async def test_get_pool_apy(fake):
    proto = _protocol(fake)
    assert abs(await proto.get_pool_apy(SPEC.pool_id) - Decimal("4.95")) < Decimal("0.001")
    with pytest.raises(ValueError):
        await proto.get_pool_apy("nope")


@pytest.mark.asyncio
async def test_protocol_is_read_only(fake):
    proto = _protocol(fake)
    with pytest.raises(NotImplementedError):
        await proto.deposit(SPEC.pool_id, "USDC", Decimal("1"))
    with pytest.raises(NotImplementedError):
        await proto.withdraw(SPEC.pool_id, "USDC", Decimal("1"))


@pytest.mark.asyncio
async def test_identity_and_gas(fake):
    proto = _protocol(fake)
    assert proto.name == "Morpho"
    assert proto.safety_score == 85
    assert "Gauntlet USDC Prime" in repr(proto)
    assert await proto.estimate_gas("deposit", {}) == 300000
    assert await proto.estimate_gas("unknown", {}) == 350000


# ===== RECONCILE INTEGRATION =====


@pytest.mark.asyncio
async def test_reconcile_records_vault_position(fake, tmp_path):
    """reconcile_positions reads the vault balance via the real protocol class."""
    from tests.unit.agents.test_optimizer_reconcile import WALLET as RECON_WALLET
    from tests.unit.agents.test_optimizer_reconcile import _make_optimizer, _opp

    fake.wallet_holds("107.79")
    proto = _protocol(fake)
    opt, tracker = _make_optimizer(
        tmp_path,
        opportunities=[_opp("Morpho", SPEC.pool_id, apy="4.4")],
        protocols=[proto],
    )
    await opt.reconcile_positions()

    rows = await tracker.get_current_positions(wallet_address=RECON_WALLET)
    assert [(r.protocol, r.pool_id, r.token) for r in rows] == [("Morpho", SPEC.pool_id, "USDC")]
    assert Decimal("107.79") <= rows[0].amount < Decimal("107.791")
