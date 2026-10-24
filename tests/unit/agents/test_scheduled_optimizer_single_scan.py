"""One protocol scan per optimization cycle.

The 3-month live run showed every cycle scanning all protocols twice — once in
reconcile_positions() and once in OptimizerAgent.find_rebalance_opportunities()
— doubling every protocol API/RPC call and error line. The cycle now scans once
and shares the result with both.

Uses the real OptimizerAgent (mock strategy) and a real on-disk PositionTracker
so the count covers both consumers end to end.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.agents.optimizer import OptimizerAgent
from src.agents.scheduled_optimizer import ScheduledOptimizer
from src.agents.yield_scanner import YieldOpportunity
from src.data.models import Position
from src.data.position_tracker import PositionTracker

WALLET = "0xAAAA000000000000000000000000000000000001"


def _opp(protocol, pool_id, apy="5"):
    return YieldOpportunity(
        protocol=protocol,
        pool_id=pool_id,
        pool_name=f"{protocol} USDC",
        apy=Decimal(apy),
        tvl=Decimal("1000000"),
        tokens=["USDC"],
    )


def _proto(name, balance):
    p = MagicMock()
    p.name = name
    p.get_user_balance = AsyncMock(return_value=Decimal(str(balance)))
    return p


def _scanner(opportunities, protocols):
    scanner = MagicMock()
    scanner.protocols = protocols
    scanner.scan_all_protocols = AsyncMock(return_value=opportunities)
    scanner.price_oracle = MagicMock()
    scanner.price_oracle.get_price = AsyncMock(return_value=Decimal("1"))
    return scanner


def _optimizer_agent(scanner):
    strategy = MagicMock()
    strategy.name = "test"
    strategy.last_rejections = []
    strategy.analyze_opportunities = AsyncMock(return_value=[])
    agent = OptimizerAgent(config={"dry_run_mode": True}, scanner=scanner, strategy=strategy)
    agent.audit_logger = MagicMock()
    agent.audit_logger.log_event = AsyncMock()
    return agent


def _scheduled(tmp_path, scanner, *, dry_run=False):
    tracker = PositionTracker(str(tmp_path / "single_scan.db"))
    wallet = MagicMock()
    wallet.address = WALLET
    # No idle capital: the hold path never reaches _deploy_idle_capital.
    wallet.get_balance = AsyncMock(return_value=Decimal("0"))
    opt = ScheduledOptimizer(
        config={
            "dry_run_mode": dry_run,
            "circuit_breaker_state_file": str(tmp_path / "breaker.json"),
            "heartbeat_file": str(tmp_path / "heartbeat.json"),
        },
        yield_scanner=scanner,
        optimizer=_optimizer_agent(scanner),
        risk_assessor=MagicMock(),
        rebalance_executor=MagicMock(),
        wallet_manager=wallet,
        profitability_calc=MagicMock(),
        audit_logger=MagicMock(),
        database=None,
        position_tracker=tracker,
    )
    opt.audit_logger.log_event = AsyncMock()
    opt._record_decision = AsyncMock()
    opt._alert_stranded_intents = AsyncMock()
    opt._check_balance_cap = AsyncMock()
    return opt, tracker


class TestSingleScanPerCycle:
    async def test_live_cycle_scans_once_and_reconcile_uses_it(self, tmp_path):
        moonwell = _proto("Moonwell", "100")
        scanner = _scanner([_opp("Moonwell", "moonwell-usdc", apy="6")], [moonwell])
        opt, tracker = _scheduled(tmp_path, scanner)

        await opt._execute_optimization_cycle()

        scanner.scan_all_protocols.assert_awaited_once()
        # Reconcile consumed the shared scan: it read the pool and recorded it.
        moonwell.get_user_balance.assert_awaited_once_with("moonwell-usdc", WALLET)
        active = await tracker.get_current_positions(wallet_address=WALLET)
        assert [(p.protocol, p.amount) for p in active] == [("Moonwell", Decimal("100"))]
        # The optimizer received the same scan (and the reconciled position).
        opt.optimizer.strategy.analyze_opportunities.assert_awaited_once()
        kwargs = opt.optimizer.strategy.analyze_opportunities.await_args.kwargs
        assert kwargs["current_positions"] == {"Moonwell": Decimal("100")}
        assert kwargs["available_yields"] == {"Moonwell": Decimal("6")}

    async def test_scans_once_across_consecutive_cycles(self, tmp_path):
        scanner = _scanner([_opp("Moonwell", "moonwell-usdc")], [_proto("Moonwell", "100")])
        opt, _ = _scheduled(tmp_path, scanner)

        for _ in range(3):
            await opt._execute_optimization_cycle()

        assert scanner.scan_all_protocols.await_count == 3

    async def test_scans_once_with_reconcile_disabled(self, tmp_path):
        scanner = _scanner([_opp("Moonwell", "moonwell-usdc")], [_proto("Moonwell", "100")])
        opt, _ = _scheduled(tmp_path, scanner)
        opt.reconcile_on_read = False

        await opt._execute_optimization_cycle()

        scanner.scan_all_protocols.assert_awaited_once()

    async def test_dry_run_scans_once_and_reconcile_stays_noop(self, tmp_path):
        moonwell = _proto("Moonwell", "100")
        scanner = _scanner([_opp("Moonwell", "moonwell-usdc")], [moonwell])
        opt, tracker = _scheduled(tmp_path, scanner, dry_run=True)

        await opt._execute_optimization_cycle()

        scanner.scan_all_protocols.assert_awaited_once()
        moonwell.get_user_balance.assert_not_called()
        assert await tracker.get_current_positions(wallet_address=WALLET) == []


class TestScanFailure:
    async def test_failed_scan_does_not_close_tracked_positions(self, tmp_path):
        moonwell = _proto("Moonwell", "0")
        scanner = _scanner([], [moonwell])
        scanner.scan_all_protocols = AsyncMock(side_effect=RuntimeError("rpc down"))
        opt, tracker = _scheduled(tmp_path, scanner)
        pos_id = await tracker.record_position(
            wallet_address=WALLET,
            protocol="Moonwell",
            pool_id="moonwell-usdc",
            token="USDC",
            amount=Decimal("100"),
            value_usd=Decimal("100"),
            current_apy=Decimal("5"),
        )

        # Best-effort: the cycle completes (no raise) and nothing is closed.
        await opt._execute_optimization_cycle()

        moonwell.get_user_balance.assert_not_called()
        assert tracker.session.query(Position).get(pos_id).status == "active"

    async def test_empty_scan_reconciles_nothing_and_does_not_rescan(self, tmp_path):
        """All protocols failing yields [] (not an exception): nothing read,
        nothing closed, and neither consumer falls back to a second scan."""
        moonwell = _proto("Moonwell", "0")
        scanner = _scanner([], [moonwell])
        opt, tracker = _scheduled(tmp_path, scanner)
        pos_id = await tracker.record_position(
            wallet_address=WALLET,
            protocol="Moonwell",
            pool_id="moonwell-usdc",
            token="USDC",
            amount=Decimal("100"),
            value_usd=Decimal("100"),
            current_apy=Decimal("5"),
        )

        await opt._execute_optimization_cycle()

        scanner.scan_all_protocols.assert_awaited_once()
        assert tracker.session.query(Position).get(pos_id).status == "active"


class TestOptimizerPrefetched:
    async def test_uses_prefetched_opportunities(self):
        scanner = _scanner([], [])
        agent = _optimizer_agent(scanner)

        await agent.find_rebalance_opportunities(
            {"Moonwell": Decimal("100")},
            opportunities=[_opp("Moonwell", "moonwell-usdc", apy="6")],
        )

        scanner.scan_all_protocols.assert_not_called()
        kwargs = agent.strategy.analyze_opportunities.await_args.kwargs
        assert kwargs["available_yields"] == {"Moonwell": Decimal("6")}

    async def test_scans_when_not_prefetched(self):
        scanner = _scanner([_opp("Moonwell", "moonwell-usdc")], [])
        agent = _optimizer_agent(scanner)

        await agent.find_rebalance_opportunities({"Moonwell": Decimal("100")})

        scanner.scan_all_protocols.assert_awaited_once()
