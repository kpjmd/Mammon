"""Profitability calculator for rebalancing decisions.

This module implements MAMMON's competitive moat: mathematically proving
every rebalancing decision is profitable before execution.

Competitive Analysis: None of the analyzed AI agents (Giza ARMA, Fungi, Mamo)
provide profitability proofs. This is MAMMON's differentiator for x402.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from enum import Enum

from src.blockchain.gas_estimator import GasEstimator
from src.blockchain.slippage_calculator import SlippageCalculator
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TransactionType(Enum):
    """Types of transactions involved in rebalancing."""

    WITHDRAW = "withdraw"
    SWAP = "swap"
    DEPOSIT = "deposit"
    APPROVE = "approve"


@dataclass
class RebalancingCosts:
    """Detailed breakdown of all rebalancing costs.

    Attributes:
        gas_withdraw: Gas cost for withdrawing from source protocol (USD)
        gas_approve: Gas cost for token approval if needed (USD)
        gas_swap: Gas cost for token swap if needed (USD)
        gas_deposit: Gas cost for depositing to target protocol (USD)
        slippage_cost: Expected slippage cost for swaps (USD)
        protocol_fees: Protocol fees if any (USD)
        total_cost: Sum of all costs (USD)
    """

    gas_withdraw: Decimal
    gas_approve: Decimal
    gas_swap: Decimal
    gas_deposit: Decimal
    slippage_cost: Decimal
    protocol_fees: Decimal
    total_cost: Decimal


@dataclass
class MoveProfitability:
    """Comprehensive profitability analysis for a rebalancing move.

    This is MAMMON's competitive advantage: transparent, provable profitability.

    Attributes:
        apy_improvement: APY improvement from the move (percentage)
        position_size: Size of position being moved (USD)
        annual_gain_usd: Expected annual gain from APY improvement (USD)
        costs: Detailed breakdown of all costs
        net_gain_first_year: Net gain in first year after costs (USD)
        break_even_days: Days to recover costs from APY improvement
        roi_on_costs: Return on investment for costs (percentage)
        is_profitable: Whether move passes all profitability gates
        rejection_reasons: List of reasons if unprofitable
        detailed_breakdown: Human-readable detailed explanation
    """

    apy_improvement: Decimal
    position_size: Decimal
    annual_gain_usd: Decimal
    costs: RebalancingCosts
    net_gain_first_year: Decimal
    break_even_days: int
    roi_on_costs: Decimal
    is_profitable: bool
    rejection_reasons: list[str]
    detailed_breakdown: str


class ProfitabilityCalculator:
    """Calculate and validate profitability of rebalancing moves.

    MAMMON's Competitive Moat: Guarantee profitability before execution.

    Competitors (Giza ARMA, Fungi, Mamo) execute rebalances without
    profitability proofs. MAMMON guarantees:
    - Net gain ≥ configured minimum (default $10/year)
    - Break-even ≤ configured maximum (default 30 days)
    - Total costs < configured maximum % of position (default 1%)

    Attributes:
        min_annual_gain_usd: Minimum annual net gain required
        max_break_even_days: Maximum break-even period in days
        max_cost_pct: Maximum cost as % of position size
        gas_estimator: Gas cost estimator
        slippage_calculator: Slippage calculator for swap costs
    """

    # Default gas estimates for different operations (in gas units)
    DEFAULT_GAS_ESTIMATES = {
        TransactionType.WITHDRAW: 150_000,  # Lending withdrawal
        TransactionType.APPROVE: 50_000,  # ERC20 approval
        TransactionType.SWAP: 200_000,  # DEX swap
        TransactionType.DEPOSIT: 150_000,  # Lending deposit
    }

    def __init__(
        self,
        min_annual_gain_usd: Decimal = Decimal("10"),
        max_break_even_days: int = 30,
        max_cost_pct: Decimal = Decimal("0.01"),
        gas_estimator: Optional[GasEstimator] = None,
        slippage_calculator: Optional[SlippageCalculator] = None,
    ) -> None:
        """Initialize profitability calculator.

        Args:
            min_annual_gain_usd: Minimum annual net gain (default: $10)
            max_break_even_days: Maximum break-even period (default: 30 days)
            max_cost_pct: Maximum cost as % of position (default: 0.01 = 1%)
            gas_estimator: Gas estimator instance (optional)
            slippage_calculator: Slippage calculator (optional)
        """
        self.min_annual_gain_usd = min_annual_gain_usd
        self.max_break_even_days = max_break_even_days
        self.max_cost_pct = max_cost_pct
        self.gas_estimator = gas_estimator
        self.slippage_calculator = slippage_calculator or SlippageCalculator()

        logger.info(
            f"Initialized ProfitabilityCalculator: "
            f"min_gain=${min_annual_gain_usd}, "
            f"max_break_even={max_break_even_days}d, "
            f"max_cost={max_cost_pct * 100}%"
        )

    async def calculate_profitability(
        self,
        current_apy: Decimal,
        target_apy: Decimal,
        position_size_usd: Decimal,
        requires_swap: bool = False,
        swap_amount_usd: Optional[Decimal] = None,
        protocol_fee_pct: Decimal = Decimal("0"),
    ) -> MoveProfitability:
        """Calculate comprehensive profitability for a rebalancing move.

        This is the core profitability gate that prevents unprofitable moves.

        Args:
            current_apy: Current position APY (e.g., Decimal("4.0") for 4%)
            target_apy: Target position APY (e.g., Decimal("8.0") for 8%)
            position_size_usd: Position size in USD
            requires_swap: Whether token swap is needed
            swap_amount_usd: Amount being swapped if different from position
            protocol_fee_pct: Protocol fees as percentage (e.g., Decimal("0.1") for 0.1%)

        Returns:
            MoveProfitability with detailed analysis and is_profitable flag
        """
        # Calculate APY improvement
        apy_improvement = target_apy - current_apy

        # Calculate annual gain from APY improvement
        annual_gain_usd = position_size_usd * (apy_improvement / Decimal(100))

        # Calculate all costs
        costs = await self._calculate_all_costs(
            position_size_usd=position_size_usd,
            requires_swap=requires_swap,
            swap_amount_usd=swap_amount_usd or position_size_usd,
            protocol_fee_pct=protocol_fee_pct,
        )

        # Calculate profitability metrics
        net_gain_first_year = annual_gain_usd - costs.total_cost

        # Calculate break-even in days
        if annual_gain_usd > 0:
            # Days = (total_cost / annual_gain) * 365
            break_even_days = int((costs.total_cost / annual_gain_usd * Decimal(365)).to_integral_value())
        else:
            break_even_days = 999999  # Never breaks even

        # Calculate ROI on costs
        if costs.total_cost > 0:
            roi_on_costs = (net_gain_first_year / costs.total_cost) * Decimal(100)
        else:
            roi_on_costs = Decimal("999999")  # Infinite ROI (zero costs)

        # Apply profitability gates
        rejection_reasons = []
        is_profitable = True

        # Gate 1: APY improvement must be positive
        if apy_improvement <= 0:
            rejection_reasons.append(
                f"No APY improvement (current: {current_apy}%, target: {target_apy}%)"
            )
            is_profitable = False

        # Gate 2: Net gain must exceed minimum
        if net_gain_first_year < self.min_annual_gain_usd:
            rejection_reasons.append(
                f"Net gain ${net_gain_first_year:.2f}/year < minimum ${self.min_annual_gain_usd}"
            )
            is_profitable = False

        # Gate 3: Break-even must be within maximum
        if break_even_days > self.max_break_even_days:
            rejection_reasons.append(
                f"Break-even {break_even_days} days > maximum {self.max_break_even_days} days"
            )
            is_profitable = False

        # Gate 4: Costs must be below maximum % of position
        cost_pct = costs.total_cost / position_size_usd if position_size_usd > 0 else Decimal(0)
        if cost_pct > self.max_cost_pct:
            rejection_reasons.append(
                f"Costs {cost_pct * 100:.2f}% of position > maximum {self.max_cost_pct * 100}%"
            )
            is_profitable = False

        # Generate detailed breakdown
        detailed_breakdown = self._generate_breakdown(
            apy_improvement=apy_improvement,
            position_size_usd=position_size_usd,
            annual_gain_usd=annual_gain_usd,
            costs=costs,
            net_gain_first_year=net_gain_first_year,
            break_even_days=break_even_days,
            roi_on_costs=roi_on_costs,
            is_profitable=is_profitable,
            rejection_reasons=rejection_reasons,
        )

        result = MoveProfitability(
            apy_improvement=apy_improvement,
            position_size=position_size_usd,
            annual_gain_usd=annual_gain_usd,
            costs=costs,
            net_gain_first_year=net_gain_first_year,
            break_even_days=break_even_days,
            roi_on_costs=roi_on_costs,
            is_profitable=is_profitable,
            rejection_reasons=rejection_reasons,
            detailed_breakdown=detailed_breakdown,
        )

        # Log result
        if is_profitable:
            logger.info(
                f"✅ PROFITABLE: APY {current_apy}% → {target_apy}% "
                f"| Net: ${net_gain_first_year:.2f}/yr "
                f"| Break-even: {break_even_days}d "
                f"| ROI: {roi_on_costs:.0f}%"
            )
        else:
            logger.warning(
                f"❌ UNPROFITABLE: {'; '.join(rejection_reasons)}"
            )

        return result

    async def _calculate_all_costs(
        self,
        position_size_usd: Decimal,
        requires_swap: bool,
        swap_amount_usd: Decimal,
        protocol_fee_pct: Decimal,
    ) -> RebalancingCosts:
        """Calculate total costs for a rebalancing move.

        Includes gas costs for all steps and slippage/fees where applicable.

        Args:
            position_size_usd: Position size in USD
            requires_swap: Whether token swap is needed
            swap_amount_usd: Amount being swapped
            protocol_fee_pct: Protocol fees as percentage

        Returns:
            RebalancingCosts with detailed breakdown
        """
        # Gas costs for each operation
        gas_withdraw = await self._estimate_gas_cost(TransactionType.WITHDRAW)
        gas_deposit = await self._estimate_gas_cost(TransactionType.DEPOSIT)

        # Swap-related costs (only if swap needed)
        if requires_swap:
            gas_approve = await self._estimate_gas_cost(TransactionType.APPROVE)
            gas_swap = await self._estimate_gas_cost(TransactionType.SWAP)
            slippage_cost = self._calculate_slippage_cost(swap_amount_usd)
        else:
            gas_approve = Decimal("0")
            gas_swap = Decimal("0")
            slippage_cost = Decimal("0")

        # Protocol fees (if any)
        protocol_fees = position_size_usd * (protocol_fee_pct / Decimal(100))

        # Total cost
        total_cost = (
            gas_withdraw
            + gas_approve
            + gas_swap
            + gas_deposit
            + slippage_cost
            + protocol_fees
        )

        return RebalancingCosts(
            gas_withdraw=gas_withdraw,
            gas_approve=gas_approve,
            gas_swap=gas_swap,
            gas_deposit=gas_deposit,
            slippage_cost=slippage_cost,
            protocol_fees=protocol_fees,
            total_cost=total_cost,
        )

    async def _estimate_gas_cost(self, tx_type: TransactionType) -> Decimal:
        """Estimate gas cost in USD for a transaction type.

        Uses GasEstimator if available, otherwise uses defaults.

        Args:
            tx_type: Type of transaction

        Returns:
            Estimated gas cost in USD
        """
        # Get gas limit estimate
        gas_limit = self.DEFAULT_GAS_ESTIMATES[tx_type]

        if self.gas_estimator:
            try:
                # Use GasEstimator to get current gas price and ETH price
                gas_price_wei = await self.gas_estimator.get_gas_price()
                gas_cost_eth = Decimal(gas_limit * gas_price_wei) / Decimal(10**18)

                # Get ETH price in USD
                eth_price_usd = await self.gas_estimator.price_oracle.get_price("ETH")

                # Convert to USD
                gas_cost_usd = gas_cost_eth * eth_price_usd

                logger.debug(
                    f"Gas cost for {tx_type.value}: "
                    f"{gas_limit} gas @ {gas_price_wei / 10**9:.2f} gwei = "
                    f"${gas_cost_usd:.4f}"
                )

                return gas_cost_usd

            except Exception as e:
                logger.warning(
                    f"Failed to estimate gas cost for {tx_type.value}: {e}. "
                    f"Using conservative fallback."
                )

        # Fallback: Conservative estimate for Base L2
        # Base typically runs at 0.001-0.01 gwei; use 0.01 gwei as conservative fallback
        gas_price_gwei = Decimal("0.01")  # Base L2 pricing (was 10 gwei for Ethereum)
        eth_price_usd = Decimal("2500")
        gas_cost_eth = (Decimal(gas_limit) * gas_price_gwei) / Decimal(10**9)
        gas_cost_usd = gas_cost_eth * eth_price_usd

        logger.debug(
            f"Gas cost for {tx_type.value} (fallback Base L2): ${gas_cost_usd:.4f}"
        )

        return gas_cost_usd

    def _calculate_slippage_cost(self, swap_amount_usd: Decimal) -> Decimal:
        """Calculate expected slippage cost for a swap.

        Uses SlippageCalculator's default slippage tolerance.

        Args:
            swap_amount_usd: Amount being swapped in USD

        Returns:
            Expected slippage cost in USD
        """
        # Get slippage percentage from calculator
        slippage_bps = self.slippage_calculator.default_slippage_bps
        slippage_pct = Decimal(slippage_bps) / Decimal(10000)

        # Calculate slippage cost
        slippage_cost = swap_amount_usd * slippage_pct

        logger.debug(
            f"Slippage cost: ${swap_amount_usd:.2f} @ {slippage_bps}bps = "
            f"${slippage_cost:.4f}"
        )

        return slippage_cost

    def _generate_breakdown(
        self,
        apy_improvement: Decimal,
        position_size_usd: Decimal,
        annual_gain_usd: Decimal,
        costs: RebalancingCosts,
        net_gain_first_year: Decimal,
        break_even_days: int,
        roi_on_costs: Decimal,
        is_profitable: bool,
        rejection_reasons: list[str],
    ) -> str:
        """Generate detailed human-readable breakdown.

        Args:
            apy_improvement: APY improvement percentage
            position_size_usd: Position size
            annual_gain_usd: Annual gain from APY
            costs: Detailed costs
            net_gain_first_year: Net gain after costs
            break_even_days: Days to break even
            roi_on_costs: ROI on costs
            is_profitable: Whether move is profitable
            rejection_reasons: Reasons if unprofitable

        Returns:
            Human-readable breakdown string
        """
        breakdown = [
            "=" * 60,
            "PROFITABILITY ANALYSIS",
            "=" * 60,
            "",
            "REVENUE:",
            f"  APY Improvement:     +{apy_improvement:.2f}%",
            f"  Position Size:       ${position_size_usd:,.2f}",
            f"  Annual Gain:         ${annual_gain_usd:,.2f}/year",
            "",
            "COSTS:",
            f"  Gas (Withdraw):      ${costs.gas_withdraw:.4f}",
            f"  Gas (Approve):       ${costs.gas_approve:.4f}",
            f"  Gas (Swap):          ${costs.gas_swap:.4f}",
            f"  Gas (Deposit):       ${costs.gas_deposit:.4f}",
            f"  Slippage:            ${costs.slippage_cost:.4f}",
            f"  Protocol Fees:       ${costs.protocol_fees:.4f}",
            f"  Total Costs:         ${costs.total_cost:.4f}",
            "",
            "PROFITABILITY:",
            f"  Net Gain (Year 1):   ${net_gain_first_year:,.2f}",
            f"  Break-even:          {break_even_days} days",
            f"  ROI on Costs:        {roi_on_costs:,.0f}%",
            "",
        ]

        if is_profitable:
            breakdown.extend([
                "DECISION: ✅ PROFITABLE",
                "  All profitability gates passed.",
                "=" * 60,
            ])
        else:
            breakdown.extend([
                "DECISION: ❌ UNPROFITABLE",
                "  Rejection reasons:",
            ])
            for reason in rejection_reasons:
                breakdown.append(f"    - {reason}")
            breakdown.append("=" * 60)

        return "\n".join(breakdown)
