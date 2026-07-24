"""Portfolio valuation must count idle balances, not just deployed positions.

The runner previously valued the portfolio as ETH + DeFi positions only. With
capital sitting idle as USDC, the reported portfolio was far below reality and
deploying that capital looked like pure profit (a real run reported
"P&L: $24.20 (317.64%)" for what was actually a bucket transfer).
"""

from decimal import Decimal

import pytest

from scripts.run_autonomous_optimizer import AutonomousRunner


class _FakeWallet:
    address = "0xE06860747338660a0474b81E401BE60aeCf96f91"

    def __init__(self, eth: Decimal, usdc: Decimal) -> None:
        self._balances = {"ETH": eth, "USDC": usdc}

    async def get_balance(self, token: str = "ETH") -> Decimal:
        return self._balances[token]


class _FakeOracle:
    async def get_price(self, token: str, quote: str = "USD") -> Decimal:
        return {"ETH": Decimal("2000"), "USDC": Decimal("1")}[token]


class _FakePosition:
    def __init__(self, value_usd: Decimal) -> None:
        self.protocol = "Moonwell"
        self.pool_id = "moonwell-usdc"
        self.value_usd = value_usd


class _FakeTracker:
    def __init__(self, positions) -> None:
        self._positions = positions
        self.asked_wallet = None

    async def get_current_positions(self, wallet_address=None):
        self.asked_wallet = wallet_address
        return self._positions


def _runner(eth, usdc, positions):
    runner = AutonomousRunner(duration_hours=1.0, dry_run=True)
    runner.wallet = _FakeWallet(Decimal(eth), Decimal(usdc))
    runner.oracle = _FakeOracle()
    runner.position_tracker = _FakeTracker(positions)
    return runner


@pytest.mark.asyncio
async def test_idle_usdc_is_counted():
    # 0.004 ETH ($8) + 102.57 idle USDC + nothing deployed.
    runner = _runner("0.004", "102.57", [])
    snap = await runner._portfolio_snapshot()

    assert snap["usdc_value_usd"] == Decimal("102.57")
    assert snap["total_usd"] == Decimal("110.57")  # 8 + 102.57


@pytest.mark.asyncio
async def test_deploying_idle_capital_is_not_profit():
    """Moving USDC into a position must leave total portfolio value flat."""
    before = await _runner("0.004", "102.57", [])._portfolio_snapshot()

    # $25 of the idle USDC is now deployed into Moonwell.
    after = await _runner(
        "0.004", "77.57", [_FakePosition(Decimal("25.00"))]
    )._portfolio_snapshot()

    assert before["total_usd"] == after["total_usd"] == Decimal("110.57")
    # Under the old ETH+positions-only basis this looked like $8 -> $33.
    pnl = after["total_usd"] - before["total_usd"]
    assert pnl == Decimal("0")


@pytest.mark.asyncio
async def test_positions_scoped_to_current_wallet():
    """Stale rows from a previous wallet must not inflate the portfolio."""
    runner = _runner("0.004", "0", [])
    await runner._portfolio_snapshot()
    assert runner.position_tracker.asked_wallet == _FakeWallet.address
