"""Unit tests for Morpho vault execution in ProtocolActionExecutor.

Uses the fake chain from tests/unit/morpho_vault_fakes.py; every write is
recorded in FakeWeb3.built as (to, function, args), so tests assert exactly
which calls would be broadcast.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.blockchain.rebalance_executor import RebalanceExecution, RebalanceExecutor
from src.protocols.morpho_vault import VaultGuardError
from src.strategies.base_strategy import RebalanceRecommendation
from tests.unit.morpho_vault_fakes import USDC, VAULT, WALLET, FakeWeb3, usdc


@pytest.fixture
def fake() -> FakeWeb3:
    return FakeWeb3()


def _executor(fake: FakeWeb3, dry_run: bool = False, **config) -> ProtocolActionExecutor:
    wallet = MagicMock()
    wallet.get_address = AsyncMock(return_value=WALLET)
    wallet.send_transaction = AsyncMock(side_effect=lambda to, data, value: f"0xhash_{len(fake.built)}")
    with patch("src.blockchain.protocol_action_executor.get_web3", return_value=fake), patch(
        "src.blockchain.protocol_action_executor.get_settings"
    ):
        ex = ProtocolActionExecutor(
            wallet, {"network": "base-mainnet", "dry_run_mode": dry_run, **config}
        )
    ex.audit_logger = MagicMock()
    ex.audit_logger.log_event = AsyncMock()
    return ex


def _writes(fake: FakeWeb3):
    return [(to, name) for to, name, _ in fake.built]


# ===== DEPOSIT =====


@pytest.mark.asyncio
async def test_deposit_approves_exact_amount_then_deposits(fake):
    ex = _executor(fake)
    result = await ex.execute_deposit("Morpho", "USDC", Decimal("25.5"))

    assert result["success"] is True
    assert result["protocol"] == "Morpho"
    assert result["action"] == "deposit"
    assert _writes(fake) == [(USDC, "approve"), (VAULT, "deposit")]
    approve_args = fake.built[0][2]
    deposit_args = fake.built[1][2]
    # Exact-amount approval to the vault, never max-uint.
    assert approve_args == (VAULT, usdc("25.5"))
    assert deposit_args == (usdc("25.5"), WALLET)
    ex.audit_logger.log_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_deposit_skips_approval_when_allowance_suffices(fake):
    fake.allowance = usdc("100")
    await _executor(fake).execute_deposit("Morpho", "USDC", Decimal("25"))
    assert _writes(fake) == [(VAULT, "deposit")]


@pytest.mark.asyncio
async def test_deposit_blocked_by_guard_before_any_write(fake):
    fake.set_vault(owner="0x000000000000000000000000000000000000dEaD")
    with pytest.raises(VaultGuardError):
        await _executor(fake).execute_deposit("Morpho", "USDC", Decimal("25"))
    assert fake.built == []


@pytest.mark.asyncio
async def test_deposit_guard_uses_configured_fee_ceiling(fake):
    fake.set_vault(fee=int(Decimal("0.03") * 10**18))
    with pytest.raises(VaultGuardError, match="fee"):
        await _executor(fake, morpho_vault_max_fee=Decimal("0.01")).execute_deposit(
            "Morpho", "USDC", Decimal("25")
        )


@pytest.mark.asyncio
async def test_deposit_refused_above_max_deposit(fake):
    fake.max_deposit = usdc("10")
    with pytest.raises(ValueError, match="maxDeposit"):
        await _executor(fake).execute_deposit("Morpho", "USDC", Decimal("25"))
    assert fake.built == []


@pytest.mark.asyncio
async def test_deposit_rejects_non_positive_amount(fake):
    with pytest.raises(ValueError):
        await _executor(fake).execute_deposit("Morpho", "USDC", Decimal("0"))


@pytest.mark.asyncio
async def test_deposit_unknown_token_has_no_vault(fake):
    with pytest.raises(ValueError, match="No Morpho vault"):
        await _executor(fake).execute_deposit("Morpho", "WETH", Decimal("1"))


@pytest.mark.asyncio
async def test_deposit_dry_run_checks_guard_but_sends_nothing(fake):
    ex = _executor(fake, dry_run=True)
    result = await ex.execute_deposit("Morpho", "USDC", Decimal("25"))
    assert result == {
        "success": True,
        "tx_hash": "0xdryrun_deposit_morpho_USDC",
        "gas_used": 300000,
        "dry_run": True,
    }
    assert fake.built == []
    ex.wallet.send_transaction.assert_not_awaited()

    fake.set_vault(timelock=0)
    with pytest.raises(VaultGuardError):
        await ex.execute_deposit("Morpho", "USDC", Decimal("25"))


@pytest.mark.asyncio
async def test_deposit_reports_reverted_tx(fake):
    fake.allowance = usdc("100")
    fake.receipt_status = 0
    result = await _executor(fake).execute_deposit("Morpho", "USDC", Decimal("25"))
    assert result["success"] is False


@pytest.mark.asyncio
async def test_deposit_stops_when_approval_reverts(fake):
    fake.receipt_status = 0
    result = await _executor(fake).execute_deposit("Morpho", "USDC", Decimal("25"))
    assert result["success"] is False
    assert result["error"] == "Approval transaction failed"
    assert _writes(fake) == [(USDC, "approve")]


# ===== WITHDRAW =====


@pytest.mark.asyncio
async def test_partial_withdraw_uses_exact_assets(fake):
    fake.wallet_holds("100")
    result = await _executor(fake).execute_withdraw("Morpho", "USDC", Decimal("40"))

    assert result["success"] is True
    assert result["mode"] == "withdraw"
    assert fake.built == [(VAULT, "withdraw", (usdc("40"), WALLET, WALLET))]


@pytest.mark.asyncio
async def test_full_amount_redeems_every_share(fake):
    fake.wallet_holds("100")
    shares = fake.wallet_shares
    result = await _executor(fake).execute_withdraw("Morpho", "USDC", Decimal("100"))

    assert result["mode"] == "redeem"
    assert fake.built == [(VAULT, "redeem", (shares, WALLET, WALLET))]


@pytest.mark.asyncio
async def test_amount_within_dust_of_position_redeems(fake):
    """A tracked value that lags accrued interest still exits fully (no dust)."""
    fake.wallet_holds("100.05")
    result = await _executor(fake).execute_withdraw("Morpho", "USDC", Decimal("100"))
    assert result["mode"] == "redeem"


@pytest.mark.asyncio
async def test_stale_amount_above_balance_redeems_instead_of_reverting(fake):
    fake.wallet_holds("99")
    result = await _executor(fake).execute_withdraw("Morpho", "USDC", Decimal("107.79"))
    assert result["mode"] == "redeem"
    assert _writes(fake) == [(VAULT, "redeem")]


@pytest.mark.asyncio
async def test_withdraw_refused_when_vault_lacks_liquidity(fake):
    fake.wallet_holds("100")
    fake.max_withdraw = usdc("30")
    with pytest.raises(ValueError, match="liquidity"):
        await _executor(fake).execute_withdraw("Morpho", "USDC", Decimal("40"))
    assert fake.built == []


@pytest.mark.asyncio
async def test_withdraw_without_shares_raises(fake):
    with pytest.raises(ValueError, match="No .* shares"):
        await _executor(fake).execute_withdraw("Morpho", "USDC", Decimal("10"))


@pytest.mark.asyncio
async def test_withdraw_rejects_non_positive_amount(fake):
    fake.wallet_holds("100")
    with pytest.raises(ValueError):
        await _executor(fake).execute_withdraw("Morpho", "USDC", Decimal("0"))


@pytest.mark.asyncio
async def test_withdraw_not_gated_by_guard(fake):
    """Exits must always work, even if the curator changed."""
    fake.wallet_holds("100")
    fake.set_vault(curator="0x000000000000000000000000000000000000dEaD", fee=10**18)
    result = await _executor(fake).execute_withdraw("Morpho", "USDC", Decimal("100"))
    assert result["success"] is True


@pytest.mark.asyncio
async def test_withdraw_dry_run_sends_nothing(fake):
    fake.wallet_holds("100")
    ex = _executor(fake, dry_run=True)
    result = await ex.execute_withdraw("Morpho", "USDC", Decimal("40"))
    assert result["dry_run"] is True
    assert result["mode"] == "withdraw"
    assert result["tx_hash"] == "0xdryrun_withdraw_morpho_USDC"
    assert fake.built == []


# ===== REBALANCE EXECUTOR APPROVAL SPENDER =====


def _rebalancer(wallet_usdc: str = "1000"):
    protocol_executor = MagicMock()
    protocol_executor.execute_approve = AsyncMock(return_value={"success": True, "tx_hash": "0xa"})
    protocol_executor.execute_deposit = AsyncMock(return_value={"success": True, "tx_hash": "0xd"})
    protocol_executor.get_token_balance = AsyncMock(return_value=Decimal(wallet_usdc))
    ex = RebalanceExecutor(
        wallet_manager=MagicMock(),
        protocol_executor=protocol_executor,
        gas_estimator=MagicMock(),
        price_oracle=MagicMock(),
        config={"network": "base-mainnet", "dry_run_mode": True},
    )
    return ex, protocol_executor


def _rec(amount: str = "50", from_protocol="Moonwell", to_protocol="Morpho"):
    return RebalanceRecommendation(
        from_protocol=from_protocol,
        to_protocol=to_protocol,
        token="USDC",
        amount=Decimal(amount),
        expected_apy=Decimal("5"),
        reason="test",
        confidence=80,
    )


@pytest.mark.asyncio
async def test_rebalance_approves_the_vault_for_morpho_target():
    ex, protocol_executor = _rebalancer()

    await ex._execute_approve_deposit_step(_rec(), MagicMock(spec=RebalanceExecution))

    protocol_executor.execute_approve.assert_awaited_once_with(
        token="USDC", spender=VAULT, amount=Decimal("50")
    )


@pytest.mark.asyncio
async def test_rebalance_deposits_balance_when_redeem_returned_dust_less():
    """A full-exit redeem 1 wei short must not make the exact deposit revert."""
    ex, protocol_executor = _rebalancer(wallet_usdc="49.999999")

    await ex._execute_deposit_step(_rec(from_protocol="Morpho", to_protocol="Moonwell"),
                                   MagicMock(spec=RebalanceExecution))

    protocol_executor.execute_deposit.assert_awaited_once_with(
        protocol_name="Moonwell", token="USDC", amount=Decimal("49.999999")
    )


@pytest.mark.asyncio
async def test_rebalance_keeps_amount_on_real_shortfall():
    """More than dust missing: deposit the recommended amount and fail loudly."""
    ex, protocol_executor = _rebalancer(wallet_usdc="45")

    assert await ex._deposit_amount(_rec()) == Decimal("50")


@pytest.mark.asyncio
async def test_rebalance_idle_deploy_skips_balance_clamp():
    ex, protocol_executor = _rebalancer(wallet_usdc="49.999999")

    assert await ex._deposit_amount(_rec(from_protocol=None)) == Decimal("50")
    protocol_executor.get_token_balance.assert_not_awaited()
