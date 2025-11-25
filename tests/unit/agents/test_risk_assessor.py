"""Tests for risk_assessor.py - Risk assessment agent.

Sprint 3: Comprehensive tests for RiskAssessorAgent covering:
- Protocol risk assessment
- Rebalance risk assessment
- Position concentration risk
- Risk level classification
- Decision gates (should_proceed)
"""

import pytest
from decimal import Decimal
from src.agents.risk_assessor import (
    RiskAssessorAgent,
    RiskLevel,
    RiskAssessment,
)


@pytest.fixture
def risk_assessor():
    """Create RiskAssessorAgent for testing."""
    config = {"dry_run_mode": True}
    return RiskAssessorAgent(config)


@pytest.fixture
def custom_risk_assessor():
    """Create RiskAssessorAgent with custom thresholds."""
    config = {"dry_run_mode": True}
    return RiskAssessorAgent(
        config=config,
        max_concentration_pct=Decimal("0.4"),  # 40% max
        large_position_threshold=Decimal("5000"),  # $5k
    )


# =============================================================================
# Protocol Risk Assessment Tests
# =============================================================================


@pytest.mark.asyncio
async def test_assess_protocol_aave_low_risk(risk_assessor):
    """Test Aave V3 with high TVL results in LOW risk."""
    assessment = await risk_assessor.assess_protocol_risk(
        protocol="Aave V3",
        pool_id="usdc-pool",
        tvl=Decimal("125_000_000"),  # $125M TVL
        utilization=Decimal("0.7"),  # 70% utilization
    )

    assert assessment.risk_level == RiskLevel.LOW
    assert assessment.risk_score < 26
    assert assessment.factors["protocol_safety_score"] == 95
    assert assessment.factors["tvl_risk_level"] == "LOW"
    assert assessment.factors["utilization_risk_level"] == "NORMAL"
    assert "LOW RISK" in assessment.recommendation


@pytest.mark.asyncio
async def test_assess_protocol_morpho_medium_risk(risk_assessor):
    """Test Morpho with moderate TVL and high utilization."""
    assessment = await risk_assessor.assess_protocol_risk(
        protocol="Morpho",
        pool_id="usdc-weth",
        tvl=Decimal("5_000_000"),  # $5M TVL (moderate)
        utilization=Decimal("0.92"),  # 92% utilization (high)
    )

    # Should be MEDIUM or HIGH due to high utilization
    assert assessment.risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
    assert assessment.factors["protocol_safety_score"] == 90
    assert assessment.factors["tvl_risk_level"] == "MODERATE"
    assert assessment.factors["utilization_risk_level"] == "HIGH"


@pytest.mark.asyncio
async def test_assess_protocol_low_tvl_critical_risk(risk_assessor):
    """Test unknown protocol with very low TVL results in HIGH/CRITICAL risk."""
    assessment = await risk_assessor.assess_protocol_risk(
        protocol="UnknownDEX",  # Not in safety scores (default: 70)
        pool_id="scam-pool",
        tvl=Decimal("50_000"),  # $50k TVL (very low)
        utilization=Decimal("0.98"),  # 98% utilization (critical)
    )

    # Should be HIGH or CRITICAL
    assert assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
    assert assessment.factors["protocol_safety_score"] == 70  # Default
    assert assessment.factors["tvl_risk_level"] == "CRITICAL"
    assert assessment.factors["utilization_risk_level"] == "CRITICAL"


@pytest.mark.asyncio
async def test_assess_protocol_without_utilization(risk_assessor):
    """Test protocol risk assessment without utilization data."""
    assessment = await risk_assessor.assess_protocol_risk(
        protocol="Moonwell",
        pool_id="usdc-pool",
        tvl=Decimal("32_000_000"),  # $32M TVL
        utilization=None,  # No utilization data
    )

    assert "utilization_rate" not in assessment.factors
    assert "utilization_risk_contribution" not in assessment.factors
    # Risk should only come from protocol safety and TVL
    assert assessment.risk_score > 0


@pytest.mark.asyncio
async def test_assess_protocol_alias_names(risk_assessor):
    """Test that protocol aliases work correctly."""
    # Test Aave alias
    aave_assessment = await risk_assessor.assess_protocol_risk(
        protocol="Aave",  # Alias for "Aave V3"
        pool_id="test",
        tvl=Decimal("10_000_000"),
    )
    assert aave_assessment.factors["protocol_safety_score"] == 95

    # Test Morpho Blue alias
    morpho_assessment = await risk_assessor.assess_protocol_risk(
        protocol="Morpho Blue",  # Alias for "Morpho"
        pool_id="test",
        tvl=Decimal("10_000_000"),
    )
    assert morpho_assessment.factors["protocol_safety_score"] == 90


