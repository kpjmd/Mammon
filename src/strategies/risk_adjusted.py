"""Risk-adjusted yield strategy using both profitability and risk assessment.

This strategy considers yield, profitability, AND risk, optimizing for
risk-adjusted returns rather than pure APY.

Strategy Logic:
1. Find high-yield opportunities
2. Validate profitability (ProfitabilityCalculator)
3. Assess risk (RiskAssessorAgent)
4. Filter HIGH/CRITICAL risk moves
5. Check concentration limits
6. Recommend based on risk tolerance
"""

from typing import Any, Dict, List, Optional
from decimal import Decimal
from src.strategies.base_strategy import BaseStrategy, RebalanceRecommendation
from src.strategies.profitability_calculator import ProfitabilityCalculator
from src.agents.risk_assessor import RiskAssessorAgent, RiskLevel
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RiskAdjustedStrategy(BaseStrategy):
    """Strategy optimizing for risk-adjusted returns.

    Uses both ProfitabilityCalculator AND RiskAssessorAgent to
    balance yield maximization with risk management.

    This is MAMMON's "conservative" mode: maximize yield while
    respecting risk limits and diversification.

    Attributes:
        profitability_calc: ProfitabilityCalculator instance
        risk_assessor: RiskAssessorAgent instance
        risk_tolerance: Risk tolerance level ('low', 'medium', 'high')
        allow_high_risk: Whether to allow HIGH risk moves
        max_concentration_pct: Maximum % in single protocol
        diversification_target: Target number of protocols
    """

    def __init__(
        self,
        config: Dict[str, Any],
        profitability_calc: Optional[ProfitabilityCalculator] = None,
        risk_assessor: Optional[RiskAssessorAgent] = None,
    ) -> None:
        """Initialize risk-adjusted strategy.

        Args:
            config: Strategy configuration
            profitability_calc: Optional ProfitabilityCalculator instance
            risk_assessor: Optional RiskAssessorAgent instance
        """
        super().__init__("RiskAdjusted", config)

        # Initialize components
        self.profitability_calc = profitability_calc or ProfitabilityCalculator()
        self.risk_assessor = risk_assessor or RiskAssessorAgent(config)

        # Risk parameters
        self.risk_tolerance = config.get("risk_tolerance", "medium")  # low/medium/high
        self.allow_high_risk = config.get("allow_high_risk", False)
        self.max_concentration_pct = Decimal(
            str(config.get("max_concentration_pct", 0.4))
        )  # 40%
        self.diversification_target = config.get("diversification_target", 3)

        # Same thresholds as SimpleYieldStrategy
        self.min_apy_improvement = config.get(
            "min_apy_improvement", Decimal("0.5")
        )
        self.min_rebalance_amount = config.get(
            "min_rebalance_amount", Decimal("100")
        )

        logger.info(
            f"RiskAdjustedStrategy initialized: "
            f"risk_tolerance={self.risk_tolerance}, "
            f"allow_high_risk={self.allow_high_risk}, "
            f"max_concentration={self.max_concentration_pct * 100}%"
        )

    async def analyze_opportunities(
        self,
        current_positions: Dict[str, Decimal],
        available_yields: Dict[str, Decimal],
    ) -> List[RebalanceRecommendation]:
        """Find best risk-adjusted opportunities.

        For each position, finds alternatives that pass BOTH
        profitability AND risk gates.

        Args:
            current_positions: Current positions (protocol->amount in USD)
            available_yields: Available yields (protocol->apy as percentage)

        Returns:
            List of risk-adjusted rebalance recommendations
        """
        recommendations = []

        logger.info(
            f"Analyzing {len(current_positions)} positions with risk-adjusted strategy"
        )

        # First, check current portfolio concentration
        total_value = sum(current_positions.values())
        concentration_assessment = await self.risk_assessor.assess_position_concentration(
            positions=current_positions,
            total_value=total_value,
        )

        logger.info(
            f"Current concentration risk: {concentration_assessment.risk_level.value.upper()} "
            f"(score: {concentration_assessment.risk_score:.1f}/100)"
        )

        # For each current position, find best risk-adjusted alternative
        for current_protocol, position_amount in current_positions.items():
            # Skip positions below minimum
            if position_amount < self.min_rebalance_amount:
                continue

            current_apy = available_yields.get(current_protocol, Decimal("0"))

            # Find alternatives with better APY
            candidates = []
            for protocol, apy in available_yields.items():
                if protocol == current_protocol:
                    continue

                apy_improvement = apy - current_apy
                if apy_improvement < self.min_apy_improvement:
                    continue

                candidates.append((protocol, apy, apy_improvement))

            if not candidates:
                logger.debug(f"{current_protocol} has no better alternatives")
                continue

            # Sort candidates by APY (highest first)
            candidates.sort(key=lambda x: x[1], reverse=True)

            # Evaluate each candidate
            for target_protocol, target_apy, apy_improvement in candidates:
                # 1. Check profitability
                profitability = await self.profitability_calc.calculate_profitability(
                    current_apy=current_apy,
                    target_apy=target_apy,
                    position_size_usd=position_amount,
                    requires_swap=False,
                )

                if not profitability.is_profitable:
                    logger.debug(
                        f"Skipping {current_protocol} → {target_protocol}: unprofitable"
                    )
                    continue

                # 2. Assess rebalance risk
                rebalance_risk = await self.risk_assessor.assess_rebalance_risk(
                    from_protocol=current_protocol,
                    to_protocol=target_protocol,
                    amount=position_amount,
                    requires_swap=False,
                )

                # 3. Check if should proceed based on risk
                if not self.risk_assessor.should_proceed(
                    rebalance_risk, allow_high_risk=self.allow_high_risk
                ):
                    logger.info(
                        f"❌ BLOCKED BY RISK: {current_protocol} → {target_protocol} - "
                        f"{rebalance_risk.risk_level.value.upper()} risk "
                        f"(score: {rebalance_risk.risk_score:.1f}/100)"
                    )
                    continue

                # 4. Check if move would create over-concentration
                # Simulate new positions after rebalance
                simulated_positions = current_positions.copy()
                simulated_positions[current_protocol] = Decimal("0")
                simulated_positions[target_protocol] = simulated_positions.get(
                    target_protocol, Decimal("0")
                ) + position_amount

                # Remove zero positions
                simulated_positions = {
                    k: v for k, v in simulated_positions.items() if v > 0
                }

                simulated_concentration = await self.risk_assessor.assess_position_concentration(
                    positions=simulated_positions,
                    total_value=total_value,
                )

                # Check if concentration would become CRITICAL
                if simulated_concentration.risk_level == RiskLevel.CRITICAL:
                    logger.info(
                        f"❌ BLOCKED BY CONCENTRATION: {current_protocol} → {target_protocol} - "
                        f"would create CRITICAL concentration"
                    )
                    continue

                # Passed all gates! Create recommendation
                recommendation = RebalanceRecommendation(
                    from_protocol=current_protocol,
                    to_protocol=target_protocol,
                    token="UNKNOWN",
                    amount=position_amount,
                    expected_apy=target_apy,
                    reason=(
                        f"APY: {current_apy}% → {target_apy}% (+{apy_improvement}%). "
                        f"Net gain: ${profitability.net_gain_first_year:.2f}/yr, "
                        f"break-even: {profitability.break_even_days}d. "
                        f"Risk: {rebalance_risk.risk_level.value.upper()} "
                        f"({rebalance_risk.risk_score:.0f}/100)"
                    ),
                    confidence=self._calculate_risk_adjusted_confidence(
                        profitability=profitability,
                        risk_assessment=rebalance_risk,
                    ),
                )
                recommendations.append(recommendation)

                logger.info(
                    f"✅ RECOMMEND (risk-adjusted): {current_protocol} → {target_protocol} "
                    f"(${position_amount:,.0f} @ {target_apy}% APY, "
                    f"risk: {rebalance_risk.risk_level.value})"
                )

                # Only recommend first viable alternative (conservative)
                break

        logger.info(
            f"Generated {len(recommendations)} risk-adjusted recommendations"
        )
        return recommendations

    def calculate_optimal_allocation(
        self,
        total_capital: Decimal,
        opportunities: Dict[str, Decimal],
    ) -> Dict[str, Decimal]:
        """Allocate capital using risk-adjusted diversification.

        Unlike SimpleYield (100% to best), this diversifies across
        top opportunities for risk management.

        Args:
            total_capital: Total capital to allocate (USD)
            opportunities: Available opportunities (protocol->apy)

        Returns:
            Diversified allocation map
        """
        if not opportunities:
            return {}

        # Sort opportunities by APY (highest first)
        sorted_opps = sorted(
            opportunities.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        # Take top N based on diversification target
        num_protocols = min(self.diversification_target, len(sorted_opps))
        top_protocols = sorted_opps[:num_protocols]

        # Allocate using weighted distribution
        # Weight by APY, but cap max allocation
        total_weight = sum(apy for _, apy in top_protocols)

        allocation = {}
        remaining_capital = total_capital

        for i, (protocol, apy) in enumerate(top_protocols):
            if i == len(top_protocols) - 1:
                # Last protocol gets remainder
                amount = remaining_capital
            else:
                # Weight by APY but respect max concentration
                weight = apy / total_weight
                max_allowed = total_capital * self.max_concentration_pct
                amount = min(total_capital * weight, max_allowed)

            allocation[protocol] = amount
            remaining_capital -= amount

        logger.info(
            f"Optimal allocation across {len(allocation)} protocols: "
            f"{', '.join(f'{p}: ${a:,.0f}' for p, a in allocation.items())}"
        )

        return allocation

    def should_rebalance(
        self,
        current_apy: Decimal,
        target_apy: Decimal,
        gas_cost: Decimal,
        amount: Decimal,
    ) -> bool:
        """Evaluate rebalancing with profitability check.

        Same logic as SimpleYieldStrategy for this method.

        Args:
            current_apy: Current APY
            target_apy: Target APY
            gas_cost: Gas cost
            amount: Amount to rebalance

        Returns:
            True if profitable
        """
        # Check basic thresholds
        apy_improvement = target_apy - current_apy

        if apy_improvement < self.min_apy_improvement:
            return False

        if amount < self.min_rebalance_amount:
            return False

        # Simple profitability check
        annual_gain = amount * (apy_improvement / Decimal(100))

        return annual_gain > gas_cost

    def _calculate_risk_adjusted_confidence(
        self,
        profitability,
        risk_assessment,
    ) -> int:
        """Calculate confidence adjusted for both profitability and risk.

        Args:
            profitability: MoveProfitability result
            risk_assessment: RiskAssessment result

        Returns:
            Risk-adjusted confidence score 0-100
        """
        # Start with profitability-based confidence (0-60)
        confidence = 40

        # Profitability bonuses (+0-30 points)
        if profitability.net_gain_first_year > 100:
            confidence += min(15, int(profitability.net_gain_first_year / 20))

        if profitability.break_even_days <= 7:
            confidence += 10
        elif profitability.break_even_days <= 14:
            confidence += 5

        # Risk-based adjustment (+0-30 points or penalty)
        risk_score = risk_assessment.risk_score

        if risk_score <= 25:  # LOW risk
            confidence += 30
        elif risk_score <= 50:  # MEDIUM risk
            confidence += 15
        elif risk_score <= 75:  # HIGH risk
            confidence += 5
        else:  # CRITICAL risk (shouldn't happen if gates work)
            confidence -= 20

        return max(0, min(100, confidence))
