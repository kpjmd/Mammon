"""End-to-end Morpho vault test against a local anvil fork of Base mainnet.

Drives the real ProtocolActionExecutor (live mode, real calldata, real
receipts) and the real MorphoVaultProtocol balance read through deposit,
partial withdraw and full-exit redeem against the pinned Gauntlet USDC Prime
vault's actual on-chain state. Nothing touches mainnet: transactions go to the
fork from an anvil-unlocked dev account funded via anvil_setStorageAt.

Skipped unless MAMMON_FORK_RPC_URL points at a running fork:

    anvil --fork-url https://mainnet.base.org --port 8546
    MAMMON_FORK_RPC_URL=http://127.0.0.1:8546 \
        poetry run pytest tests/integration/test_morpho_vault_fork.py -o addopts="" -v
"""

import os
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from web3 import Web3

from src.blockchain.protocol_action_executor import ERC20_ABI, ProtocolActionExecutor
from src.protocols.morpho_vault import MorphoVaultProtocol, get_vault_spec

FORK_RPC = os.environ.get("MAMMON_FORK_RPC_URL")
pytestmark = pytest.mark.skipif(not FORK_RPC, reason="MAMMON_FORK_RPC_URL not set")

# anvil's first default dev account (unlocked on every anvil instance).
DEV_ACCOUNT = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
# FiatTokenV2_2 `balanceAndBlacklistStates` mapping slot (verified with cast:
# storage(USDC, keccak(holder . 9)) == balanceOf(holder) on Base).
USDC_BALANCE_SLOT = 9
SPEC = get_vault_spec("USDC")


class AnvilWallet:
    """Minimal WalletManager stand-in that signs via anvil's unlocked account."""

    def __init__(self, w3: Web3, address: str) -> None:
        self.w3 = w3
        self.address = address

    async def get_address(self) -> str:
        return self.address

    async def send_transaction(self, to: str, data: str, value: Decimal) -> str:
        tx_hash = self.w3.eth.send_transaction(
            {"from": self.address, "to": Web3.to_checksum_address(to), "data": data, "value": 0}
        )
        return "0x" + tx_hash.hex().removeprefix("0x")


def _fund_usdc(w3: Web3, holder: str, amount_raw: int) -> None:
    slot = Web3.solidity_keccak(
        ["uint256", "uint256"], [int(holder, 16), USDC_BALANCE_SLOT]
    )
    w3.provider.make_request(
        "anvil_setStorageAt",
        [SPEC.asset, "0x" + slot.hex().removeprefix("0x"), "0x" + amount_raw.to_bytes(32, "big").hex()],
    )


def _usdc_balance(w3: Web3, holder: str) -> Decimal:
    usdc = w3.eth.contract(address=SPEC.asset, abi=ERC20_ABI)
    return Decimal(usdc.functions.balanceOf(holder).call()) / Decimal(10**6)


@pytest.fixture
def fork() -> Any:
    w3 = Web3(Web3.HTTPProvider(FORK_RPC))
    assert w3.is_connected(), f"no fork at {FORK_RPC}"
    snapshot = w3.provider.make_request("evm_snapshot", [])["result"]
    yield w3
    w3.provider.make_request("evm_revert", [snapshot])


def _build(w3: Web3):
    with patch("src.blockchain.protocol_action_executor.get_web3", return_value=w3), patch(
        "src.blockchain.protocol_action_executor.get_settings"
    ), patch("src.protocols.morpho_vault.get_web3", return_value=w3), patch(
        "src.protocols.morpho_vault.get_settings"
    ):
        executor = ProtocolActionExecutor(
            AnvilWallet(w3, DEV_ACCOUNT), {"network": "base-mainnet", "dry_run_mode": False}
        )
        protocol = MorphoVaultProtocol({"network": "base-mainnet", "chainlink_enabled": False})
    return executor, protocol


@pytest.mark.asyncio
async def test_pool_reads_real_vault_state(fork):
    _, protocol = _build(fork)
    pool = (await protocol.get_pools())[0]
    assert pool.pool_id == SPEC.pool_id
    assert Decimal("0.5") < pool.apy < Decimal("25")
    assert pool.tvl > Decimal("1_000_000")
    assert pool.metadata["liquidity"] > Decimal("1000")