# =============================================================================
# Rebalance Risk Assessment Tests
# =============================================================================


@pytest.mark.asyncio
async def test_assess_rebalance_safe_upgrade(risk_assessor):
    """Test rebalancing to safer protocol (Moonwell → Aave V3)."""
    assessment = await risk_assessor.assess_rebalance_risk(
        from_protocol="Moonwell",  # Safety: 85
        to_protocol="Aave V3",  # Safety: 95
        amount=Decimal("5000"),  # $5k (normal size)
        requires_swap=False,  # Same token
    )

    assert assessment.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
    assert assessment.factors["transition_risk_level"] == "UPGRADE"
    assert assessment.factors["transition_risk_contribution"] == 0.0
    assert assessment.factors["swap_risk_level"] == "MINIMAL"


@pytest.mark.asyncio
async def test_assess_rebalance_with_swap(risk_assessor):
    """Test rebalancing requiring token swap adds risk."""
    no_swap = await risk_assessor.assess_rebalance_risk(
        from_protocol="Aave V3",
        to_protocol="Morpho",
        amount=Decimal("5000"),
        requires_swap=False,
    )

    with_swap = await risk_assessor.assess_rebalance_risk(
        from_protocol="Aave V3",
        to_protocol="Morpho",
        amount=Decimal("5000"),
        requires_swap=True,
    )

    # Swap should add ~15 points of risk (20 vs 5)
    assert with_swap.risk_score > no_swap.risk_score
    assert with_swap.factors["swap_risk_level"] == "ELEVATED"
    assert no_swap.factors["swap_risk_level"] == "MINIMAL"


@pytest.mark.asyncio
async def test_assess_rebalance_large_position(custom_risk_assessor):
    """Test large position increases risk score."""
    # custom_risk_assessor has large_position_threshold = $5k

    small = await custom_risk_assessor.assess_rebalance_risk(
        from_protocol="Aave V3",
        to_protocol="Morpho",
        amount=Decimal("2000"),  # $2k (below threshold)
        requires_swap=False,
    )

    large = await custom_risk_assessor.assess_rebalance_risk(
        from_protocol="Aave V3",
        to_protocol="Morpho",
        amount=Decimal("20000"),  # $20k (above threshold)
        requires_swap=False,
    )

    assert large.risk_score > small.risk_score
    assert small.factors["position_size_risk_level"] == "NORMAL"
    assert large.factors["position_size_risk_level"] == "LARGE"


@pytest.mark.asyncio
async def test_assess_rebalance_safety_downgrade(risk_assessor):
    """Test moving to less safe protocol increases risk."""
    assessment = await risk_assessor.assess_rebalance_risk(
        from_protocol="Aave V3",  # Safety: 95
        to_protocol="Moonwell",  # Safety: 85
        amount=Decimal("5000"),
        requires_swap=False,
    )

    # Downgrade should add risk
    assert assessment.factors["transition_risk_level"] == "DOWNGRADE"
    assert assessment.factors["transition_risk_contribution"] > 0


@pytest.mark.asyncio
async def test_assess_rebalance_worst_case(risk_assessor):
    """Test worst-case rebalance: large, swap, downgrade."""
    assessment = await risk_assessor.assess_rebalance_risk(
        from_protocol="Aave V3",  # Safety: 95
        to_protocol="UnknownProtocol",  # Safety: 70 (default)
        amount=Decimal("100_000"),  # $100k (very large)
        requires_swap=True,
    )

    # Should be HIGH or CRITICAL risk
    assert assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
    assert assessment.factors["position_size_risk_level"] == "LARGE"
    assert assessment.factors["swap_risk_level"] == "ELEVATED"
    assert assessment.factors["transition_risk_level"] == "DOWNGRADE"


# =============================================================================
# Concentration Risk Assessment Tests
# =============================================================================


@pytest.mark.asyncio
async def test_assess_concentration_well_diversified(risk_assessor):
    """Test well-diversified portfolio has LOW risk."""
    positions = {
        "Aave V3": Decimal("4000"),
        "Morpho": Decimal("4000"),
        "Moonwell": Decimal("4000"),
        "Aerodrome": Decimal("4000"),
    }  # Total: $16k, max 25% in each (well diversified)

    assessment = await risk_assessor.assess_position_concentration(positions)

    assert assessment.risk_level == RiskLevel.LOW
    assert assessment.factors["num_positions"] == 4
    assert assessment.factors["diversification_level"] == "WELL_DIVERSIFIED"
    assert assessment.factors["concentration_risk_level"] == "LOW"


