"""Risk assessment agent for evaluating DeFi position safety.

This module implements the agent responsible for assessing risks
of yield opportunities and rebalancing decisions.

Risk Framework:
- Protocol Safety Scores: Aave V3 (95), Morpho (90), Moonwell (85), Aerodrome (85)
- Risk Levels: LOW (0-25), MEDIUM (26-50), HIGH (51-75), CRITICAL (76-100)
- Decision Gates: CRITICAL blocks execution, HIGH requires elevated approval
"""

from typing import Any, Dict, Optional
from decimal import Decimal
from enum import Enum
from src.utils.logger import get_logger
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity

logger = get_logger(__name__)


class RiskLevel(Enum):
    """Risk level classification for DeFi positions."""

    LOW = "low"  # 0-25: Safe to proceed
    MEDIUM = "medium"  # 26-50: Normal risk
    HIGH = "high"  # 51-75: Elevated approval required
    CRITICAL = "critical"  # 76-100: Block execution


class RiskFactor(Enum):
    """Individual risk factors that contribute to overall risk score."""

    PROTOCOL_SAFETY = "protocol_safety"
    CONCENTRATION = "concentration"
    REBALANCE_AMOUNT = "rebalance_amount"
    SWAP_REQUIRED = "swap_required"
    TVL_ADEQUACY = "tvl_adequacy"
    UTILIZATION = "utilization"


class RiskAssessment:
    """Risk assessment result for a DeFi position or action.

    Attributes:
        risk_level: Overall risk classification
        risk_score: Numerical risk score (0-100, higher = riskier)
        factors: Contributing risk factors with individual scores
        recommendation: Recommended action
        detailed_analysis: Human-readable detailed breakdown
    """

    def __init__(
        self,
        risk_level: RiskLevel,
        risk_score: Decimal,
        factors: Dict[str, Any],
        recommendation: str,
        detailed_analysis: str = "",
    ) -> None:
        """Initialize a risk assessment.

        Args:
            risk_level: Overall risk classification
            risk_score: Numerical score 0-100 (higher = riskier)
            factors: Dict of risk factors and their values
            recommendation: Human-readable recommendation
            detailed_analysis: Detailed breakdown string
        """
        self.risk_level = risk_level
        self.risk_score = risk_score
        self.factors = factors
        self.recommendation = recommendation
        self.detailed_analysis = detailed_analysis


