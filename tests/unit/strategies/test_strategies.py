"""Tests for yield strategies (simple_yield.py and risk_adjusted.py).

Sprint 3: Comprehensive tests for both SimpleYieldStrategy and RiskAdjustedStrategy
covering:
- Opportunity analysis
- Optimal allocation
- Rebalance decisions
- Profitability integration
- Risk assessment integration
- Concentration limits
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from src.strategies.simple_yield import SimpleYieldStrategy
from src.strategies.risk_adjusted import RiskAdjustedStrategy
from src.strategies.profitability_calculator import (
    ProfitabilityCalculator,
    MoveProfitability,
    RebalancingCosts,
)
from src.agents.risk_assessor import RiskAssessorAgent, RiskLevel, RiskAssessment


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_profitability_calc():
    """Create mock ProfitabilityCalculator for testing."""
    calc = AsyncMock(spec=ProfitabilityCalculator)

    # Default: return profitable result
    calc.calculate_profitability.return_value = MoveProfitability(
        apy_improvement=Decimal("4.0"),
        position_size=Decimal("1000"),
        annual_gain_usd=Decimal("40"),
        costs=RebalancingCosts(
            gas_withdraw=Decimal("1"),
            gas_approve=Decimal("0"),
            gas_swap=Decimal("0"),
            gas_deposit=Decimal("1"),
            slippage_cost=Decimal("0"),
            protocol_fees=Decimal("0"),
            total_cost=Decimal("2"),
        ),
        net_gain_first_year=Decimal("38"),
        break_even_days=18,
        roi_on_costs=Decimal("1900"),
        is_profitable=True,
        rejection_reasons=[],
        detailed_breakdown="Mock profitable",
    )

    return calc


@pytest.fixture
def mock_risk_assessor():
    """Create mock RiskAssessorAgent for testing."""
    assessor = AsyncMock(spec=RiskAssessorAgent)

    # Default: LOW risk
    assessor.assess_rebalance_risk.return_value = RiskAssessment(
        risk_level=RiskLevel.LOW,
        risk_score=Decimal("15"),
        factors={"target_protocol_safety": 95},
        recommendation="Safe to proceed",
    )

    assessor.assess_position_concentration.return_value = RiskAssessment(
        risk_level=RiskLevel.LOW,
        risk_score=Decimal("10"),
        factors={"num_positions": 3},
        recommendation="Well diversified",
    )

    assessor.should_proceed.return_value = True

    return assessor


@pytest.fixture
def simple_strategy(mock_profitability_calc):
    """Create SimpleYieldStrategy for testing."""
    config = {"min_apy_improvement": Decimal("0.5"), "min_rebalance_amount": Decimal("100")}
    return SimpleYieldStrategy(config=config, profitability_calc=mock_profitability_calc)


@pytest.fixture
def risk_adjusted_strategy(mock_profitability_calc, mock_risk_assessor):
    """Create RiskAdjustedStrategy for testing."""
    config = {
        "min_apy_improvement": Decimal("0.5"),
        "min_rebalance_amount": Decimal("100"),
        "risk_tolerance": "medium",
        "allow_high_risk": False,
        "max_concentration_pct": 0.4,
        "diversification_target": 3,
    }
    return RiskAdjustedStrategy(
        config=config,
        profitability_calc=mock_profitability_calc,
        risk_assessor=mock_risk_assessor,
    )


# =============================================================================
# SimpleYieldStrategy Tests
# =============================================================================


@pytest.mark.asyncio
async def test_simple_strategy_finds_better_yield(simple_strategy, mock_profitability_calc):
    """Test SimpleYield finds and recommends higher yield."""
    current_positions = {"Moonwell": Decimal("1000")}
    available_yields = {
        "Moonwell": Decimal("4.0"),
        "Aave V3": Decimal("5.0"),  # Better
        "Morpho": Decimal("8.0"),  # Best
    }

    recommendations = await simple_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 1
    rec = recommendations[0]
    assert rec.from_protocol == "Moonwell"
    assert rec.to_protocol == "Morpho"  # Should pick highest (8%)
    assert rec.amount == Decimal("1000")
    assert rec.expected_apy == Decimal("8.0")


@pytest.mark.asyncio
async def test_simple_strategy_skips_below_threshold(simple_strategy):
    """Test SimpleYield skips moves with APY improvement below threshold."""
    current_positions = {"Aave V3": Decimal("1000")}
    available_yields = {
        "Aave V3": Decimal("5.0"),
        "Moonwell": Decimal("5.2"),  # Only 0.2% improvement (below 0.5% threshold)
    }

    recommendations = await simple_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 0  # Should skip


@pytest.mark.asyncio
async def test_simple_strategy_skips_small_positions(simple_strategy):
    """Test SimpleYield skips positions below minimum size."""
    current_positions = {"Morpho": Decimal("50")}  # Below $100 minimum
    available_yields = {
        "Morpho": Decimal("5.0"),
        "Aave V3": Decimal("10.0"),  # Much better but position too small
    }

    recommendations = await simple_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 0


@pytest.mark.asyncio
async def test_simple_strategy_respects_profitability_gate(
    simple_strategy, mock_profitability_calc
):
    """Test SimpleYield blocks unprofitable moves."""
    # Mock unprofitable result
    mock_profitability_calc.calculate_profitability.return_value = MoveProfitability(
        apy_improvement=Decimal("1.0"),
        position_size=Decimal("1000"),
        annual_gain_usd=Decimal("10"),
        costs=RebalancingCosts(
            gas_withdraw=Decimal("5"),
            gas_approve=Decimal("0"),
            gas_swap=Decimal("0"),
            gas_deposit=Decimal("5"),
            slippage_cost=Decimal("0"),
            protocol_fees=Decimal("0"),
            total_cost=Decimal("10"),
        ),
        net_gain_first_year=Decimal("0"),  # Breaks even, not profitable
        break_even_days=365,
        roi_on_costs=Decimal("0"),
        is_profitable=False,
        rejection_reasons=["Net gain too low"],
        detailed_breakdown="Mock unprofitable",
    )

    current_positions = {"Aave V3": Decimal("1000")}
    available_yields = {
        "Aave V3": Decimal("5.0"),
        "Morpho": Decimal("6.0"),  # Better APY but unprofitable
    }

    recommendations = await simple_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 0


def test_simple_strategy_optimal_allocation_all_in(simple_strategy):
    """Test SimpleYield puts all capital in best opportunity."""
    total_capital = Decimal("10000")
    opportunities = {
        "Aave V3": Decimal("5.0"),
        "Morpho": Decimal("8.0"),  # Best
        "Moonwell": Decimal("6.0"),
    }

    allocation = simple_strategy.calculate_optimal_allocation(total_capital, opportunities)

    # Should allocate 100% to Morpho (highest APY)
    assert allocation == {"Morpho": Decimal("10000")}


def test_simple_strategy_should_rebalance_profitable(simple_strategy):
    """Test should_rebalance returns True for profitable move."""
    result = simple_strategy.should_rebalance(
        current_apy=Decimal("5.0"),
        target_apy=Decimal("8.0"),  # +3% improvement
        gas_cost=Decimal("5.0"),
        amount=Decimal("1000"),  # Annual gain: $30, cost: $5 → profitable
    )

    assert result is True


def test_simple_strategy_should_rebalance_unprofitable_gas(simple_strategy):
    """Test should_rebalance returns False when gas cost exceeds gain."""
    result = simple_strategy.should_rebalance(
        current_apy=Decimal("5.0"),
        target_apy=Decimal("5.6"),  # +0.6% improvement
        gas_cost=Decimal("10.0"),
        amount=Decimal("1000"),  # Annual gain: $6, cost: $10 → unprofitable
    )

    assert result is False


# =============================================================================
# RiskAdjustedStrategy Tests
# =============================================================================


@pytest.mark.asyncio
async def test_risk_adjusted_finds_safe_yield(
    risk_adjusted_strategy, mock_profitability_calc, mock_risk_assessor
):
    """Test RiskAdjusted finds profitable AND safe yield."""
    current_positions = {"Moonwell": Decimal("1000")}
    available_yields = {
        "Moonwell": Decimal("4.0"),
        "Aave V3": Decimal("8.0"),  # Better and safe (LOW risk)
    }

    recommendations = await risk_adjusted_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 1
    rec = recommendations[0]
    assert rec.from_protocol == "Moonwell"
    assert rec.to_protocol == "Aave V3"
    assert "Risk: LOW" in rec.reason  # Should mention risk level


@pytest.mark.asyncio
async def test_risk_adjusted_blocks_high_risk(
    risk_adjusted_strategy, mock_profitability_calc, mock_risk_assessor
):
    """Test RiskAdjusted blocks HIGH risk moves."""
    # Mock HIGH risk assessment
    mock_risk_assessor.assess_rebalance_risk.return_value = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        risk_score=Decimal("60"),
        factors={},
        recommendation="High risk",
    )
    mock_risk_assessor.should_proceed.return_value = False  # Block

    current_positions = {"Aave V3": Decimal("1000")}
    available_yields = {
        "Aave V3": Decimal("5.0"),
        "UnknownDEX": Decimal("50.0"),  # Suspiciously high APY, HIGH risk
    }

    recommendations = await risk_adjusted_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 0  # Should block


@pytest.mark.asyncio
async def test_risk_adjusted_blocks_critical_concentration(
    mock_profitability_calc
):
    """Test RiskAdjusted blocks moves that create CRITICAL concentration."""
    # Create fresh mock risk assessor for this test
    mock_risk_assessor = AsyncMock(spec=RiskAssessorAgent)

    # Mock that simulated concentration would be CRITICAL
    call_count = 0
    async def mock_concentration_assessment(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: current positions (LOW)
            return RiskAssessment(
                risk_level=RiskLevel.LOW,
                risk_score=Decimal("10"),
                factors={},
                recommendation="Well diversified",
            )
        elif call_count == 2:
            # Second call: simulated for Aave move (LOW)
            return RiskAssessment(
                risk_level=RiskLevel.LOW,
                risk_score=Decimal("20"),
                factors={},
                recommendation="Still diversified",
            )
        else:
            # Third+ call: simulated for Morpho move (CRITICAL)
            return RiskAssessment(
                risk_level=RiskLevel.CRITICAL,
                risk_score=Decimal("85"),
                factors={},
                recommendation="Critical concentration",
            )

    mock_risk_assessor.assess_position_concentration.side_effect = mock_concentration_assessment
    mock_risk_assessor.should_proceed.return_value = True
    mock_risk_assessor.assess_rebalance_risk.return_value = RiskAssessment(
        risk_level=RiskLevel.LOW,
        risk_score=Decimal("15"),
        factors={},
        recommendation="Safe",
    )

    # Create strategy with fresh mocks
    config = {
        "min_apy_improvement": Decimal("0.5"),
        "allow_high_risk": False,
    }
    strategy = RiskAdjustedStrategy(
        config=config,
        profitability_calc=mock_profitability_calc,
        risk_assessor=mock_risk_assessor,
    )

    current_positions = {
        "Aave V3": Decimal("2000"),
        "Morpho": Decimal("8000"),  # Moving this would create 100% concentration
    }
    available_yields = {
        "Aave V3": Decimal("5.0"),
        "Morpho": Decimal("3.0"),
        "Moonwell": Decimal("6.0"),  # Better but would concentrate
    }

    recommendations = await strategy.analyze_opportunities(
        current_positions, available_yields
    )

    # Should not recommend moving Morpho→Moonwell (would create over-concentration)
    assert all(rec.from_protocol != "Morpho" for rec in recommendations)


@pytest.mark.asyncio
async def test_risk_adjusted_allows_high_risk_when_enabled(
    mock_profitability_calc, mock_risk_assessor
):
    """Test RiskAdjusted allows HIGH risk when allow_high_risk=True."""
    # Create strategy with allow_high_risk=True
    config = {
        "allow_high_risk": True,  # Enable HIGH risk moves
        "min_apy_improvement": Decimal("0.5"),
    }
    strategy = RiskAdjustedStrategy(
        config=config,
        profitability_calc=mock_profitability_calc,
        risk_assessor=mock_risk_assessor,
    )

    # Mock HIGH risk but should_proceed returns True (elevated approval)
    mock_risk_assessor.assess_rebalance_risk.return_value = RiskAssessment(
        risk_level=RiskLevel.HIGH,
        risk_score=Decimal("60"),
        factors={},
        recommendation="High risk but allowed",
    )
    mock_risk_assessor.should_proceed.return_value = True  # Allow with elevated approval

    current_positions = {"Aave V3": Decimal("1000")}
    available_yields = {
        "Aave V3": Decimal("5.0"),
        "RiskyProtocol": Decimal("15.0"),  # High yield, HIGH risk
    }

    recommendations = await strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 1  # Should allow


def test_risk_adjusted_optimal_allocation_diversified(risk_adjusted_strategy):
    """Test RiskAdjusted diversifies across top protocols."""
    total_capital = Decimal("10000")
    opportunities = {
        "Morpho": Decimal("8.0"),  # Best
        "Aave V3": Decimal("6.0"),  # Second
        "Moonwell": Decimal("5.0"),  # Third
        "Aerodrome": Decimal("4.0"),  # Fourth (below diversification target)
    }

    allocation = risk_adjusted_strategy.calculate_optimal_allocation(
        total_capital, opportunities
    )

    # Should allocate across top 3 (diversification_target=3)
    assert len(allocation) == 3
    assert "Morpho" in allocation
    assert "Aave V3" in allocation
    assert "Moonwell" in allocation
    assert "Aerodrome" not in allocation

    # Total should equal capital
    assert sum(allocation.values()) == total_capital

    # No single protocol should exceed max concentration (40% = $4000)
    for amount in allocation.values():
        assert amount <= Decimal("4000")


def test_risk_adjusted_optimal_allocation_respects_max_concentration(risk_adjusted_strategy):
    """Test RiskAdjusted respects max_concentration_pct limit."""
    total_capital = Decimal("10000")
    opportunities = {
        "Morpho": Decimal("100.0"),  # Extremely high
        "Aave V3": Decimal("5.0"),  # Much lower
    }

    allocation = risk_adjusted_strategy.calculate_optimal_allocation(
        total_capital, opportunities
    )

    # Even though Morpho is much better, should not exceed 40% ($4000)
    assert allocation["Morpho"] <= Decimal("4000")


@pytest.mark.asyncio
async def test_risk_adjusted_conservative_first_alternative(
    risk_adjusted_strategy, mock_profitability_calc, mock_risk_assessor
):
    """Test RiskAdjusted only recommends first viable alternative (conservative)."""
    current_positions = {"Moonwell": Decimal("1000")}
    available_yields = {
        "Moonwell": Decimal("4.0"),
        "Aave V3": Decimal("8.0"),  # Best and safe
        "Morpho": Decimal("7.0"),  # Also good but should not recommend both
    }

    recommendations = await risk_adjusted_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    # Should only recommend ONE move per position (conservative)
    assert len(recommendations) == 1
    assert recommendations[0].to_protocol == "Aave V3"  # Highest APY


# =============================================================================
# Confidence Score Tests
# =============================================================================


@pytest.mark.asyncio
async def test_simple_strategy_confidence_calculation(simple_strategy, mock_profitability_calc):
    """Test SimpleYield calculates confidence based on profitability."""
    # Mock high profitability
    mock_profitability_calc.calculate_profitability.return_value = MoveProfitability(
        apy_improvement=Decimal("10.0"),
        position_size=Decimal("10000"),
        annual_gain_usd=Decimal("1000"),
        costs=RebalancingCosts(
            gas_withdraw=Decimal("2"),
            gas_approve=Decimal("0"),
            gas_swap=Decimal("0"),
            gas_deposit=Decimal("2"),
            slippage_cost=Decimal("0"),
            protocol_fees=Decimal("0"),
            total_cost=Decimal("4"),
        ),
        net_gain_first_year=Decimal("996"),  # Very high
        break_even_days=1,  # Very fast
        roi_on_costs=Decimal("24900"),  # 249x ROI
        is_profitable=True,
        rejection_reasons=[],
        detailed_breakdown="Mock highly profitable",
    )

    current_positions = {"Moonwell": Decimal("10000")}
    available_yields = {
        "Moonwell": Decimal("5.0"),
        "Morpho": Decimal("15.0"),  # Much better
    }

    recommendations = await simple_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 1
    # High profitability should result in high confidence (close to 100)
    assert recommendations[0].confidence >= 90


@pytest.mark.asyncio
async def test_risk_adjusted_confidence_includes_risk(
    risk_adjusted_strategy, mock_profitability_calc, mock_risk_assessor
):
    """Test RiskAdjusted confidence includes both profitability and risk."""
    # Mock good profitability + LOW risk
    mock_profitability_calc.calculate_profitability.return_value = MoveProfitability(
        apy_improvement=Decimal("5.0"),
        position_size=Decimal("1000"),
        annual_gain_usd=Decimal("50"),
        costs=RebalancingCosts(
            gas_withdraw=Decimal("1"),
            gas_approve=Decimal("0"),
            gas_swap=Decimal("0"),
            gas_deposit=Decimal("1"),
            slippage_cost=Decimal("0"),
            protocol_fees=Decimal("0"),
            total_cost=Decimal("2"),
        ),
        net_gain_first_year=Decimal("48"),
        break_even_days=15,
        roi_on_costs=Decimal("2400"),
        is_profitable=True,
        rejection_reasons=[],
        detailed_breakdown="Mock profitable",
    )

    mock_risk_assessor.assess_rebalance_risk.return_value = RiskAssessment(
        risk_level=RiskLevel.LOW,
        risk_score=Decimal("15"),  # LOW risk
        factors={},
        recommendation="Safe",
    )

    current_positions = {"Moonwell": Decimal("1000")}
    available_yields = {
        "Moonwell": Decimal("5.0"),
        "Aave V3": Decimal("10.0"),
    }

    recommendations = await risk_adjusted_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 1
    # LOW risk should boost confidence
    low_risk_confidence = recommendations[0].confidence

    # Now test with MEDIUM risk
    mock_risk_assessor.assess_rebalance_risk.return_value = RiskAssessment(
        risk_level=RiskLevel.MEDIUM,
        risk_score=Decimal("40"),  # MEDIUM risk
        factors={},
        recommendation="Normal risk",
    )

    recommendations2 = await risk_adjusted_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    # MEDIUM risk should have lower confidence than LOW risk
    medium_risk_confidence = recommendations2[0].confidence
    assert medium_risk_confidence < low_risk_confidence


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_simple_strategy_no_positions(simple_strategy):
    """Test SimpleYield handles empty positions."""
    current_positions = {}
    available_yields = {"Morpho": Decimal("10.0")}

    recommendations = await simple_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 0


@pytest.mark.asyncio
async def test_simple_strategy_already_optimal(simple_strategy):
    """Test SimpleYield recognizes when position is already optimal."""
    current_positions = {"Morpho": Decimal("1000")}
    available_yields = {
        "Morpho": Decimal("10.0"),  # Already in best position
        "Aave V3": Decimal("5.0"),
        "Moonwell": Decimal("4.0"),
    }

    recommendations = await simple_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    assert len(recommendations) == 0


def test_simple_strategy_empty_opportunities(simple_strategy):
    """Test SimpleYield handles no opportunities."""
    allocation = simple_strategy.calculate_optimal_allocation(
        total_capital=Decimal("1000"),
        opportunities={},
    )

    assert allocation == {}


@pytest.mark.asyncio
async def test_risk_adjusted_multiple_positions(
    risk_adjusted_strategy, mock_profitability_calc, mock_risk_assessor
):
    """Test RiskAdjusted handles multiple positions independently."""
    current_positions = {
        "Moonwell": Decimal("1000"),
        "Aerodrome": Decimal("2000"),
    }
    available_yields = {
        "Moonwell": Decimal("4.0"),
        "Aerodrome": Decimal("3.0"),
        "Aave V3": Decimal("8.0"),  # Better for both
        "Morpho": Decimal("7.0"),
    }

    recommendations = await risk_adjusted_strategy.analyze_opportunities(
        current_positions, available_yields
    )

    # Should recommend moving both to better yields (conservative: one each)
    # But RiskAdjusted only recommends first alternative per position
    assert len(recommendations) <= 2
    assert all(rec.to_protocol in ["Aave V3", "Morpho"] for rec in recommendations)