@pytest.mark.asyncio
async def test_deposit_partial_withdraw_full_redeem(fork):
    executor, protocol = _build(fork)
    _fund_usdc(fork, DEV_ACCOUNT, 1000 * 10**6)
    start = _usdc_balance(fork, DEV_ACCOUNT)
    assert start == Decimal("1000")

    dep = await executor.execute_deposit("Morpho", "USDC", Decimal("100"))
    assert dep["success"], dep
    held = await protocol.get_user_balance(SPEC.pool_id, DEV_ACCOUNT)
    # ERC-4626 rounds against the depositor by at most a wei or two.
    assert Decimal("99.999998") <= held <= Decimal("100")
    assert _usdc_balance(fork, DEV_ACCOUNT) == Decimal("900")
    # Exact-amount approval: nothing left standing after the deposit.
    usdc = fork.eth.contract(address=SPEC.asset, abi=ERC20_ABI + [{
        "inputs": [{"name": "o", "type": "address"}, {"name": "s", "type": "address"}],
        "name": "allowance", "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view", "type": "function",
    }])
    assert usdc.functions.allowance(DEV_ACCOUNT, SPEC.address).call() == 0

    part = await executor.execute_withdraw("Morpho", "USDC", Decimal("40"))
    assert part["success"] and part["mode"] == "withdraw", part
    assert _usdc_balance(fork, DEV_ACCOUNT) == Decimal("940")
    remaining = await protocol.get_user_balance(SPEC.pool_id, DEV_ACCOUNT)
    assert Decimal("59.99999") <= remaining <= Decimal("60")

    # A tracked value slightly above the real balance (stale) still exits fully.
    full = await executor.execute_withdraw("Morpho", "USDC", Decimal("60.05"))
    assert full["success"] and full["mode"] == "redeem", full
    assert await protocol.get_user_balance(SPEC.pool_id, DEV_ACCOUNT) == 0
    end = _usdc_balance(fork, DEV_ACCOUNT)
    assert start - Decimal("0.00001") <= end <= start + Decimal("0.01")


def _rec(from_protocol, to_protocol, amount: str):
    from src.strategies.base_strategy import RebalanceRecommendation

    return RebalanceRecommendation(
        from_protocol=from_protocol,
        to_protocol=to_protocol,
        token="USDC",
        amount=Decimal(amount),
        expected_apy=Decimal("5"),
        reason="fork e2e",
        confidence=90,
    )


@pytest.mark.asyncio
async def test_rebalance_executor_idle_to_vault_then_vault_to_moonwell(fork):
    """The live loop's path: RebalanceExecutor drives approve/deposit/withdraw.

    The wallet holds exactly the deployed amount, so the vault→Moonwell leg
    only succeeds if the deposit is clamped to what the full-exit redeem
    actually returned (a wei or two under the tracked amount).
    """
    from unittest.mock import AsyncMock, MagicMock

    from src.blockchain.rebalance_executor import RebalanceExecutor

    executor, protocol = _build(fork)
    gas = MagicMock()
    gas.get_gas_price = AsyncMock(return_value=10**7)
    oracle = MagicMock()
    oracle.get_price = AsyncMock(return_value=Decimal("3000"))
    rebalancer = RebalanceExecutor(
        wallet_manager=MagicMock(),
        protocol_executor=executor,
        gas_estimator=gas,
        price_oracle=oracle,
        config={
            "network": "base-mainnet",
            "dry_run_mode": False,
            "max_transaction_value_usd": "1000",
            "daily_spending_limit_usd": "5000",
        },
    )
    _fund_usdc(fork, DEV_ACCOUNT, 50 * 10**6)

    deploy = await rebalancer.execute_rebalance(_rec(None, "Morpho", "50"))
    assert deploy.success, [s.error for s in deploy.steps]
    assert _usdc_balance(fork, DEV_ACCOUNT) == 0
    held = await protocol.get_user_balance(SPEC.pool_id, DEV_ACCOUNT)
    assert Decimal("49.99999") <= held <= Decimal("50")

    move = await rebalancer.execute_rebalance(_rec("Morpho", "Moonwell", "50"))
    assert move.success, [s.error for s in move.steps]
    assert await protocol.get_user_balance(SPEC.pool_id, DEV_ACCOUNT) == 0
    assert _usdc_balance(fork, DEV_ACCOUNT) == 0  # everything landed in Moonwell
