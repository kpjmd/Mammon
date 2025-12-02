"""Scheduled autonomous optimizer for continuous rebalancing.

This module provides scheduled execution of the optimizer workflow:
1. Scans protocols for current APYs
2. Generates rebalance recommendations
3. Executes profitable rebalances automatically
4. Tracks performance and gas costs

Designed for autonomous operation with configurable scheduling,
safety limits, and error recovery.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, UTC, timedelta
from decimal import Decimal
import asyncio

from src.agents.yield_scanner import YieldScannerAgent
from src.agents.optimizer import OptimizerAgent
from src.agents.risk_assessor import RiskAssessorAgent
from src.strategies.base_strategy import RebalanceRecommendation
from src.strategies.profitability_calculator import ProfitabilityCalculator
from src.blockchain.rebalance_executor import RebalanceExecutor, RebalanceExecution
from src.blockchain.wallet import WalletManager
from src.data.database import Database
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SchedulerStatus:
    """Status information for the scheduler."""

    def __init__(self):
        self.running: bool = False
        self.start_time: Optional[datetime] = None
        self.last_scan_time: Optional[datetime] = None
        self.next_scan_time: Optional[datetime] = None
        self.total_scans: int = 0
        self.total_rebalances: int = 0
        self.total_opportunities_found: int = 0
        self.total_opportunities_executed: int = 0
        self.total_opportunities_skipped: int = 0
        self.total_gas_spent_usd: Decimal = Decimal("0")
        self.errors: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert status to dictionary for serialization."""
        return {
            "running": self.running,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "last_scan_time": (
                self.last_scan_time.isoformat() if self.last_scan_time else None
            ),
            "next_scan_time": (
                self.next_scan_time.isoformat() if self.next_scan_time else None
            ),
            "total_scans": self.total_scans,
            "total_rebalances": self.total_rebalances,
            "total_opportunities_found": self.total_opportunities_found,
            "total_opportunities_executed": self.total_opportunities_executed,
            "total_opportunities_skipped": self.total_opportunities_skipped,
            "total_gas_spent_usd": float(self.total_gas_spent_usd),
            "recent_errors": self.errors[-10:],  # Last 10 errors
        }


