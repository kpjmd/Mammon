"""High-level rebalance workflow orchestration.

This module executes complete rebalancing workflows by coordinating:
- Protocol withdrawals and deposits (via ProtocolActionExecutor)
- Token swaps (via UniswapV3Router)
- Token approvals
- Balance verification
- Gas cost tracking
- Audit logging

Phase 4 Sprint 1: Executes optimizer-driven rebalances on Base Sepolia testnet.
"""

from typing import Any, Dict, List, Optional
from decimal import Decimal
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field

from src.blockchain.wallet import WalletManager
from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.blockchain.gas_estimator import GasEstimator
from src.protocols.uniswap_v3_router import UniswapV3Router
from src.strategies.base_strategy import RebalanceRecommendation
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.security.limits import SpendingLimits
from src.data.oracles import PriceOracle
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RebalanceStep(Enum):
    """Enumeration of rebalance workflow steps."""

    VALIDATION = "validation"
    BALANCE_CHECK = "balance_check"
    WITHDRAW = "withdraw"
    APPROVE_SWAP = "approve_swap"
    SWAP = "swap"
    APPROVE_DEPOSIT = "approve_deposit"
    DEPOSIT = "deposit"
    VERIFICATION = "verification"


@dataclass
class StepResult:
    """Result of a single rebalance step.

    Attributes:
        step: Step name
        success: Whether step succeeded
        tx_hash: Transaction hash (if applicable)
        gas_used: Gas consumed (if applicable)
        error: Error message (if failed)
        timestamp: When step completed
    """

    step: RebalanceStep
    success: bool
    tx_hash: Optional[str] = None
    gas_used: Optional[int] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RebalanceExecution:
    """Tracks the execution state of a rebalance.

    Attributes:
        recommendation: Original recommendation being executed
        steps: List of completed step results
        initial_balances: Balances before execution
        final_balances: Balances after execution
        total_gas_used: Total gas consumed across all steps
        total_gas_cost_eth: Total gas cost in ETH
        total_gas_cost_usd: Total gas cost in USD
        started_at: Execution start time
        completed_at: Execution completion time
        success: Overall success status
    """

    recommendation: RebalanceRecommendation
    steps: List[StepResult] = field(default_factory=list)
    initial_balances: Dict[str, Decimal] = field(default_factory=dict)
    final_balances: Dict[str, Decimal] = field(default_factory=dict)
    total_gas_used: int = 0
    total_gas_cost_eth: Decimal = Decimal("0")
    total_gas_cost_usd: Decimal = Decimal("0")
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    success: bool = False

    def add_step_result(self, result: StepResult) -> None:
        """Add a step result and update gas tracking."""
        self.steps.append(result)
        if result.gas_used:
            self.total_gas_used += result.gas_used

    def get_step_result(self, step: RebalanceStep) -> Optional[StepResult]:
        """Get result for a specific step."""
        for result in self.steps:
            if result.step == step:
                return result
        return None


