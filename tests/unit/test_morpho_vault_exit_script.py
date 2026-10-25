"""Tests for scripts/morpho_vault_exit.py (manual full exit of the vault)."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import scripts.morpho_vault_exit as exit_script


def _patched(position: str):
    wallet = MagicMock()
    wallet.address = "0xE06860747338660a0474b81E401BE60aeCf96f91"
    wallet.initialize = AsyncMock()
    executor = MagicMock()
    executor.execute_withdraw = AsyncMock(return_value={"success": True, "mode": "redeem"})
    protocol = MagicMock()
    protocol.get_user_balance = AsyncMock(return_value=Decimal(position))
    patches = [
        patch.object(exit_script, "WalletManager", return_value=wallet),
        patch.object(exit_script, "ProtocolActionExecutor", return_value=executor),
        patch.object(exit_script, "MorphoVaultProtocol", return_value=protocol),
    ]
    return patches, executor


async def _run(position: str, live: bool, typed: str = ""):
    patches, executor = _patched(position)
    for p in patches:
        p.start()
    try:
        with patch("builtins.input", return_value=typed) as prompt:
            code = await exit_script.main(live)
    finally:
        for p in patches:
            p.stop()
    return code, executor, prompt


@pytest.mark.asyncio
async def test_dry_run_requests_full_redeem_without_prompt():
    code, executor, prompt = await _run("107.79", live=False)
    assert code == 0
    prompt.assert_not_called()
    executor.execute_withdraw.assert_awaited_once_with("Morpho", "USDC", Decimal("108.79"))


@pytest.mark.asyncio
async def test_live_requires_exact_confirmation():
    code, executor, _ = await _run("107.79", live=True, typed="yes")
    assert code == 1
    executor.execute_withdraw.assert_not_awaited()

    code, executor, _ = await _run("107.79", live=True, typed=exit_script.CONFIRMATION)
    assert code == 0
    executor.execute_withdraw.assert_awaited_once()


@pytest.mark.asyncio
async def test_nothing_to_exit():
    code, executor, _ = await _run("0", live=True)
    assert code == 0
    executor.execute_withdraw.assert_not_awaited()
