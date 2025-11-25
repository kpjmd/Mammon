#!/usr/bin/env python3
"""Run 24-hour autonomous optimizer test.

This script runs the MAMMON optimizer in autonomous mode for 24 hours,
scanning for yield opportunities and executing profitable rebalances.

Sprint 3 Competitive Moat: Demonstrates full autonomous operation with:
- Position tracking with predicted vs actual ROI
- Performance metrics and 4-gate validation
- Safe limits on gas and rebalance frequency

Usage:
    poetry run python scripts/run_autonomous_optimizer.py
    poetry run python scripts/run_autonomous_optimizer.py --duration 1  # 1 hour test
    poetry run python scripts/run_autonomous_optimizer.py --dry-run  # No real transactions
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import argparse
import signal
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional
import json

from src.agents.yield_scanner import YieldScannerAgent
from src.agents.optimizer import OptimizerAgent
from src.agents.risk_assessor import RiskAssessorAgent
from src.agents.scheduled_optimizer import ScheduledOptimizer
from src.blockchain.wallet import WalletManager
from src.blockchain.rebalance_executor import RebalanceExecutor, RebalanceExecution
from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.blockchain.gas_estimator import GasEstimator
from src.data.oracles import create_price_oracle
from src.data.database import Database
from src.data.position_tracker import PositionTracker
from src.data.performance_tracker import PerformanceTracker
from src.strategies.profitability_calculator import ProfitabilityCalculator
from src.strategies.simple_yield import SimpleYieldStrategy
from src.security.audit import AuditLogger
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AutonomousRunner:
    """Manages the 24-hour autonomous optimizer run."""

    def __init__(
        self,
        duration_hours: float = 24.0,
        scan_interval_hours: float = 2.0,
        max_rebalances_per_day: int = 6,
        max_gas_per_day_usd: Decimal = Decimal("10"),
        dry_run: bool = False,
    ):
        """Initialize the autonomous runner.

        Args:
            duration_hours: Total run duration in hours
            scan_interval_hours: Hours between scans
            max_rebalances_per_day: Maximum rebalances allowed per day
            max_gas_per_day_usd: Maximum gas spend per day in USD
            dry_run: If True, simulate transactions only
        """
        self.duration_hours = duration_hours
        self.scan_interval_hours = scan_interval_hours
        self.max_rebalances_per_day = max_rebalances_per_day
        self.max_gas_per_day_usd = max_gas_per_day_usd
        self.dry_run = dry_run

        self.settings = get_settings()
        self.scheduler: Optional[ScheduledOptimizer] = None
        self.running = False
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

        # Metrics
        self.total_scans = 0
        self.total_rebalances = 0
        self.total_gas_spent_usd = Decimal("0")
        self.opportunities_found = 0
        self.opportunities_executed = 0
        self.opportunities_skipped = 0
        self.errors: list = []

    async def initialize(self) -> None:
        """Initialize all components for autonomous operation."""
        print_header("MAMMON - Autonomous Optimizer Initialization")

        # Build config
        config = {
            "network": self.settings.network,
            "wallet_seed": self.settings.wallet_seed,
            "read_only": False,
            "dry_run_mode": self.dry_run,
            "use_mock_data": False,
            "chainlink_enabled": True,
            "max_transaction_value_usd": self.settings.max_transaction_value_usd,
            "daily_spending_limit_usd": self.settings.daily_spending_limit_usd,
            "min_apy_improvement": float(self.settings.min_apy_improvement),
            "min_profit_usd": float(self.settings.min_profit_usd),
            "max_break_even_days": self.settings.max_break_even_days,
            "max_cost_pct": float(self.settings.max_cost_pct),
        }

        print(f"Network: {config['network']}")
        print(f"Dry Run: {self.dry_run}")
        print(f"Duration: {self.duration_hours} hours")
        print(f"Scan Interval: {self.scan_interval_hours} hours")
        print(f"Max Rebalances/Day: {self.max_rebalances_per_day}")
        print(f"Max Gas/Day: ${self.max_gas_per_day_usd}")

        # Initialize components
        print("\nInitializing components...")

        # Price oracle
        oracle = create_price_oracle(
            "chainlink" if config["chainlink_enabled"] else "mock",
            network=config["network"],
        )
        print("  ✅ Price oracle")

        # Wallet
        wallet = WalletManager(config=config, price_oracle=oracle)
        await wallet.initialize()
        print(f"  ✅ Wallet: {wallet.address}")

        # Database
        db_path = self.settings.database_url.replace("sqlite:///", "")
        database = Database(self.settings.database_url)
        database.create_all_tables()
        print("  ✅ Database")

        # Trackers - use db_path string
        position_tracker = PositionTracker(db_path)
        performance_tracker = PerformanceTracker(db_path)
        print("  ✅ Position & Performance Trackers")

        # Agents
        yield_scanner = YieldScannerAgent(config)
        strategy = SimpleYieldStrategy(config)
        optimizer = OptimizerAgent(config, yield_scanner, strategy)
        risk_assessor = RiskAssessorAgent(config)
        print("  ✅ Yield Scanner, Optimizer, Risk Assessor")

        # Calculators and executors
        gas_estimator = GasEstimator(config["network"], oracle)
        profitability_calc = ProfitabilityCalculator(
            min_annual_gain_usd=Decimal(str(config["min_profit_usd"])),
            max_break_even_days=config["max_break_even_days"],
            max_cost_pct=Decimal(str(config["max_cost_pct"])),
            gas_estimator=gas_estimator,
        )
        protocol_executor = ProtocolActionExecutor(wallet, config)
        rebalance_executor = RebalanceExecutor(
            wallet_manager=wallet,
            protocol_executor=protocol_executor,
            gas_estimator=gas_estimator,
            price_oracle=oracle,
            config=config,
        )
        audit_logger = AuditLogger()
        print("  ✅ Profitability Calculator, Rebalance Executor")

        # Create scheduled optimizer
        self.scheduler = ScheduledOptimizer(
            config=config,
            yield_scanner=yield_scanner,
            optimizer=optimizer,
            risk_assessor=risk_assessor,
            rebalance_executor=rebalance_executor,
            wallet_manager=wallet,
            profitability_calc=profitability_calc,
            audit_logger=audit_logger,
            database=database,
            position_tracker=position_tracker,
        )
        print("  ✅ Scheduled Optimizer")

        # Store references for metrics
        self.position_tracker = position_tracker
        self.performance_tracker = performance_tracker
        self.database = database
        self.wallet = wallet
        self.oracle = oracle

        print("\n✅ Initialization complete!")

    async def run(self) -> Dict[str, Any]:
        """Run the autonomous optimizer for the configured duration.

        Returns:
            Summary of the run including all metrics
        """
        print_header("Starting Autonomous Operation")

        self.running = True
        self.start_time = datetime.now(UTC)
        self.end_time = self.start_time + timedelta(hours=self.duration_hours)

        print(f"Start Time: {self.start_time.isoformat()}")
        print(f"End Time: {self.end_time.isoformat()}")
        print(f"Total Scans Expected: {int(self.duration_hours / self.scan_interval_hours)}")

        # Initial wallet balance - simplified for autonomy test
        try:
            eth_balance = await self.wallet.get_balance()
            # get_balance returns Decimal for ETH
            if isinstance(eth_balance, Decimal):
                initial_balance = eth_balance
            else:
                initial_balance = Decimal(str(eth_balance))
            eth_price = await self.oracle.get_price("ETH")
            initial_value_usd = initial_balance * eth_price
            print(f"Initial ETH Balance: {initial_balance:.6f} ETH (${initial_value_usd:.2f})")
        except Exception as e:
            initial_value_usd = Decimal("0")
            print(f"Could not fetch balance: {e}")

        print("\n" + "-" * 60)
        print("Running... Press Ctrl+C to stop early")
        print("-" * 60 + "\n")

        try:
            while self.running and datetime.now(UTC) < self.end_time:
                await self._run_scan_cycle()

                # Check if we should continue
                if not self.running:
                    break

                # Check limits
                if self.total_rebalances >= self.max_rebalances_per_day:
                    logger.warning(f"Reached max rebalances ({self.max_rebalances_per_day})")
                    print(f"\n⚠️  Reached max rebalances limit ({self.max_rebalances_per_day})")
                    break

                if self.total_gas_spent_usd >= self.max_gas_per_day_usd:
                    logger.warning(f"Reached max gas spend (${self.max_gas_per_day_usd})")
                    print(f"\n⚠️  Reached max gas spend (${self.max_gas_per_day_usd})")
                    break

                # Sleep until next scan
                next_scan = datetime.now(UTC) + timedelta(hours=self.scan_interval_hours)
                if next_scan < self.end_time:
                    sleep_seconds = self.scan_interval_hours * 3600
                    print(f"\nNext scan at {next_scan.strftime('%H:%M:%S UTC')}")
                    print(f"Sleeping for {self.scan_interval_hours} hours...")

                    # Sleep in short intervals to allow for interruption
                    for _ in range(int(sleep_seconds / 10)):
                        if not self.running:
                            break
                        await asyncio.sleep(10)

        except Exception as e:
            logger.error(f"Error during autonomous operation: {e}")
            self.errors.append({
                "timestamp": datetime.now(UTC).isoformat(),
                "error": str(e),
            })
            print(f"\n❌ Error: {e}")

        finally:
            self.running = False

        # Generate summary
        return await self._generate_summary(initial_value_usd)

    async def _run_scan_cycle(self) -> None:
        """Run a single scan cycle."""
        self.total_scans += 1
        scan_time = datetime.now(UTC)

        print(f"\n{'='*60}")
        print(f"SCAN #{self.total_scans} at {scan_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}")

        try:
            # Run optimizer scan - returns List[RebalanceExecution]
            executions = await self.scheduler.run_once()

            # Count successful and failed
            successful = [e for e in executions if e.success]
            failed = [e for e in executions if not e.success]

            # Calculate gas spent
            gas_spent = sum(e.total_gas_cost_usd for e in executions)

            self.opportunities_found += len(executions)
            self.opportunities_executed += len(successful)
            self.opportunities_skipped += len(failed)
            self.total_gas_spent_usd += gas_spent
            self.total_rebalances += len(successful)

            print(f"\nResults:")
            print(f"  Rebalances Attempted: {len(executions)}")
            print(f"  Successful: {len(successful)}")
            print(f"  Failed: {len(failed)}")
            print(f"  Gas Spent: ${gas_spent:.4f}")

            # Show executed rebalances
            for execution in successful:
                rec = execution.recommendation
                print(f"\n  ✅ Rebalanced:")
                print(f"     From: {rec.from_protocol} ({rec.token})")
                print(f"     To: {rec.to_protocol} ({rec.token})")
                print(f"     Amount: ${float(rec.amount):.2f}")
                apy_gain = rec.expected_apy - rec.current_apy
                print(f"     APY Gain: {apy_gain:.2f}%")
                print(f"     Gas Cost: ${float(execution.total_gas_cost_usd):.4f}")

            # Show failed rebalances
            for execution in failed:
                rec = execution.recommendation
                print(f"\n  ❌ Failed:")
                print(f"     From: {rec.from_protocol} to {rec.to_protocol}")
                if execution.steps:
                    last_step = execution.steps[-1]
                    print(f"     Error: {last_step.error_message or 'Unknown'}")

            if not executions:
                print("\n  No rebalance opportunities found")

        except Exception as e:
            logger.error(f"Error in scan cycle: {e}")
            self.errors.append({
                "timestamp": scan_time.isoformat(),
                "error": str(e),
            })
            print(f"\n  ❌ Error: {e}")

    async def _generate_summary(self, initial_balance: Decimal) -> Dict[str, Any]:
        """Generate a summary of the autonomous run.

        Args:
            initial_balance: Initial portfolio value in USD

        Returns:
            Summary dictionary
        """
        print_header("Autonomous Run Summary")

        end_time = datetime.now(UTC)
        duration = end_time - self.start_time

        # Get final balance - simplified
        final_balance = initial_balance  # Same for now (would need price updates)
        pnl = final_balance - initial_balance
        pnl_percent = (pnl / initial_balance * 100) if initial_balance > 0 else Decimal("0")

        # Get performance metrics if available
        try:
            perf_metrics = await self.performance_tracker.get_session_summary(
                self.start_time, end_time
            )
        except Exception:
            perf_metrics = {}

        summary = {
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_hours": duration.total_seconds() / 3600,
            "total_scans": self.total_scans,
            "total_rebalances": self.total_rebalances,
            "opportunities_found": self.opportunities_found,
            "opportunities_executed": self.opportunities_executed,
            "opportunities_skipped": self.opportunities_skipped,
            "total_gas_spent_usd": float(self.total_gas_spent_usd),
            "initial_balance_usd": float(initial_balance),
            "final_balance_usd": float(final_balance),
            "pnl_usd": float(pnl),
            "pnl_percent": float(pnl_percent),
            "errors": len(self.errors),
            "dry_run": self.dry_run,
            "performance_metrics": perf_metrics,
        }

        # Print summary
        print(f"Duration: {duration}")
        print(f"Total Scans: {self.total_scans}")
        print(f"Total Rebalances: {self.total_rebalances}")
        print(f"\nOpportunities:")
        print(f"  Found: {self.opportunities_found}")
        print(f"  Executed: {self.opportunities_executed}")
        print(f"  Skipped: {self.opportunities_skipped}")
        print(f"\nFinancials:")
        print(f"  Initial Balance: ${initial_balance:.2f}")
        print(f"  Final Balance: ${final_balance:.2f}")
        print(f"  P&L: ${pnl:.2f} ({pnl_percent:.2f}%)")
        print(f"  Gas Spent: ${self.total_gas_spent_usd:.4f}")
        print(f"\nErrors: {len(self.errors)}")

        if self.dry_run:
            print("\n⚠️  This was a DRY RUN - no real transactions were executed")

        # Save summary to file
        summary_file = project_root / "data" / f"autonomous_run_{self.start_time.strftime('%Y%m%d_%H%M%S')}.json"
        summary_file.parent.mkdir(parents=True, exist_ok=True)

        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"\nSummary saved to: {summary_file}")

        return summary

    def stop(self) -> None:
        """Stop the autonomous runner."""
        print("\n\nStopping autonomous optimizer...")
        self.running = False


def print_header(title: str):
    """Print formatted section header."""
    print("\n" + "=" * 60)
    print(title.center(60))
    print("=" * 60)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run MAMMON autonomous optimizer"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=24.0,
        help="Run duration in hours (default: 24)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Scan interval in hours (default: 2)"
    )
    parser.add_argument(
        "--max-rebalances",
        type=int,
        default=6,
        help="Maximum rebalances per day (default: 6)"
    )
    parser.add_argument(
        "--max-gas",
        type=float,
        default=10.0,
        help="Maximum gas spend per day in USD (default: 10)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate transactions only"
    )

    args = parser.parse_args()

    # Create runner
    runner = AutonomousRunner(
        duration_hours=args.duration,
        scan_interval_hours=args.interval,
        max_rebalances_per_day=args.max_rebalances,
        max_gas_per_day_usd=Decimal(str(args.max_gas)),
        dry_run=args.dry_run,
    )

    # Setup signal handler for graceful shutdown
    def signal_handler(sig, frame):
        runner.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize and run
    try:
        await runner.initialize()
        summary = await runner.run()

        # Exit with success or failure based on errors
        if summary.get("errors", 0) > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