@pytest.mark.asyncio
async def test_assess_concentration_single_protocol(risk_assessor):
    """Test single protocol has MEDIUM risk."""
    positions = {"Aave V3": Decimal("10000")}  # 100% in one protocol

    assessment = await risk_assessor.assess_position_concentration(positions)

    # Single protocol but high safety (Aave) should be MEDIUM, not CRITICAL
    assert assessment.risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
    assert assessment.factors["num_positions"] == 1
    assert assessment.factors["diversification_level"] == "SINGLE_PROTOCOL"
    assert assessment.factors["max_concentration_pct"] == 1.0


@pytest.mark.asyncio
async def test_assess_concentration_excessive(custom_risk_assessor):
    """Test over-concentration (>50%) increases risk."""
    # custom_risk_assessor has max_concentration_pct = 40%
    positions = {
        "Morpho": Decimal("7000"),  # 70% concentration
        "Aave V3": Decimal("3000"),  # 30% concentration
    }  # Total: $10k

    assessment = await custom_risk_assessor.assess_position_concentration(positions)

    # 70% > 40% threshold should trigger excessive concentration
    assert assessment.factors["concentration_risk_level"] == "EXCESSIVE"
    assert assessment.factors["max_concentration_pct"] == 0.7


@pytest.mark.asyncio
async def test_assess_concentration_empty_portfolio(risk_assessor):
    """Test empty portfolio returns LOW risk."""
    positions = {}

    assessment = await risk_assessor.assess_position_concentration(positions)

    assert assessment.risk_level == RiskLevel.LOW
    assert assessment.risk_score == 0
    assert assessment.factors["reason"] == "no_positions"


@pytest.mark.asyncio
async def test_assess_concentration_weighted_safety(risk_assessor):
    """Test weighted safety calculation."""
    # High concentration in low-safety protocol should increase risk
    positions = {
        "UnknownDEX": Decimal("8000"),  # 80% in unknown (safety: 70)
        "Aave V3": Decimal("2000"),  # 20% in Aave (safety: 95)
    }  # Weighted safety: 0.8*70 + 0.2*95 = 56 + 19 = 75

    assessment = await risk_assessor.assess_position_concentration(positions)

    # Should have higher risk due to low weighted safety
    weighted_safety = assessment.factors["weighted_safety_score"]
    assert 74 <= weighted_safety <= 76  # ~75


@pytest.mark.asyncio
async def test_assess_concentration_with_total_value(risk_assessor):
    """Test providing explicit total_value parameter."""
    positions = {
        "Aave V3": Decimal("5000"),
        "Morpho": Decimal("5000"),
    }

    assessment = await risk_assessor.assess_position_concentration(
        positions=positions,
        total_value=Decimal("10000"),  # Explicit total
    )

    assert assessment.factors["total_value_usd"] == 10000.0
    assert assessment.factors["max_concentration_pct"] == 0.5


# =============================================================================
# Risk Level Classification Tests
# =============================================================================


def test_score_to_level_boundaries(risk_assessor):
    """Test risk score to level conversion boundaries."""
    assert risk_assessor._score_to_level(Decimal("0")) == RiskLevel.LOW
    assert risk_assessor._score_to_level(Decimal("25")) == RiskLevel.LOW
    assert risk_assessor._score_to_level(Decimal("26")) == RiskLevel.MEDIUM
    assert risk_assessor._score_to_level(Decimal("50")) == RiskLevel.MEDIUM
    assert risk_assessor._score_to_level(Decimal("51")) == RiskLevel.HIGH
    assert risk_assessor._score_to_level(Decimal("75")) == RiskLevel.HIGH
    assert risk_assessor._score_to_level(Decimal("76")) == RiskLevel.CRITICAL
    assert risk_assessor._score_to_level(Decimal("100")) == RiskLevel.CRITICAL


# =============================================================================
# Decision Gate Tests (should_proceed)
# =============================================================================


def test_should_proceed_low_risk(risk_assessor):
    """Test LOW risk always proceeds."""
    assessment = RiskAssessment(
        risk_level=RiskLevel.LOW,
        risk_score=Decimal("10"),
        factors={},
        recommendation="Safe",
    )

    assert risk_assessor.should_proceed(assessment) is True
    assert risk_assessor.should_proceed(assessment, allow_high_risk=False) is True


def test_should_proceed_medium_risk(risk_assessor):
    """Test MEDIUM risk proceeds."""
    assessment = RiskAssessment(
        risk_level=RiskLevel.MEDIUM,
        risk_score=Decimal("40"),
        factors={},
        recommendation="Normal risk",
    )

    assert risk_assessor.should_proceed(assessment) is True
    assert risk_assessor.should_proceed(assessment, allow_high_risk=False) is True


