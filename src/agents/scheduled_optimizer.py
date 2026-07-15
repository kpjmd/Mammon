"""Scheduled autonomous optimizer for continuous rebalancing.

This module provides scheduled execution of the optimizer workflow:
1. Scans protocols for current APYs
2. Generates rebalance recommendations
3. Executes profitable rebalances automatically
4. Tracks performance and gas costs

Designed for autonomous operation with configurable scheduling,
safety limits, and error recovery.
"""

from typing import Dict, List, Optional, Any, Tuple
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
from src.data.database import Database, BaseRepository
from src.data.models import Decision
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
        self.target_token = config.get("target_token", "USDC")

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
                # Check if we have idle capital to deploy
                idle_capital = await self._get_idle_capital()

                if idle_capital:
                    logger.info("💰 No positions to rebalance, but found idle capital")
                    self.status.total_opportunities_found += len(idle_capital)

                    deployment_executions = await self._deploy_idle_capital(idle_capital)
                    executions.extend(deployment_executions)
                else:
                    logger.info("No positions and no idle capital - nothing to do")

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

                apy_improvement = (
                    (rec.expected_apy - rec.current_apy)
                    if rec.current_apy is not None
                    else None
                )

                # Check profitability
                logger.info(f"🔍 SCAN STEP 5.{i}a: Checking profitability...")
                is_profitable, rejection_reasons = await self._is_profitable(rec)
                if not is_profitable:
                    logger.info(f"Skipping unprofitable recommendation: {rec.reason}")
                    self.status.total_opportunities_skipped += 1
                    await self._record_decision(
                        decision_type="rebalance",
                        rationale="; ".join(rejection_reasons) or "Unprofitable",
                        from_protocol=rec.from_protocol,
                        to_protocol=rec.to_protocol,
                        approved=-1,
                        expected_apy_improvement=apy_improvement,
                    )
                    continue

                # Check risk (CRITICAL always blocks, HIGH blocks unless
                # explicitly allowed via config)
                logger.info(f"🔍 SCAN STEP 5.{i}a2: Checking risk...")
                risk_assessment = await self.risk_assessor.assess_rebalance_risk(
                    from_protocol=rec.from_protocol,
                    to_protocol=rec.to_protocol,
                    amount=rec.amount,
                    requires_swap=False,
                )
                if not self.risk_assessor.should_proceed(
                    risk_assessment,
                    allow_high_risk=self.config.get("allow_high_risk", False),
                ):
                    logger.warning(
                        f"Skipping recommendation blocked by risk assessment "
                        f"({risk_assessment.risk_level.value}): "
                        f"{rec.from_protocol} → {rec.to_protocol}"
                    )
                    self.status.total_opportunities_skipped += 1
                    await self._record_decision(
                        decision_type="rebalance",
                        rationale=f"Blocked by risk assessment: {risk_assessment.recommendation}",
                        from_protocol=rec.from_protocol,
                        to_protocol=rec.to_protocol,
                        approved=-1,
                        expected_apy_improvement=apy_improvement,
                        risk_score=risk_assessment.risk_score,
                    )
                    continue

                # Execute rebalance
                logger.info(f"🔍 SCAN STEP 5.{i}b: Executing rebalance: {rec.from_protocol} → {rec.to_protocol}")

                await self._record_decision(
                    decision_type="rebalance",
                    rationale=rec.reason,
                    from_protocol=rec.from_protocol,
                    to_protocol=rec.to_protocol,
                    approved=1,
                    expected_apy_improvement=apy_improvement,
                    risk_score=risk_assessment.risk_score,
                )

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

                # Aggregate by protocol, restricted to target_token — a
                # non-target-token position can't be compared against
                # available_yields (which is also filtered to target_token)
                # or rebalanced by strategies that only emit target_token
                # recommendations.
                skipped = 0
                for pos in active_positions:
                    if pos.token.upper() != self.target_token.upper():
                        skipped += 1
                        continue

                    protocol = pos.protocol
                    value_usd = pos.value_usd

                    if protocol in positions:
                        positions[protocol] += value_usd
                    else:
                        positions[protocol] = value_usd

                if skipped:
                    logger.info(
                        f"Skipped {skipped} position(s) not in target token "
                        f"'{self.target_token}'"
                    )

                logger.info(f"✅ Detected {len(active_positions)} positions, aggregated to: {positions}")
                return positions

            except Exception as e:
                logger.error(f"❌ Error getting positions from tracker: {e}", exc_info=True)
                # Fall through to return empty positions

        # No position tracker or error - return empty positions
        logger.warning("⚠️  No position tracker available or error occurred")
        return {}

    async def _get_idle_capital(
        self, min_amount: Decimal = Decimal("10")
    ) -> Dict[str, Decimal]:
        """Detect idle stablecoins in wallet that aren't deployed to protocols.

        Args:
            min_amount: Minimum amount to consider as deployable (default $10)

        Returns:
            Dict mapping token symbol to idle amount (e.g., {"USDC": Decimal("100")})
        """
        idle_capital: Dict[str, Decimal] = {}

        try:
            # Check USDC balance (primary stablecoin on Base)
            usdc_balance = await self.wallet_manager.get_balance("usdc")

            if usdc_balance >= min_amount:
                idle_capital["USDC"] = usdc_balance
                logger.info(f"💰 Detected idle capital: {usdc_balance} USDC")
            else:
                logger.debug(f"USDC balance {usdc_balance} below minimum {min_amount}")

        except Exception as e:
            logger.error(f"Error detecting idle capital: {e}")

        return idle_capital

    async def _is_profitable(
        self, recommendation: RebalanceRecommendation
    ) -> Tuple[bool, List[str]]:
        """Check if recommendation meets profitability criteria.

        Args:
            recommendation: RebalanceRecommendation to evaluate

        Returns:
            Tuple of (is_profitable, reasons) - reasons explain the gate
            outcome (rejection reasons if unprofitable, empty if profitable)
        """
        try:
            # Calculate profitability metrics
            current_apy = recommendation.current_apy
            if current_apy is None:
                reason = (
                    f"Recommendation for {recommendation.from_protocol} → "
                    f"{recommendation.to_protocol} has no current_apy set; "
                    "treating as unprofitable rather than guessing."
                )
                logger.warning(reason)
                return False, [reason]

            # RebalanceRecommendation only carries a single `token` field, so
            # a recommendation can never represent a cross-token move. Swaps
            # are unsupported end-to-end (see RebalanceExecutor._requires_swap).
            requires_swap = False

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
                return False, analysis.rejection_reasons

            logger.info(
                f"✅ Profitable: ${analysis.annual_gain_usd}/year, "
                f"break-even in {analysis.break_even_days} days"
            )
            return True, []

        except Exception as e:
            logger.error(f"Error checking profitability: {e}", exc_info=True)
            return False, [f"Error checking profitability: {e}"]

    async def _is_deployment_profitable(
        self, recommendation: RebalanceRecommendation
    ) -> bool:
        """Check if deploying idle capital is profitable after gas costs.

        For new deployments, we compare expected yield vs gas cost.
        Since there's no current APY (idle capital earns 0%), any positive
        yield after gas is profitable.

        Args:
            recommendation: RebalanceRecommendation for deployment

        Returns:
            True if profitable, False otherwise
        """
        try:
            # For idle capital, current APY is 0
            analysis = await self.profitability_calc.calculate_profitability(
                current_apy=Decimal("0"),  # Idle capital earns nothing
                target_apy=recommendation.expected_apy,
                position_size_usd=recommendation.amount,
                requires_swap=False,  # Same token
                swap_amount_usd=Decimal("0"),
            )

            if not analysis.is_profitable:
                logger.info(
                    f"Deployment unprofitable: {', '.join(analysis.rejection_reasons)}"
                )
                return False

            logger.info(
                f"✅ Deployment profitable: ${analysis.annual_gain_usd}/year, "
                f"break-even in {analysis.break_even_days} days"
            )
            return True

        except Exception as e:
            logger.error(f"Error checking deployment profitability: {e}", exc_info=True)
            return False

    async def _record_decision(
        self,
        decision_type: str,
        rationale: str,
        from_protocol: Optional[str],
        to_protocol: Optional[str],
        approved: int,
        expected_apy_improvement: Optional[Decimal] = None,
        risk_score: Optional[Decimal] = None,
    ) -> None:
        """Persist an optimization decision for auditability.

        This is what makes `scripts/daily_check.py`'s gate-rejection stats
        real instead of always reporting zero. No-op if no database is
        configured (e.g. in unit tests).

        Args:
            decision_type: Category of decision (e.g. "rebalance", "idle_deployment")
            rationale: Human-readable explanation of the outcome
            from_protocol: Source protocol, if any
            to_protocol: Target protocol
            approved: 1=approved, -1=rejected, 0=pending (see Decision model)
            expected_apy_improvement: APY delta driving the decision, if known
            risk_score: Risk score from RiskAssessorAgent, if computed
        """
        if self.database is None:
            return

        try:
            async with self.database.get_session() as session:
                BaseRepository(session, Decision).create(
                    decision_type=decision_type,
                    rationale=rationale,
                    from_protocol=from_protocol,
                    to_protocol=to_protocol,
                    expected_apy_improvement=expected_apy_improvement,
                    risk_score=int(risk_score) if risk_score is not None else None,
                    approved=approved,
                )
        except Exception as e:
            logger.error(f"Failed to record decision: {e}", exc_info=True)

    async def _deploy_idle_capital(
        self, idle_capital: Dict[str, Decimal]
    ) -> List[RebalanceExecution]:
        """Deploy idle capital to the best yield opportunity.

        Args:
            idle_capital: Dict of token -> idle amount

        Returns:
            List of RebalanceExecution results
        """
        executions: List[RebalanceExecution] = []

        # Only deploy to protocols the strategy actually supports execution
        # for — the scanner also returns protocols like Morpho that are
        # scanned for yield comparison but whose deposit/withdraw isn't
        # implemented yet, and would fail at execution time.
        protocol_allowlist = getattr(self.optimizer.strategy, "supported_protocols", None)

        for token, amount in idle_capital.items():
            try:
                # Find best yield for this token
                best_opportunity = await self.yield_scanner.find_best_yield(
                    token, protocol_allowlist=protocol_allowlist
                )

                if not best_opportunity:
                    logger.warning(f"No yield opportunity found for {token}")
                    continue

                logger.info(
                    f"📊 Best opportunity for {amount} {token}: "
                    f"{best_opportunity.protocol} @ {best_opportunity.apy}% APY"
                )

                # Check daily limits
                if not self._check_daily_limits():
                    logger.warning(
                        "Daily limits reached, skipping idle capital deployment"
                    )
                    break

                # Create deployment recommendation (from_protocol=None indicates new deposit)
                recommendation = RebalanceRecommendation(
                    from_protocol=None,  # No source - this is new capital
                    to_protocol=best_opportunity.protocol,
                    token=token,
                    amount=amount,
                    expected_apy=best_opportunity.apy,
                    reason=f"Deploy idle {token} to highest-yielding protocol",
                    confidence=80,  # High confidence for simple deployment
                )

                # Check profitability (mainly gas cost vs yield)
                if not await self._is_deployment_profitable(recommendation):
                    logger.info("Skipping deployment - not profitable after gas costs")
                    self.status.total_opportunities_skipped += 1
                    await self._record_decision(
                        decision_type="idle_deployment",
                        rationale="Unprofitable after gas costs",
                        from_protocol=None,
                        to_protocol=best_opportunity.protocol,
                        approved=-1,
                        expected_apy_improvement=best_opportunity.apy,
                    )
                    continue

                # Check risk (CRITICAL always blocks, HIGH blocks unless
                # explicitly allowed via config)
                risk_assessment = await self.risk_assessor.assess_rebalance_risk(
                    from_protocol=None,
                    to_protocol=best_opportunity.protocol,
                    amount=amount,
                    requires_swap=False,
                )
                if not self.risk_assessor.should_proceed(
                    risk_assessment,
                    allow_high_risk=self.config.get("allow_high_risk", False),
                ):
                    logger.warning(
                        f"Skipping deployment blocked by risk assessment "
                        f"({risk_assessment.risk_level.value}): "
                        f"{token} → {best_opportunity.protocol}"
                    )
                    self.status.total_opportunities_skipped += 1
                    await self._record_decision(
                        decision_type="idle_deployment",
                        rationale=f"Blocked by risk assessment: {risk_assessment.recommendation}",
                        from_protocol=None,
                        to_protocol=best_opportunity.protocol,
                        approved=-1,
                        expected_apy_improvement=best_opportunity.apy,
                        risk_score=risk_assessment.risk_score,
                    )
                    continue

                await self._record_decision(
                    decision_type="idle_deployment",
                    rationale=recommendation.reason,
                    from_protocol=None,
                    to_protocol=best_opportunity.protocol,
                    approved=1,
                    expected_apy_improvement=best_opportunity.apy,
                    risk_score=risk_assessment.risk_score,
                )

                # Execute deployment
                logger.info(f"🚀 Deploying {amount} {token} → {best_opportunity.protocol}")

                execution = await self.rebalance_executor.execute_rebalance(
                    recommendation
                )
                executions.append(execution)

                if execution.success:
                    self.status.total_rebalances += 1
                    self.status.total_opportunities_executed += 1
                    self.status.total_gas_spent_usd += execution.total_gas_cost_usd

                    await self.audit_logger.log_event(
                        event_type=AuditEventType.REBALANCE_EXECUTED,
                        severity=AuditSeverity.INFO,
                        message=f"Idle capital deployed: {token} → {best_opportunity.protocol}",
                        metadata={
                            "action": "idle_capital_deployment",
                            "token": token,
                            "amount": float(amount),
                            "to_protocol": best_opportunity.protocol,
                            "expected_apy": float(best_opportunity.apy),
                            "gas_cost_usd": float(execution.total_gas_cost_usd),
                        },
                    )

                    logger.info(
                        f"✅ Deployment successful! Gas: ${execution.total_gas_cost_usd}"
                    )
                else:
                    self.status.total_opportunities_skipped += 1
                    logger.warning(f"❌ Deployment failed: {execution.error}")

            except Exception as e:
                logger.error(f"Error deploying {token}: {e}", exc_info=True)
                self.status.total_opportunities_skipped += 1

        return executions

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
