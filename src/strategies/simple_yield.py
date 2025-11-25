"""Simple yield strategy prioritizing highest APY.

This strategy simply chases the highest available APY with
profitability validation via ProfitabilityCalculator.

Strategy Logic:
1. Find highest APY opportunity
2. Validate profitability (uses ProfitabilityCalculator)
3. Recommend if profitable
4. No risk weighting (pure APY optimization)
"""

from typing import Any, Dict, List, Optional
from decimal import Decimal
from src.strategies.base_strategy import BaseStrategy, RebalanceRecommendation
from src.strategies.profitability_calculator import ProfitabilityCalculator
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SimpleYieldStrategy(BaseStrategy):
    """Simple strategy that prioritizes highest APY.

    Moves capital to the highest yielding opportunity after
    validating profitability via ProfitabilityCalculator.

    This is MAMMON's "aggressive" mode: maximize yield without
    risk considerations.

    Attributes:
        profitability_calc: ProfitabilityCalculator instance
        min_apy_improvement: Minimum APY improvement threshold (default: 0.5%)
        min_rebalance_amount: Minimum position size to rebalance (default: $100)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        profitability_calc: Optional[ProfitabilityCalculator] = None,
    ) -> None:
        """Initialize simple yield strategy.

        Args:
            config: Strategy configuration
            profitability_calc: Optional ProfitabilityCalculator instance
        """
        super().__init__("SimpleYield", config)

        # Initialize profitability calculator
        self.profitability_calc = profitability_calc or ProfitabilityCalculator()

        # Strategy thresholds
        self.min_apy_improvement = config.get(
            "min_apy_improvement", Decimal("0.5")
        )  # 0.5% minimum
        self.min_rebalance_amount = config.get(
            "min_rebalance_amount", Decimal("100")
        )  # $100 minimum

        # Protocol whitelist (only fully implemented protocols)
        # TODO: Implement approval/deposit for: Aerodrome, Morpho
        self.supported_protocols = config.get(
            "supported_protocols",
            ["Aave V3", "Moonwell"]  # Only these have working approval/deposit
        )

        logger.info(
            f"SimpleYieldStrategy initialized: "
            f"min_apy_improvement={self.min_apy_improvement}%, "
            f"min_rebalance_amount=${self.min_rebalance_amount}, "
            f"supported_protocols={self.supported_protocols}"
        )

    async def analyze_opportunities(
        self,
        current_positions: Dict[str, Decimal],
        available_yields: Dict[str, Decimal],
    ) -> List[RebalanceRecommendation]:
        """Find highest yield opportunities for each current position.

        For each current position, finds the best alternative yield
        and validates profitability.

        Args:
            current_positions: Current positions (protocol->amount in USD)
            available_yields: Available yields (protocol->apy as percentage)

        Returns:
            List of profitable rebalance recommendations
        """
        logger.info("🔍 DEBUG: SimpleYieldStrategy.analyze_opportunities() called")
        logger.info(f"🔍 DEBUG: current_positions = {current_positions}")
        logger.info(f"🔍 DEBUG: available_yields keys = {list(available_yields.keys())}")
        logger.info(f"🔍 DEBUG: available_yields = {available_yields}")

        recommendations = []

        logger.info(
            f"Analyzing {len(current_positions)} positions against "
            f"{len(available_yields)} available yields"
        )

        # For each current position, find best alternative
        for current_protocol, position_amount in current_positions.items():
            logger.info(f"🔍 DEBUG: Analyzing position: {current_protocol} = ${position_amount}")
            # Skip positions below minimum
            if position_amount < self.min_rebalance_amount:
                logger.debug(
                    f"Skipping {current_protocol}: position ${position_amount:.2f} "
                    f"below minimum ${self.min_rebalance_amount}"
                )
                continue

            current_apy = available_yields.get(current_protocol, Decimal("0"))
            logger.info(f"🔍 DEBUG: Current protocol '{current_protocol}' APY lookup: {current_apy}%")

            # Find best alternative (highest APY that's not current protocol)
            best_protocol = None
            best_apy = current_apy
            logger.info(f"🔍 DEBUG: Searching for better yields than {current_apy}%...")

            for protocol, apy in available_yields.items():
                # Skip unsupported protocols
                if protocol not in self.supported_protocols:
                    logger.debug(f"Skipping unsupported protocol: {protocol}")
                    continue

                if protocol != current_protocol and apy > best_apy:
                    logger.info(f"🔍 DEBUG: Found better yield: {protocol} @ {apy}% (was best_apy={best_apy}%)")
                    best_protocol = protocol
                    best_apy = apy

            # No better option found
            if best_protocol is None:
                logger.info(
                    f"🔍 DEBUG: No better option found - {current_protocol} already optimal at {current_apy}% APY"
                )
                continue

            logger.info(f"🔍 DEBUG: Best alternative: {best_protocol} @ {best_apy}%")

            # Check APY improvement threshold
            apy_improvement = best_apy - current_apy
            if apy_improvement < self.min_apy_improvement:
                logger.debug(
                    f"Skipping {current_protocol} → {best_protocol}: "
                    f"improvement {apy_improvement}% below threshold "
                    f"{self.min_apy_improvement}%"
                )
                continue

            # Validate profitability
            profitability = await self.profitability_calc.calculate_profitability(
                current_apy=current_apy,
                target_apy=best_apy,
                position_size_usd=position_amount,
                requires_swap=False,  # Assume same token for simplicity
            )

            if profitability.is_profitable:
                # Create recommendation
                # TODO: Get actual token from position data instead of hardcoding USDC
                recommendation = RebalanceRecommendation(
                    from_protocol=current_protocol,
                    to_protocol=best_protocol,
                    token="USDC",  # TODO: Should come from position data
                    amount=position_amount,
                    expected_apy=best_apy,
                    current_apy=current_apy,
                    reason=(
                        f"APY improvement: {current_apy}% → {best_apy}% "
                        f"(+{apy_improvement}%). "
                        f"Net gain: ${profitability.net_gain_first_year:.2f}/year, "
                        f"break-even: {profitability.break_even_days} days"
                    ),
                    confidence=self._calculate_confidence(profitability),
                )
                recommendations.append(recommendation)

                logger.info(
                    f"✅ RECOMMEND: {current_protocol} → {best_protocol} "
                    f"(${position_amount:,.0f} @ {best_apy}% APY)"
                )
            else:
                logger.info(
                    f"❌ UNPROFITABLE: {current_protocol} → {best_protocol} - "
                    f"{'; '.join(profitability.rejection_reasons)}"
                )

        logger.info(f"Generated {len(recommendations)} recommendations")
        return recommendations

    def calculate_optimal_allocation(
        self,
        total_capital: Decimal,
        opportunities: Dict[str, Decimal],
    ) -> Dict[str, Decimal]:
        """Allocate all capital to highest yield (simple greedy approach).

        SimpleYieldStrategy puts everything in the single best opportunity.

        Args:
            total_capital: Total capital to allocate (USD)
            opportunities: Available opportunities (protocol->apy)

        Returns:
            Dict mapping protocol to allocation amount
        """
        if not opportunities:
            logger.warning("No opportunities available for allocation")
            return {}

        # Find highest APY
        best_protocol = max(opportunities, key=opportunities.get)
        best_apy = opportunities[best_protocol]

        allocation = {best_protocol: total_capital}

        logger.info(
            f"Optimal allocation: 100% to {best_protocol} "
            f"(${total_capital:,.0f} @ {best_apy}% APY)"
        )

        return allocation

    def should_rebalance(
        self,
        current_apy: Decimal,
        target_apy: Decimal,
        gas_cost: Decimal,
        amount: Decimal,
    ) -> bool:
        """Check if APY improvement justifies costs (uses ProfitabilityCalculator).

        This is a simpler sync wrapper around profitability validation.

        Args:
            current_apy: Current position APY
            target_apy: Target position APY
            gas_cost: Estimated gas cost in USD
            amount: Amount to rebalance

        Returns:
            True if rebalancing is profitable
        """
        # Check basic thresholds first (quick filters)
        apy_improvement = target_apy - current_apy

        if apy_improvement < self.min_apy_improvement:
            logger.debug(
                f"APY improvement {apy_improvement}% below threshold "
                f"{self.min_apy_improvement}%"
            )
            return False

        if amount < self.min_rebalance_amount:
            logger.debug(
                f"Amount ${amount:.2f} below minimum ${self.min_rebalance_amount}"
            )
            return False

        # Simple profitability check: annual gain > gas cost
        annual_gain = amount * (apy_improvement / Decimal(100))

        if annual_gain < gas_cost:
            logger.debug(
                f"Annual gain ${annual_gain:.2f} < gas cost ${gas_cost:.2f}"
            )
            return False

        logger.info(
            f"✅ Rebalance profitable: {current_apy}% → {target_apy}% "
            f"(${amount:,.0f}, gain: ${annual_gain:.2f}/yr, cost: ${gas_cost:.2f})"
        )
        return True

    def _calculate_confidence(self, profitability) -> int:
        """Calculate confidence score based on profitability metrics.

        Higher confidence for:
        - Higher net gain
        - Faster break-even
        - Higher ROI

        Args:
            profitability: MoveProfitability result

        Returns:
            Confidence score 0-100
        """
        # Base confidence: 60
        confidence = 60

        # Bonus for high net gain (+0-20 points)
        if profitability.net_gain_first_year > 100:
            confidence += min(20, int(profitability.net_gain_first_year / 10))

        # Bonus for fast break-even (+0-10 points)
        if profitability.break_even_days <= 7:
            confidence += 10
        elif profitability.break_even_days <= 14:
            confidence += 5

        # Bonus for high ROI (+0-10 points)
        if profitability.roi_on_costs > 1000:  # 10x ROI
            confidence += 10
        elif profitability.roi_on_costs > 500:  # 5x ROI
            confidence += 5

        return min(100, confidence)