class RiskAssessorAgent:
    """Agent for assessing risks of DeFi positions and transactions.

    Evaluates protocol risks, smart contract risks, market risks,
    and provides recommendations for safe operation.

    Protocol Safety Scores (inverse scale: lower risk = higher safety):
    - Aave V3: 95/100 (battle-tested, $125M+ TVL on Base)
    - Morpho: 90/100 (Coinbase-promoted, $45M+ TVL)
    - Moonwell: 85/100 (Compound V2 fork, $32M+ TVL)
    - Aerodrome: 85/100 (Velodrome fork, $602M+ TVL)

    Risk Score Calculation (0-100, higher = riskier):
    - 0-25: LOW - Safe to proceed
    - 26-50: MEDIUM - Normal risk, proceed with monitoring
    - 51-75: HIGH - Elevated risk, requires higher approval threshold
    - 76-100: CRITICAL - Do not proceed

    Attributes:
        config: Configuration settings
        protocol_safety_scores: Safety scores by protocol name
        max_concentration_pct: Max single protocol concentration
        large_position_threshold: USD threshold for "large" position
        audit_logger: Audit logging instance
    """

    # Protocol safety scores (0-100, higher = safer)
    PROTOCOL_SAFETY_SCORES = {
        "Aave V3": 95,
        "Aave": 95,  # Alias
        "Morpho": 90,
        "Morpho Blue": 90,  # Alias
        "Moonwell": 85,
        "Aerodrome": 85,
    }

    # TVL thresholds for safety assessment (USD)
    MIN_SAFE_TVL = Decimal("1_000_000")  # $1M minimum
    COMFORTABLE_TVL = Decimal("10_000_000")  # $10M+ is very safe

    # Utilization thresholds
    HIGH_UTILIZATION_THRESHOLD = Decimal("0.9")  # 90%+
    CRITICAL_UTILIZATION_THRESHOLD = Decimal("0.95")  # 95%+

    def __init__(
        self,
        config: Dict[str, Any],
        max_concentration_pct: Decimal = Decimal("0.5"),  # 50%
        large_position_threshold: Decimal = Decimal("10000"),  # $10k
    ) -> None:
        """Initialize the risk assessor agent.

        Args:
            config: Configuration dictionary
            max_concentration_pct: Maximum % of portfolio in single protocol (default: 0.5 = 50%)
            large_position_threshold: USD threshold for large positions (default: $10,000)
        """
        self.config = config
        self.max_concentration_pct = max_concentration_pct
        self.large_position_threshold = large_position_threshold
        self.audit_logger = AuditLogger()

        logger.info(
            f"RiskAssessorAgent initialized: "
            f"max_concentration={max_concentration_pct * 100}%, "
            f"large_position_threshold=${large_position_threshold:,.0f}"
        )

    async def assess_protocol_risk(
        self,
        protocol: str,
        pool_id: str,
        tvl: Decimal = Decimal("0"),
        utilization: Optional[Decimal] = None,
    ) -> RiskAssessment:
        """Assess the risk of a specific protocol and pool.

        Args:
            protocol: Protocol name (e.g., 'Aave V3', 'Morpho')
            pool_id: Pool/vault identifier
            tvl: Total value locked in the pool (USD)
            utilization: Pool utilization rate (0-1, optional)

        Returns:
            Risk assessment for the protocol/pool
        """
        factors = {}
        risk_score = Decimal("0")

        # Factor 1: Protocol safety (0-40 points of risk)
        # Lower safety score = higher risk
        protocol_safety = self.PROTOCOL_SAFETY_SCORES.get(protocol, 70)  # Default: 70
        factors["protocol_safety_score"] = protocol_safety

        # Convert safety to risk: 100 - safety = base risk
        # Scale to max 40 points: (100 - safety) * 0.4
        protocol_risk = (Decimal("100") - Decimal(protocol_safety)) * Decimal("0.4")
        risk_score += protocol_risk
        factors["protocol_risk_contribution"] = float(protocol_risk)

        # Factor 2: TVL adequacy (0-30 points of risk)
        if tvl < self.MIN_SAFE_TVL:
            # Very low TVL: 30 points risk
            tvl_risk = Decimal("30")
            factors["tvl_risk_level"] = "CRITICAL"
        elif tvl < self.COMFORTABLE_TVL:
            # Moderate TVL: 10-30 points risk (linear scale)
            # $1M = 30 points, $10M = 10 points
            tvl_ratio = (tvl - self.MIN_SAFE_TVL) / (self.COMFORTABLE_TVL - self.MIN_SAFE_TVL)
            tvl_risk = Decimal("30") - (tvl_ratio * Decimal("20"))
            factors["tvl_risk_level"] = "MODERATE"
        else:
            # High TVL: minimal risk (5 points)
            tvl_risk = Decimal("5")
            factors["tvl_risk_level"] = "LOW"

        risk_score += tvl_risk
        factors["tvl_usd"] = float(tvl)
        factors["tvl_risk_contribution"] = float(tvl_risk)

        # Factor 3: Utilization risk (0-30 points of risk)
        if utilization is not None:
            if utilization >= self.CRITICAL_UTILIZATION_THRESHOLD:
                # Critical utilization: 30 points risk
                util_risk = Decimal("30")
                factors["utilization_risk_level"] = "CRITICAL"
            elif utilization >= self.HIGH_UTILIZATION_THRESHOLD:
                # High utilization: 15-30 points risk (linear scale)
                util_ratio = (utilization - self.HIGH_UTILIZATION_THRESHOLD) / (
                    self.CRITICAL_UTILIZATION_THRESHOLD - self.HIGH_UTILIZATION_THRESHOLD
                )
                util_risk = Decimal("15") + (util_ratio * Decimal("15"))
                factors["utilization_risk_level"] = "HIGH"
            else:
                # Normal utilization: 0-15 points risk
                util_risk = utilization * Decimal("15")
                factors["utilization_risk_level"] = "NORMAL"

            risk_score += util_risk
            factors["utilization_rate"] = float(utilization)
            factors["utilization_risk_contribution"] = float(util_risk)

        # Determine risk level
        risk_level = self._score_to_level(risk_score)

        # Generate recommendation
        recommendation = self._generate_protocol_recommendation(
            protocol=protocol,
            risk_level=risk_level,
            risk_score=risk_score,
            factors=factors,
        )

        # Generate detailed analysis
        detailed_analysis = self._generate_protocol_analysis(
            protocol=protocol,
            pool_id=pool_id,
            risk_level=risk_level,
            risk_score=risk_score,
            factors=factors,
        )

        # Audit log
        await self.audit_logger.log_event(
            AuditEventType.RISK_CHECK,
            AuditSeverity.INFO if risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM] else AuditSeverity.WARNING,
            {
                "assessment_type": "protocol",
                "protocol": protocol,
                "pool_id": pool_id,
                "risk_level": risk_level.value,
                "risk_score": str(risk_score),
            },
        )

        logger.info(
            f"Protocol risk: {protocol} - {risk_level.value.upper()} "
            f"(score: {risk_score:.1f}/100)"
        )

        return RiskAssessment(
            risk_level=risk_level,
            risk_score=risk_score,
            factors=factors,
            recommendation=recommendation,
            detailed_analysis=detailed_analysis,
        )

    async def assess_rebalance_risk(
        self,
        from_protocol: str,
        to_protocol: str,
        amount: Decimal,
        requires_swap: bool = False,
    ) -> RiskAssessment:
        """Assess the risk of a rebalancing operation.

        Args:
            from_protocol: Current protocol name
            to_protocol: Target protocol name
            amount: Amount to rebalance in USD
            requires_swap: Whether token swap is required

        Returns:
            Risk assessment for the rebalance operation
        """
        factors = {}
        risk_score = Decimal("0")

        # Factor 1: Target protocol safety (0-40 points of risk)
        target_safety = self.PROTOCOL_SAFETY_SCORES.get(to_protocol, 70)
        factors["target_protocol_safety"] = target_safety
        target_risk = (Decimal("100") - Decimal(target_safety)) * Decimal("0.4")
        risk_score += target_risk
        factors["target_protocol_risk_contribution"] = float(target_risk)

        # Factor 2: Position size (0-30 points of risk)
        if amount >= self.large_position_threshold:
            # Large position: higher scrutiny
            # $10k = 15 points, $100k = 30 points (logarithmic scale)
            size_ratio = min(
                (amount / self.large_position_threshold).ln() / Decimal("2.3"),  # ln(10) ≈ 2.3
                Decimal("1"),
            )
            size_risk = Decimal("15") + (size_ratio * Decimal("15"))
            factors["position_size_risk_level"] = "LARGE"
        else:
            # Normal position: minimal risk (5-15 points)
            size_ratio = amount / self.large_position_threshold
            size_risk = Decimal("5") + (size_ratio * Decimal("10"))
            factors["position_size_risk_level"] = "NORMAL"

        risk_score += size_risk
        factors["amount_usd"] = float(amount)
        factors["position_size_risk_contribution"] = float(size_risk)

        # Factor 3: Swap requirement (0-20 points of risk)
        if requires_swap:
            # Swaps add slippage and smart contract risk
            swap_risk = Decimal("20")
            factors["swap_risk_level"] = "ELEVATED"
        else:
            # Same-token rebalance: minimal swap risk
            swap_risk = Decimal("5")
            factors["swap_risk_level"] = "MINIMAL"

        risk_score += swap_risk
        factors["requires_swap"] = requires_swap
        factors["swap_risk_contribution"] = float(swap_risk)

        # Factor 4: Protocol transition risk (0-10 points)
        # Moving from safer to riskier protocol adds risk
        source_safety = self.PROTOCOL_SAFETY_SCORES.get(from_protocol, 70)
        factors["source_protocol_safety"] = source_safety

        if target_safety < source_safety:
            # Downgrade in safety
            safety_delta = source_safety - target_safety
            transition_risk = Decimal(safety_delta) / Decimal("10")  # Max 10 points
            factors["transition_risk_level"] = "DOWNGRADE"
        else:
            # Upgrade or neutral
            transition_risk = Decimal("0")
            factors["transition_risk_level"] = "UPGRADE" if target_safety > source_safety else "NEUTRAL"

        risk_score += transition_risk
        factors["transition_risk_contribution"] = float(transition_risk)

        # Determine risk level
        risk_level = self._score_to_level(risk_score)

        # Generate recommendation
        recommendation = self._generate_rebalance_recommendation(
            from_protocol=from_protocol,
            to_protocol=to_protocol,
            amount=amount,
            risk_level=risk_level,
            risk_score=risk_score,
            factors=factors,
        )

        # Generate detailed analysis
        detailed_analysis = self._generate_rebalance_analysis(
            from_protocol=from_protocol,
            to_protocol=to_protocol,
            amount=amount,
            risk_level=risk_level,
            risk_score=risk_score,
            factors=factors,
        )

        # Audit log
        await self.audit_logger.log_event(
            AuditEventType.RISK_CHECK,
            AuditSeverity.INFO if risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM] else AuditSeverity.WARNING,
            {
                "assessment_type": "rebalance",
                "from_protocol": from_protocol,
                "to_protocol": to_protocol,
                "amount_usd": str(amount),
                "requires_swap": requires_swap,
                "risk_level": risk_level.value,
                "risk_score": str(risk_score),
            },
        )

        logger.info(
            f"Rebalance risk: {from_protocol} → {to_protocol} (${amount:,.0f}) - "
            f"{risk_level.value.upper()} (score: {risk_score:.1f}/100)"
        )

        return RiskAssessment(
            risk_level=risk_level,
            risk_score=risk_score,
            factors=factors,
            recommendation=recommendation,
            detailed_analysis=detailed_analysis,
        )

    async def assess_position_concentration(
        self,
        positions: Dict[str, Decimal],
        total_value: Optional[Decimal] = None,
    ) -> RiskAssessment:
        """Assess portfolio concentration risk.

        Args:
            positions: Dict of protocol->amount positions (USD)
            total_value: Total portfolio value (computed if not provided)

        Returns:
            Assessment of concentration risk
        """
        if not positions:
            return RiskAssessment(
                risk_level=RiskLevel.LOW,
                risk_score=Decimal("0"),
                factors={"reason": "no_positions"},
                recommendation="No positions to assess",
                detailed_analysis="Portfolio is empty",
            )

        factors = {}
        risk_score = Decimal("0")

        # Calculate total if not provided
        if total_value is None:
            total_value = sum(positions.values())

        factors["total_value_usd"] = float(total_value)
        factors["num_positions"] = len(positions)

        # Calculate concentration percentages
        concentrations = {
            protocol: (amount / total_value) if total_value > 0 else Decimal("0")
            for protocol, amount in positions.items()
        }

        # Find max concentration
        max_protocol = max(concentrations, key=concentrations.get)
        max_concentration = concentrations[max_protocol]

        factors["max_concentration_protocol"] = max_protocol
        factors["max_concentration_pct"] = float(max_concentration)
        factors["concentrations"] = {k: float(v) for k, v in concentrations.items()}

        # Factor 1: Single protocol concentration (0-50 points of risk)
        if max_concentration > self.max_concentration_pct:
            # Over-concentrated: 25-50 points based on severity
            excess = max_concentration - self.max_concentration_pct
            concentration_risk = Decimal("25") + (excess * Decimal("50"))  # Up to 50 points
            factors["concentration_risk_level"] = "EXCESSIVE"
        elif max_concentration > Decimal("0.3"):  # 30%
            # Moderately concentrated: 10-25 points
            ratio = (max_concentration - Decimal("0.3")) / (self.max_concentration_pct - Decimal("0.3"))
            concentration_risk = Decimal("10") + (ratio * Decimal("15"))
            factors["concentration_risk_level"] = "MODERATE"
        else:
            # Well diversified: 0-10 points
            concentration_risk = max_concentration * Decimal("33")  # 30% = 10 points
            factors["concentration_risk_level"] = "LOW"

        risk_score += concentration_risk
        factors["concentration_risk_contribution"] = float(concentration_risk)

        # Factor 2: Number of protocols (0-20 points of risk)
        # Fewer protocols = higher concentration risk
        if len(positions) == 1:
            diversification_risk = Decimal("20")
            factors["diversification_level"] = "SINGLE_PROTOCOL"
        elif len(positions) == 2:
            diversification_risk = Decimal("10")
            factors["diversification_level"] = "TWO_PROTOCOLS"
        elif len(positions) == 3:
            diversification_risk = Decimal("5")
            factors["diversification_level"] = "THREE_PROTOCOLS"
        else:
            diversification_risk = Decimal("0")
            factors["diversification_level"] = "WELL_DIVERSIFIED"

        risk_score += diversification_risk
        factors["diversification_risk_contribution"] = float(diversification_risk)

        # Factor 3: Protocol safety weighted average (0-30 points of risk)
        # Lower average safety = higher risk
        weighted_safety = Decimal("0")
        for protocol, concentration in concentrations.items():
            protocol_safety = self.PROTOCOL_SAFETY_SCORES.get(protocol, 70)
            weighted_safety += Decimal(protocol_safety) * concentration

        factors["weighted_safety_score"] = float(weighted_safety)

        # Convert to risk: (100 - weighted_safety) * 0.3
        safety_risk = (Decimal("100") - weighted_safety) * Decimal("0.3")
        risk_score += safety_risk
        factors["safety_risk_contribution"] = float(safety_risk)

        # Determine risk level
        risk_level = self._score_to_level(risk_score)

        # Generate recommendation
        recommendation = self._generate_concentration_recommendation(
            max_protocol=max_protocol,
            max_concentration=max_concentration,
            num_protocols=len(positions),
            risk_level=risk_level,
            risk_score=risk_score,
            factors=factors,
        )

        # Generate detailed analysis
        detailed_analysis = self._generate_concentration_analysis(
            positions=positions,
            concentrations=concentrations,
            risk_level=risk_level,
            risk_score=risk_score,
            factors=factors,
        )

        # Audit log
        await self.audit_logger.log_event(
            AuditEventType.RISK_CHECK,
            AuditSeverity.INFO if risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM] else AuditSeverity.WARNING,
            {
                "assessment_type": "concentration",
                "num_positions": len(positions),
                "max_concentration_protocol": max_protocol,
                "max_concentration_pct": str(max_concentration),
                "risk_level": risk_level.value,
                "risk_score": str(risk_score),
            },
        )

        logger.info(
            f"Concentration risk: {len(positions)} protocols, "
            f"max {max_concentration * 100:.1f}% in {max_protocol} - "
            f"{risk_level.value.upper()} (score: {risk_score:.1f}/100)"
        )

        return RiskAssessment(
            risk_level=risk_level,
            risk_score=risk_score,
            factors=factors,
            recommendation=recommendation,
            detailed_analysis=detailed_analysis,
        )

    def should_proceed(
        self,
        assessment: RiskAssessment,
        allow_high_risk: bool = False,
    ) -> bool:
        """Determine if an action should proceed based on risk assessment.

        Args:
            assessment: Risk assessment to evaluate
            allow_high_risk: If True, allow HIGH risk (requires elevated approval)

        Returns:
            True if action should proceed, False otherwise
        """
        # CRITICAL risk: never proceed
        if assessment.risk_level == RiskLevel.CRITICAL:
            logger.warning(
                f"❌ BLOCKING: CRITICAL risk level (score: {assessment.risk_score:.1f}/100)"
            )
            return False

        # HIGH risk: only proceed if explicitly allowed
        if assessment.risk_level == RiskLevel.HIGH:
            if allow_high_risk:
                logger.warning(
                    f"⚠️ PROCEEDING: HIGH risk with elevated approval "
                    f"(score: {assessment.risk_score:.1f}/100)"
                )
                return True
            else:
                logger.warning(
                    f"❌ BLOCKING: HIGH risk requires elevated approval "
                    f"(score: {assessment.risk_score:.1f}/100)"
                )
                return False

        # MEDIUM/LOW risk: proceed
        logger.info(
            f"✅ PROCEEDING: {assessment.risk_level.value.upper()} risk "
            f"(score: {assessment.risk_score:.1f}/100)"
        )
        return True

    def _score_to_level(self, score: Decimal) -> RiskLevel:
        """Convert numerical risk score to risk level.

        Args:
            score: Risk score 0-100

        Returns:
            RiskLevel classification
        """
        if score >= 76:
            return RiskLevel.CRITICAL
        elif score >= 51:
            return RiskLevel.HIGH
        elif score >= 26:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _generate_protocol_recommendation(
        self,
        protocol: str,
        risk_level: RiskLevel,
        risk_score: Decimal,
        factors: Dict[str, Any],
    ) -> str:
        """Generate recommendation for protocol risk assessment."""
        if risk_level == RiskLevel.CRITICAL:
            return f"DO NOT USE {protocol}: Critical risk detected (score: {risk_score:.1f}/100)"
        elif risk_level == RiskLevel.HIGH:
            return f"CAUTION with {protocol}: Elevated risk requires careful monitoring (score: {risk_score:.1f}/100)"
        elif risk_level == RiskLevel.MEDIUM:
            return f"NORMAL RISK for {protocol}: Proceed with standard monitoring (score: {risk_score:.1f}/100)"
        else:
            return f"LOW RISK for {protocol}: Safe to proceed (score: {risk_score:.1f}/100)"

    def _generate_rebalance_recommendation(
        self,
        from_protocol: str,
        to_protocol: str,
        amount: Decimal,
        risk_level: RiskLevel,
        risk_score: Decimal,
        factors: Dict[str, Any],
    ) -> str:
        """Generate recommendation for rebalance risk assessment."""
        if risk_level == RiskLevel.CRITICAL:
            return (
                f"DO NOT REBALANCE {from_protocol} → {to_protocol} (${amount:,.0f}): "
                f"Critical risk detected (score: {risk_score:.1f}/100)"
            )
        elif risk_level == RiskLevel.HIGH:
            return (
                f"ELEVATED APPROVAL REQUIRED for {from_protocol} → {to_protocol} (${amount:,.0f}): "
                f"High risk operation (score: {risk_score:.1f}/100)"
            )
        elif risk_level == RiskLevel.MEDIUM:
            return (
                f"PROCEED WITH MONITORING {from_protocol} → {to_protocol} (${amount:,.0f}): "
                f"Normal risk (score: {risk_score:.1f}/100)"
            )
        else:
            return (
                f"SAFE TO PROCEED {from_protocol} → {to_protocol} (${amount:,.0f}): "
                f"Low risk operation (score: {risk_score:.1f}/100)"
            )

    def _generate_concentration_recommendation(
        self,
        max_protocol: str,
        max_concentration: Decimal,
        num_protocols: int,
        risk_level: RiskLevel,
        risk_score: Decimal,
        factors: Dict[str, Any],
    ) -> str:
        """Generate recommendation for concentration risk assessment."""
        if risk_level == RiskLevel.CRITICAL:
            return (
                f"CRITICAL CONCENTRATION: {max_concentration * 100:.1f}% in {max_protocol}. "
                f"MUST diversify immediately (score: {risk_score:.1f}/100)"
            )
        elif risk_level == RiskLevel.HIGH:
            return (
                f"HIGH CONCENTRATION: {max_concentration * 100:.1f}% in {max_protocol}. "
                f"Recommend diversifying across more protocols (score: {risk_score:.1f}/100)"
            )
        elif risk_level == RiskLevel.MEDIUM:
            return (
                f"MODERATE CONCENTRATION: {num_protocols} protocols, "
                f"max {max_concentration * 100:.1f}% in {max_protocol}. "
                f"Consider gradual diversification (score: {risk_score:.1f}/100)"
            )
        else:
            return (
                f"WELL DIVERSIFIED: {num_protocols} protocols, "
                f"max {max_concentration * 100:.1f}% in {max_protocol}. "
                f"Healthy distribution (score: {risk_score:.1f}/100)"
            )

    def _generate_protocol_analysis(
        self,
        protocol: str,
        pool_id: str,
        risk_level: RiskLevel,
        risk_score: Decimal,
        factors: Dict[str, Any],
    ) -> str:
        """Generate detailed protocol risk analysis."""
        lines = [
            "=" * 60,
            "PROTOCOL RISK ANALYSIS",
            "=" * 60,
            "",
            f"Protocol: {protocol}",
            f"Pool: {pool_id}",
            f"Risk Level: {risk_level.value.upper()}",
            f"Risk Score: {risk_score:.1f}/100",
            "",
            "RISK FACTORS:",
            f"  Protocol Safety: {factors.get('protocol_safety_score', 'N/A')}/100 "
            f"(risk: {factors.get('protocol_risk_contribution', 0):.1f} points)",
        ]

        if "tvl_usd" in factors:
            lines.append(
                f"  TVL: ${factors['tvl_usd']:,.0f} "
                f"({factors.get('tvl_risk_level', 'N/A')}, "
                f"risk: {factors.get('tvl_risk_contribution', 0):.1f} points)"
            )

        if "utilization_rate" in factors:
            lines.append(
                f"  Utilization: {factors['utilization_rate'] * 100:.1f}% "
                f"({factors.get('utilization_risk_level', 'N/A')}, "
                f"risk: {factors.get('utilization_risk_contribution', 0):.1f} points)"
            )

        lines.append("=" * 60)
        return "\n".join(lines)

    def _generate_rebalance_analysis(
        self,
        from_protocol: str,
        to_protocol: str,
        amount: Decimal,
        risk_level: RiskLevel,
        risk_score: Decimal,
        factors: Dict[str, Any],
    ) -> str:
        """Generate detailed rebalance risk analysis."""
        lines = [
            "=" * 60,
            "REBALANCE RISK ANALYSIS",
            "=" * 60,
            "",
            f"From: {from_protocol} (safety: {factors.get('source_protocol_safety', 'N/A')}/100)",
            f"To: {to_protocol} (safety: {factors.get('target_protocol_safety', 'N/A')}/100)",
            f"Amount: ${amount:,.2f}",
            f"Requires Swap: {factors.get('requires_swap', False)}",
            f"Risk Level: {risk_level.value.upper()}",
            f"Risk Score: {risk_score:.1f}/100",
            "",
            "RISK FACTORS:",
            f"  Target Protocol: {factors.get('target_protocol_risk_contribution', 0):.1f} points",
            f"  Position Size: ${factors.get('amount_usd', 0):,.0f} "
            f"({factors.get('position_size_risk_level', 'N/A')}, "
            f"{factors.get('position_size_risk_contribution', 0):.1f} points)",
            f"  Swap Risk: {factors.get('swap_risk_level', 'N/A')} "
            f"({factors.get('swap_risk_contribution', 0):.1f} points)",
            f"  Transition: {factors.get('transition_risk_level', 'N/A')} "
            f"({factors.get('transition_risk_contribution', 0):.1f} points)",
            "=" * 60,
        ]
        return "\n".join(lines)

    def _generate_concentration_analysis(
        self,
        positions: Dict[str, Decimal],
        concentrations: Dict[str, Decimal],
        risk_level: RiskLevel,
        risk_score: Decimal,
        factors: Dict[str, Any],
    ) -> str:
        """Generate detailed concentration risk analysis."""
        lines = [
            "=" * 60,
            "PORTFOLIO CONCENTRATION ANALYSIS",
            "=" * 60,
            "",
            f"Total Value: ${factors.get('total_value_usd', 0):,.2f}",
            f"Number of Protocols: {factors.get('num_positions', 0)}",
            f"Risk Level: {risk_level.value.upper()}",
            f"Risk Score: {risk_score:.1f}/100",
            "",
            "POSITIONS:",
        ]

        # Sort by concentration (highest first)
        sorted_protocols = sorted(concentrations.items(), key=lambda x: x[1], reverse=True)
        for protocol, concentration in sorted_protocols:
            amount = positions[protocol]
            safety = self.PROTOCOL_SAFETY_SCORES.get(protocol, 70)
            lines.append(
                f"  {protocol}: {concentration * 100:.1f}% (${amount:,.0f}, safety: {safety}/100)"
            )

        lines.extend([
            "",
            "RISK FACTORS:",
            f"  Concentration: {factors.get('concentration_risk_level', 'N/A')} "
            f"(risk: {factors.get('concentration_risk_contribution', 0):.1f} points)",
            f"  Diversification: {factors.get('diversification_level', 'N/A')} "
            f"(risk: {factors.get('diversification_risk_contribution', 0):.1f} points)",
            f"  Weighted Safety: {factors.get('weighted_safety_score', 0):.1f}/100 "
            f"(risk: {factors.get('safety_risk_contribution', 0):.1f} points)",
            "=" * 60,
        ])
        return "\n".join(lines)