def test_should_proceed_high_risk_blocked_by_default(risk_assessor):
    """Test HIGH risk blocked unless allow_high_risk=True."""
    assessment = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        risk_score=Decimal("60"),
        factors={},
        recommendation="Elevated risk",
    )

    # Blocked by default
    assert risk_assessor.should_proceed(assessment, allow_high_risk=False) is False

    # Allowed with elevated approval
    assert risk_assessor.should_proceed(assessment, allow_high_risk=True) is True


def test_should_proceed_critical_risk_always_blocked(risk_assessor):
    """Test CRITICAL risk always blocked."""
    assessment = RiskAssessment(
        risk_level=RiskLevel.CRITICAL,
        risk_score=Decimal("90"),
        factors={},
        recommendation="Critical risk",
    )

    # Always blocked
    assert risk_assessor.should_proceed(assessment, allow_high_risk=False) is False
    assert risk_assessor.should_proceed(assessment, allow_high_risk=True) is False


# =============================================================================
# Detailed Analysis Generation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_protocol_detailed_analysis_format(risk_assessor):
    """Test protocol risk analysis generates proper format."""
    assessment = await risk_assessor.assess_protocol_risk(
        protocol="Aave V3",
        pool_id="usdc-pool",
        tvl=Decimal("125_000_000"),
        utilization=Decimal("0.8"),
    )

    analysis = assessment.detailed_analysis
    assert "PROTOCOL RISK ANALYSIS" in analysis
    assert "Aave V3" in analysis
    assert "usdc-pool" in analysis
    assert "RISK FACTORS:" in analysis
    assert "Protocol Safety:" in analysis
    assert "TVL:" in analysis
    assert "Utilization:" in analysis


@pytest.mark.asyncio
async def test_rebalance_detailed_analysis_format(risk_assessor):
    """Test rebalance risk analysis generates proper format."""
    assessment = await risk_assessor.assess_rebalance_risk(
        from_protocol="Moonwell",
        to_protocol="Aave V3",
        amount=Decimal("5000"),
        requires_swap=True,
    )

    analysis = assessment.detailed_analysis
    assert "REBALANCE RISK ANALYSIS" in analysis
    assert "Moonwell" in analysis
    assert "Aave V3" in analysis
    assert "$5,000" in analysis
    assert "True" in analysis  # requires_swap
    assert "RISK FACTORS:" in analysis


@pytest.mark.asyncio
async def test_concentration_detailed_analysis_format(risk_assessor):
    """Test concentration analysis generates proper format."""
    positions = {
        "Aave V3": Decimal("6000"),
        "Morpho": Decimal("4000"),
    }

    assessment = await risk_assessor.assess_position_concentration(positions)

    analysis = assessment.detailed_analysis
    assert "PORTFOLIO CONCENTRATION ANALYSIS" in analysis
    assert "Total Value:" in analysis
    assert "Number of Protocols: 2" in analysis
    assert "POSITIONS:" in analysis
    assert "Aave V3" in analysis
    assert "Morpho" in analysis
    assert "RISK FACTORS:" in analysis


# =============================================================================
# Recommendation Generation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_recommendations_match_risk_levels(risk_assessor):
    """Test recommendations align with risk levels."""
    # LOW risk recommendation
    low_assessment = await risk_assessor.assess_protocol_risk(
        protocol="Aave V3",
        pool_id="test",
        tvl=Decimal("100_000_000"),
    )
    assert "LOW RISK" in low_assessment.recommendation or "Safe" in low_assessment.recommendation

    # HIGH risk recommendation
    high_assessment = await risk_assessor.assess_protocol_risk(
        protocol="UnknownDEX",
        pool_id="test",
        tvl=Decimal("100_000"),  # Very low TVL
        utilization=Decimal("0.98"),  # Critical utilization
    )
    assert high_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
    assert any(
        word in high_assessment.recommendation
        for word in ["CAUTION", "DO NOT", "CRITICAL", "HIGH"]
    )


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


@pytest.mark.asyncio
async def test_zero_amount_rebalance(risk_assessor):
    """Test rebalancing with zero amount."""
    assessment = await risk_assessor.assess_rebalance_risk(
        from_protocol="Aave V3",
        to_protocol="Morpho",
        amount=Decimal("0"),
        requires_swap=False,
    )

    # Should still assess risk (very low for amount)
    assert assessment.risk_score >= 0
    assert assessment.factors["amount_usd"] == 0.0


@pytest.mark.asyncio
async def test_concentration_all_same_protocol(risk_assessor):
    """Test concentration with multiple positions in same protocol."""
    positions = {
        "Aave V3": Decimal("10000"),
    }

    assessment = await risk_assessor.assess_position_concentration(positions)

    assert assessment.factors["max_concentration_pct"] == 1.0
    assert assessment.factors["num_positions"] == 1