class ScheduledOptimizer:
    """Autonomous optimizer that runs on a schedule.

    Continuously scans for yield opportunities and executes profitable
    rebalances according to configured strategy and safety parameters.

    Attributes:
        config: Configuration dictionary
        yield_scanner: YieldScannerAgent instance
        optimizer: OptimizerAgent instance
        risk_assessor: RiskAssessor instance
        rebalance_executor: RebalanceExecutor instance
        wallet_manager: WalletManager instance
        profitability_calc: ProfitabilityCalculator instance
        audit_logger: AuditLogger instance
        database: Database instance
        status: Current scheduler status
    """

    def __init__(
        self,
        config: Dict[str, Any],
        yield_scanner: YieldScannerAgent,
        optimizer: OptimizerAgent,
        risk_assessor: RiskAssessorAgent,
        rebalance_executor: RebalanceExecutor,
        wallet_manager: WalletManager,
        profitability_calc: ProfitabilityCalculator,
        audit_logger: Optional[AuditLogger] = None,
        database: Optional[Database] = None,
        position_tracker: Optional[Any] = None,
    ):
        """Initialize the scheduled optimizer.

        Args:
            config: Configuration with scheduling parameters
            yield_scanner: YieldScannerAgent for protocol scanning
            optimizer: OptimizerAgent for generating recommendations
            risk_assessor: RiskAssessorAgent for safety checks
            rebalance_executor: RebalanceExecutor for transaction execution
            wallet_manager: WalletManager for balance tracking
            profitability_calc: ProfitabilityCalculator for ROI analysis
            audit_logger: Optional audit logger
            database: Optional database for state persistence
            position_tracker: Optional position tracker for detecting existing positions
        """
        self.config = config
        self.yield_scanner = yield_scanner
        self.optimizer = optimizer
        self.risk_assessor = risk_assessor
        self.rebalance_executor = rebalance_executor
        self.wallet_manager = wallet_manager
        self.profitability_calc = profitability_calc
        self.audit_logger = audit_logger or AuditLogger()
        self.database = database
        self.position_tracker = position_tracker

        # Scheduler configuration
        self.scan_interval_hours = config.get("scan_interval_hours", 4)
        self.max_rebalances_per_day = config.get("max_rebalances_per_day", 5)
        self.max_gas_per_day_usd = config.get("max_gas_per_day_usd", Decimal("50"))
        self.min_profit_usd = config.get("min_profit_usd", Decimal("10"))
        self.dry_run_mode = config.get("dry_run_mode", False)

        # State
        self.status = SchedulerStatus()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the autonomous scheduler.

        Begins continuous monitoring and rebalancing according to
        configured schedule. Non-blocking - runs in background task.
        """
        if self.status.running:
            logger.warning("Scheduler already running")
            return

        logger.info(
            f"Starting ScheduledOptimizer (interval: {self.scan_interval_hours}h, "
            f"max rebalances/day: {self.max_rebalances_per_day})"
        )

        self.status.running = True
        self.status.start_time = datetime.now(UTC)
        self._stop_event.clear()

        # Start background task
        self._task = asyncio.create_task(self._run_loop())

        await self.audit_logger.log_event(
            event_type=AuditEventType.CONFIG_CHANGED,
            severity=AuditSeverity.INFO,
            message="ScheduledOptimizer started",
            metadata={
                "scan_interval_hours": self.scan_interval_hours,
                "max_rebalances_per_day": self.max_rebalances_per_day,
                "max_gas_per_day_usd": float(self.max_gas_per_day_usd),
                "dry_run_mode": self.dry_run_mode,
            },
        )

        logger.info("✅ ScheduledOptimizer started successfully")

    async def stop(self) -> None:
        """Stop the autonomous scheduler.

        Gracefully shuts down the scheduler, allowing current scan
        to complete before stopping.
        """
        if not self.status.running:
            logger.warning("Scheduler not running")
            return

        logger.info("Stopping ScheduledOptimizer...")

        self._stop_event.set()
        self.status.running = False

        # Wait for task to complete
        if self._task:
            await self._task
            self._task = None

        await self.audit_logger.log_event(
            event_type=AuditEventType.CONFIG_CHANGED,
            severity=AuditSeverity.INFO,
            message="ScheduledOptimizer stopped",
            metadata=self.status.to_dict(),
        )

        logger.info("✅ ScheduledOptimizer stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status.

        Returns:
            Dictionary with status information
        """
        return self.status.to_dict()

    async def run_once(self) -> List[RebalanceExecution]:
        """Run a single optimization cycle manually.

        Useful for testing or manual execution.

        Returns:
            List of RebalanceExecution results
        """
        return await self._execute_optimization_cycle()

    async def _run_loop(self) -> None:
        """Main scheduler loop (runs in background task)."""
        try:
            while not self._stop_event.is_set():
                try:
                    # Calculate next scan time
                    self.status.next_scan_time = datetime.now(UTC) + timedelta(
                        hours=self.scan_interval_hours
                    )

                    # Execute optimization cycle
                    await self._execute_optimization_cycle()

                    # Update scan time
                    self.status.last_scan_time = datetime.now(UTC)
                    self.status.total_scans += 1

                    # Wait for next interval (or stop signal)
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.scan_interval_hours * 3600,
                    )

                except asyncio.TimeoutError:
                    # Normal timeout - continue to next cycle
                    continue

                except Exception as e:
                    # Log error but continue running
                    logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                    self.status.errors.append(
                        {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "error": str(e),
                            "type": type(e).__name__,
                        }
                    )

                    await self.audit_logger.log_event(
                        event_type=AuditEventType.RISK_ALERT,
                        severity=AuditSeverity.ERROR,
                        message=f"Scheduler error: {e}",
                        metadata={"error": str(e), "type": type(e).__name__},
                    )

                    # Wait before retrying (5 minutes)
                    await asyncio.sleep(300)

        except asyncio.CancelledError:
            logger.info("Scheduler loop cancelled")
            raise

    async def _execute_optimization_cycle(self) -> List[RebalanceExecution]:
        """Execute one complete optimization cycle.

        Returns:
            List of RebalanceExecution results
        """

        executions: List[RebalanceExecution] = []

        try:
            # 1. Get current positions
            current_positions = await self._get_current_positions()

            # 2. Get rebalance recommendations
            recommendations = await self.optimizer.find_rebalance_opportunities(
                current_positions
            )

            if not recommendations:
                return executions

            logger.info(f"Found {len(recommendations)} potential opportunities")
            self.status.total_opportunities_found += len(recommendations)

            # 3. Filter and execute profitable recommendations
            for i, rec in enumerate(recommendations, 1):

                # Check daily limits
                if not self._check_daily_limits():
                    logger.warning("Daily limits reached, skipping remaining opportunities")
                    self.status.total_opportunities_skipped += len(recommendations) - len(executions)
                    break

                # Check profitability
                logger.info(f"🔍 SCAN STEP 5.{i}a: Checking profitability...")
                if not await self._is_profitable(rec):
                    logger.info(f"Skipping unprofitable recommendation: {rec.reason}")
                    self.status.total_opportunities_skipped += 1
                    continue

                # Execute rebalance
                logger.info(f"🔍 SCAN STEP 5.{i}b: Executing rebalance: {rec.from_protocol} → {rec.to_protocol}")

                try:
                    execution = await self.rebalance_executor.execute_rebalance(rec)
                    executions.append(execution)

                    if execution.success:
                        self.status.total_rebalances += 1
                        self.status.total_opportunities_executed += 1
                        self.status.total_gas_spent_usd += execution.total_gas_cost_usd

                        # Log success
                        await self.audit_logger.log_event(
                            event_type=AuditEventType.REBALANCE_EXECUTED,
                            severity=AuditSeverity.INFO,
                            message=f"Rebalance executed: {rec.from_protocol} → {rec.to_protocol}",
                            metadata={
                                "from_protocol": rec.from_protocol,
                                "to_protocol": rec.to_protocol,
                                "token": rec.token,
                                "amount": float(rec.amount),
                                "gas_cost_usd": float(execution.total_gas_cost_usd),
                            },
                        )

                        logger.info(f"✅ Rebalance successful! Gas cost: ${execution.total_gas_cost_usd}")
                    else:
                        self.status.total_opportunities_skipped += 1
                        logger.warning(f"❌ Rebalance failed: {execution.error}")

                except Exception as e:
                    logger.error(f"Error executing rebalance: {e}", exc_info=True)
                    self.status.total_opportunities_skipped += 1

            logger.info("=" * 80)
            logger.info(f"Cycle complete: {len(executions)} rebalances executed")
            logger.info("=" * 80)

            return executions

        except Exception as e:
            logger.error(f"Error in optimization cycle: {e}", exc_info=True)
            raise

    async def _get_current_positions(self) -> Dict[str, Decimal]:
        """Get current protocol positions.

        Returns:
            Dictionary mapping protocol name to USD value
        """
        logger.info("🔍 DEBUG: _get_current_positions() called")
        logger.info(f"🔍 DEBUG: position_tracker present: {self.position_tracker is not None}")

        positions = {}

        if self.position_tracker:
            try:
                # Get active positions from position tracker (async call)
                logger.info("🔍 DEBUG: Calling position_tracker.get_current_positions()")
                active_positions = await self.position_tracker.get_current_positions()
                logger.info(f"🔍 DEBUG: Got {len(active_positions)} active positions from database")

                # Log details of each position
                for i, pos in enumerate(active_positions):
                    logger.info(f"🔍 DEBUG: Position {i+1}: protocol={pos.protocol}, value_usd={pos.value_usd}, token={pos.token}")

                # Aggregate by protocol
                for pos in active_positions:
                    protocol = pos.protocol
                    value_usd = pos.value_usd

                    if protocol in positions:
                        positions[protocol] += value_usd
                    else:
                        positions[protocol] = value_usd

                logger.info(f"✅ Detected {len(active_positions)} positions, aggregated to: {positions}")
                return positions

            except Exception as e:
                logger.error(f"❌ Error getting positions from tracker: {e}", exc_info=True)
                # Fall through to return empty positions

        # No position tracker or error - return empty positions
        logger.warning("⚠️  No position tracker available or error occurred")
        return {}

    async def _is_profitable(self, recommendation: RebalanceRecommendation) -> bool:
        """Check if recommendation meets profitability criteria.

        Args:
            recommendation: RebalanceRecommendation to evaluate

        Returns:
            True if profitable, False otherwise
        """
        try:
            # Calculate profitability metrics
            # TODO: Get current APY from database/position tracker
            current_apy = Decimal("3.5")  # Placeholder - should match Aave USDC

            # Check if swap is required (different tokens)
            requires_swap = recommendation.token != recommendation.token  # Same token for now

            analysis = await self.profitability_calc.calculate_profitability(
                current_apy=current_apy,
                target_apy=recommendation.expected_apy,
                position_size_usd=recommendation.amount,
                requires_swap=requires_swap,
                swap_amount_usd=recommendation.amount,
            )

            # Check if meets profitability gates
            if not analysis.is_profitable:
                logger.info(
                    f"Unprofitable: {', '.join(analysis.rejection_reasons)}"
                )
                return False

            logger.info(
                f"✅ Profitable: ${analysis.annual_gain_usd}/year, "
                f"break-even in {analysis.break_even_days} days"
            )
            return True

        except Exception as e:
            logger.error(f"Error checking profitability: {e}", exc_info=True)
            return False

    def _check_daily_limits(self) -> bool:
        """Check if daily limits allow more rebalances.

        Returns:
            True if within limits, False otherwise
        """
        # Reset counters if new day
        now = datetime.now(UTC)
        if self.status.start_time:
            hours_since_start = (now - self.status.start_time).total_seconds() / 3600
            if hours_since_start >= 24:
                # Reset daily counters
                self.status.start_time = now
                self.status.total_rebalances = 0
                self.status.total_gas_spent_usd = Decimal("0")

        # Check rebalance count limit
        if self.status.total_rebalances >= self.max_rebalances_per_day:
            logger.warning(
                f"Daily rebalance limit reached: {self.status.total_rebalances}/{self.max_rebalances_per_day}"
            )
            return False

        # Check gas spending limit
        if self.status.total_gas_spent_usd >= self.max_gas_per_day_usd:
            logger.warning(
                f"Daily gas limit reached: ${self.status.total_gas_spent_usd}/${self.max_gas_per_day_usd}"
            )
            return False

        return True