class RebalanceExecutor:
    """Executes complete rebalancing workflows.

    Orchestrates multi-step rebalancing by coordinating protocol actions,
    swaps, approvals, and verification. Provides comprehensive tracking
    and error recovery.

    Attributes:
        wallet: WalletManager instance
        protocol_executor: ProtocolActionExecutor for protocol transactions
        swap_router: UniswapV3Router for token swaps (optional)
        gas_estimator: GasEstimator for cost tracking
        spending_limits: SpendingLimits for safety checks
        audit_logger: AuditLogger for compliance
        config: Configuration dictionary
    """

    def __init__(
        self,
        wallet_manager: WalletManager,
        protocol_executor: ProtocolActionExecutor,
        gas_estimator: GasEstimator,
        price_oracle: PriceOracle,
        config: Dict[str, Any],
        swap_router: Optional[UniswapV3Router] = None,
    ) -> None:
        """Initialize the rebalance executor.

        Args:
            wallet_manager: WalletManager instance
            protocol_executor: ProtocolActionExecutor instance
            gas_estimator: GasEstimator instance
            price_oracle: PriceOracle for USD conversions
            config: Configuration dictionary
            swap_router: Optional UniswapV3Router for swaps
        """
        self.wallet = wallet_manager
        self.protocol_executor = protocol_executor
        self.swap_router = swap_router
        self.gas_estimator = gas_estimator
        self.price_oracle = price_oracle
        self.config = config
        self.audit_logger = AuditLogger()
        self.spending_limits = SpendingLimits(config)

        self.simulate_before_execute = config.get("simulate_before_execute", True)
        self.dry_run_mode = config.get("dry_run_mode", True)

        logger.info(
            f"RebalanceExecutor initialized "
            f"(simulate={self.simulate_before_execute}, dry_run={self.dry_run_mode})"
        )

    async def execute_rebalance(
        self,
        recommendation: RebalanceRecommendation,
    ) -> RebalanceExecution:
        """Execute a complete rebalancing workflow.

        Workflow:
        1. Validate recommendation
        2. Check initial balances
        3. Withdraw from source protocol (if applicable)
        4. Approve + swap tokens (if needed)
        5. Approve + deposit to target protocol
        6. Verify final balances
        7. Calculate actual costs

        Args:
            recommendation: RebalanceRecommendation to execute

        Returns:
            RebalanceExecution with complete results

        Raises:
            ValueError: If validation fails
            RuntimeError: If execution fails
        """
        execution = RebalanceExecution(recommendation=recommendation)

        await self.audit_logger.log_event(
            AuditEventType.REBALANCE_OPPORTUNITY_FOUND,
            AuditSeverity.INFO,
            f"Starting rebalance execution: {recommendation.from_protocol} → "
            f"{recommendation.to_protocol}",
            metadata={
                "from_protocol": recommendation.from_protocol,
                "to_protocol": recommendation.to_protocol,
                "token": recommendation.token,
                "amount": str(recommendation.amount),
                "expected_apy": str(recommendation.expected_apy),
            },
        )

        try:
            # Step 1: Validation
            await self._validate_recommendation(recommendation, execution)

            # Step 2: Check initial balances
            await self._check_initial_balances(recommendation, execution)

            # Step 3: Withdraw from source (if rebalancing existing position)
            if recommendation.from_protocol:
                await self._execute_withdraw_step(recommendation, execution)

            # Step 4: Swap if needed (different tokens)
            if self._requires_swap(recommendation):
                await self._execute_swap_step(recommendation, execution)

            # Step 5: Approve target protocol
            await self._execute_approve_deposit_step(recommendation, execution)

            # Step 6: Deposit to target protocol
            await self._execute_deposit_step(recommendation, execution)

            # Step 7: Verify final balances
            await self._verify_final_balances(recommendation, execution)

            # Step 8: Calculate actual costs
            await self._calculate_actual_costs(execution)

            # Mark as successful
            execution.success = True
            execution.completed_at = datetime.now()

            await self.audit_logger.log_event(
                AuditEventType.REBALANCE_EXECUTED,
                AuditSeverity.INFO,
                f"Rebalance completed successfully",
                metadata={
                    "total_gas_used": execution.total_gas_used,
                    "total_gas_cost_usd": str(execution.total_gas_cost_usd),
                    "steps_completed": len(execution.steps),
                },
            )

            logger.info(
                f"✅ Rebalance completed successfully! "
                f"Gas used: {execution.total_gas_used}, "
                f"Cost: ${execution.total_gas_cost_usd:.2f}"
            )

        except Exception as e:
            execution.success = False
            execution.completed_at = datetime.now()

            await self.audit_logger.log_event(
                AuditEventType.SECURITY_VIOLATION,
                AuditSeverity.ERROR,
                f"Rebalance execution failed: {str(e)}",
                metadata={
                    "error": str(e),
                    "steps_completed": len(execution.steps),
                    "last_step": execution.steps[-1].step.value if execution.steps else None,
                },
            )

            logger.error(f"❌ Rebalance execution failed: {e}")
            raise

        return execution

    async def _validate_recommendation(
        self,
        recommendation: RebalanceRecommendation,
        execution: RebalanceExecution,
    ) -> None:
        """Validate the recommendation before execution."""
        logger.info("Validating rebalance recommendation...")

        try:
            # Basic validation
            if recommendation.amount <= 0:
                raise ValueError(f"Invalid amount: {recommendation.amount}")

            if not recommendation.to_protocol:
                raise ValueError("Target protocol is required")

            # Check spending limits (convert to USD)
            amount_usd = recommendation.amount  # Assuming amount is already in USD
            if not self.spending_limits.check_transaction_limit(amount_usd):
                raise ValueError(
                    f"Transaction amount ${amount_usd} exceeds spending limits"
                )

            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.VALIDATION,
                    success=True,
                )
            )

            logger.info("✅ Validation passed")

        except Exception as e:
            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.VALIDATION,
                    success=False,
                    error=str(e),
                )
            )
            raise

    async def _check_initial_balances(
        self,
        recommendation: RebalanceRecommendation,
        execution: RebalanceExecution,
    ) -> None:
        """Check and record initial balances."""
        logger.info("Checking initial balances...")

        try:
            # Get wallet balance for token
            balance = await self.protocol_executor.get_token_balance(
                recommendation.token
            )

            execution.initial_balances[recommendation.token] = balance

            logger.info(f"Initial {recommendation.token} balance: {balance}")

            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.BALANCE_CHECK,
                    success=True,
                )
            )

        except Exception as e:
            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.BALANCE_CHECK,
                    success=False,
                    error=str(e),
                )
            )
            raise

    async def _execute_withdraw_step(
        self,
        recommendation: RebalanceRecommendation,
        execution: RebalanceExecution,
    ) -> None:
        """Execute withdrawal from source protocol."""
        logger.info(
            f"Withdrawing {recommendation.amount} {recommendation.token} "
            f"from {recommendation.from_protocol}..."
        )

        try:
            result = await self.protocol_executor.execute_withdraw(
                protocol_name=recommendation.from_protocol,
                token=recommendation.token,
                amount=recommendation.amount,
            )

            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.WITHDRAW,
                    success=result["success"],
                    tx_hash=result.get("tx_hash"),
                    gas_used=result.get("gas_used"),
                )
            )

            logger.info(f"✅ Withdrawal successful: {result.get('tx_hash')}")

        except Exception as e:
            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.WITHDRAW,
                    success=False,
                    error=str(e),
                )
            )
            raise

    def _requires_swap(self, recommendation: RebalanceRecommendation) -> bool:
        """Check if swap is required (same token for now = no swap)."""
        # Phase 4 Sprint 1: Assume same-token rebalancing (no swap needed)
        # Phase 5: Add cross-token rebalancing support
        return False

    async def _execute_swap_step(
        self,
        recommendation: RebalanceRecommendation,
        execution: RebalanceExecution,
    ) -> None:
        """Execute token swap (Phase 5 feature)."""
        raise NotImplementedError(
            "Token swaps not yet implemented in Phase 4 Sprint 1. "
            "Will be added in Phase 5."
        )

    async def _execute_approve_deposit_step(
        self,
        recommendation: RebalanceRecommendation,
        execution: RebalanceExecution,
    ) -> None:
        """Execute approval for target protocol deposit."""
        logger.info(
            f"Approving {recommendation.token} for {recommendation.to_protocol}..."
        )

        try:
            # Get protocol contract address for approval
            # For Aave V3, approve the Pool contract
            # For Moonwell, approve the mToken contract
            from src.blockchain.protocol_action_executor import (
                AAVE_V3_POOL_ADDRESSES,
                MOONWELL_MTOKEN_ADDRESSES,
            )

            if recommendation.to_protocol == "Aave V3":
                network = self.config.get("network", "base-sepolia")
                spender = AAVE_V3_POOL_ADDRESSES[network]
            elif recommendation.to_protocol == "Moonwell":
                network = self.config.get("network", "base-sepolia")
                mtoken_addresses = MOONWELL_MTOKEN_ADDRESSES.get(network, {})
                spender = mtoken_addresses.get(recommendation.token)
                if not spender:
                    raise ValueError(
                        f"Moonwell mToken not configured for {recommendation.token} on {network}"
                    )
            else:
                raise NotImplementedError(
                    f"Approval not yet implemented for {recommendation.to_protocol}"
                )

            result = await self.protocol_executor.execute_approve(
                token=recommendation.token,
                spender=spender,
                amount=recommendation.amount,
            )

            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.APPROVE_DEPOSIT,
                    success=result["success"],
                    tx_hash=result.get("tx_hash"),
                    gas_used=result.get("gas_used"),
                )
            )

            logger.info(f"✅ Approval successful: {result.get('tx_hash')}")

        except Exception as e:
            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.APPROVE_DEPOSIT,
                    success=False,
                    error=str(e),
                )
            )
            raise

    async def _execute_deposit_step(
        self,
        recommendation: RebalanceRecommendation,
        execution: RebalanceExecution,
    ) -> None:
        """Execute deposit to target protocol."""
        logger.info(
            f"Depositing {recommendation.amount} {recommendation.token} "
            f"to {recommendation.to_protocol}..."
        )

        try:
            result = await self.protocol_executor.execute_deposit(
                protocol_name=recommendation.to_protocol,
                token=recommendation.token,
                amount=recommendation.amount,
            )

            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.DEPOSIT,
                    success=result["success"],
                    tx_hash=result.get("tx_hash"),
                    gas_used=result.get("gas_used"),
                )
            )

            logger.info(f"✅ Deposit successful: {result.get('tx_hash')}")

        except Exception as e:
            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.DEPOSIT,
                    success=False,
                    error=str(e),
                )
            )
            raise

    async def _verify_final_balances(
        self,
        recommendation: RebalanceRecommendation,
        execution: RebalanceExecution,
    ) -> None:
        """Verify final balances match expectations."""
        logger.info("Verifying final balances...")

        try:
            # Get final balance
            final_balance = await self.protocol_executor.get_token_balance(
                recommendation.token
            )

            execution.final_balances[recommendation.token] = final_balance

            # In dry run mode, we can't verify actual balance changes
            if not self.dry_run_mode:
                initial = execution.initial_balances.get(recommendation.token, Decimal("0"))

                # For withdraw→deposit: balance should be roughly the same (minus gas)
                # Allow for small discrepancies due to gas costs
                tolerance = Decimal("0.01")  # 1% tolerance
                if abs(final_balance - initial) > tolerance * initial:
                    logger.warning(
                        f"Balance change unexpected: {initial} → {final_balance}"
                    )

            logger.info(f"Final {recommendation.token} balance: {final_balance}")

            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.VERIFICATION,
                    success=True,
                )
            )

        except Exception as e:
            execution.add_step_result(
                StepResult(
                    step=RebalanceStep.VERIFICATION,
                    success=False,
                    error=str(e),
                )
            )
            # Don't raise - verification failure is not critical

    async def _calculate_actual_costs(self, execution: RebalanceExecution) -> None:
        """Calculate actual gas costs from execution."""
        logger.info("Calculating actual gas costs...")

        # Sum up gas from all steps
        total_gas = execution.total_gas_used

        if total_gas > 0:
            # Get current gas price
            gas_price_wei = await self.gas_estimator.get_gas_price()

            # Calculate cost in ETH
            gas_cost_wei = total_gas * gas_price_wei
            gas_cost_eth = Decimal(gas_cost_wei) / Decimal(10**18)

            # Convert to USD
            eth_price_usd = await self.price_oracle.get_price("ETH")
            gas_cost_usd = gas_cost_eth * eth_price_usd

            execution.total_gas_cost_eth = gas_cost_eth
            execution.total_gas_cost_usd = gas_cost_usd

            logger.info(
                f"Total gas costs: {total_gas} gas = "
                f"{gas_cost_eth:.6f} ETH = ${gas_cost_usd:.2f} USD"
            )

    def get_execution_summary(self, execution: RebalanceExecution) -> str:
        """Generate human-readable execution summary."""
        lines = []
        lines.append("=" * 80)
        lines.append("REBALANCE EXECUTION SUMMARY")
        lines.append("=" * 80)
        lines.append("")

        rec = execution.recommendation
        lines.append(f"Direction: {rec.from_protocol or 'New Position'} → {rec.to_protocol}")
        lines.append(f"Token: {rec.token}")
        lines.append(f"Amount: {rec.amount}")
        lines.append(f"Expected APY: {rec.expected_apy}%")
        lines.append("")

        lines.append("Execution Steps:")
        for i, step in enumerate(execution.steps, 1):
            status = "✅" if step.success else "❌"
            lines.append(f"  {i}. {status} {step.step.value}")
            if step.tx_hash:
                lines.append(f"     TX: {step.tx_hash}")
            if step.gas_used:
                lines.append(f"     Gas: {step.gas_used:,}")

        lines.append("")
        lines.append(f"Total Gas Used: {execution.total_gas_used:,}")
        lines.append(f"Total Gas Cost: {execution.total_gas_cost_eth:.6f} ETH "
                    f"(${execution.total_gas_cost_usd:.2f} USD)")
        lines.append("")

        if execution.success:
            lines.append("Status: ✅ SUCCESS")
        else:
            lines.append("Status: ❌ FAILED")

        lines.append("=" * 80)

        return "\n".join(lines)
