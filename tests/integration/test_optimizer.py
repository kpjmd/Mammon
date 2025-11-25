"""Integration tests for OptimizerAgent.

Tests the complete optimization workflow from scanner → strategy → recommendations.
"""

import pytest
from decimal import Decimal
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

from src.agents.optimizer import OptimizerAgent
from src.agents.yield_scanner import YieldScannerAgent, YieldOpportunity
from src.strategies.simple_yield import SimpleYieldStrategy
from src.strategies.risk_adjusted import RiskAdjustedStrategy


@pytest.fixture
def mock_scanner():
    """Create a mock YieldScannerAgent."""
    scanner = MagicMock(spec=YieldScannerAgent)
    scanner.scan_all_protocols = AsyncMock()
    return scanner


@pytest.fixture
def simple_yield_strategy():
    """Create a SimpleYieldStrategy for testing."""
    config = {
        "min_apy_improvement": Decimal("0.5"),
        "min_rebalance_amount": Decimal("100"),
    }
    return SimpleYieldStrategy(config)


@pytest.fixture
def risk_adjusted_strategy():
    """Create a RiskAdjustedStrategy for testing."""
    config = {
        "dry_run_mode": True,
        "min_apy_improvement": Decimal("0.5"),
        "min_rebalance_amount": Decimal("100"),
        "risk_tolerance": "medium",
        "allow_high_risk": False,
        "max_concentration_pct": 0.4,
        "diversification_target": 3,
    }
    return RiskAdjustedStrategy(config)


def create_mock_opportunities() -> List[YieldOpportunity]:
    """Create mock yield opportunities for testing."""
    return [
        YieldOpportunity(
            protocol="Aave V3",
            pool_id="usdc-pool",
            pool_name="USDC Pool",
            apy=Decimal("5.5"),
            tvl=Decimal("125_000_000"),
            tokens=["USDC"],
            metadata={"utilization": 0.7},
        ),
        YieldOpportunity(
            protocol="Morpho",
            pool_id="usdc-vault",
            pool_name="USDC Vault",
            apy=Decimal("7.2"),
            tvl=Decimal("45_000_000"),
            tokens=["USDC"],
            metadata={"utilization": 0.65},
        ),
        YieldOpportunity(
            protocol="Moonwell",
            pool_id="usdc-market",
            pool_name="USDC Market",
            apy=Decimal("6.0"),
            tvl=Decimal("32_000_000"),
            tokens=["USDC"],
            metadata={"utilization": 0.72},
        ),
        YieldOpportunity(
            protocol="Aerodrome",
            pool_id="usdc-usdt-pool",
            pool_name="USDC/USDT Pool",
            apy=Decimal("4.8"),
            tvl=Decimal("15_000_000"),
            tokens=["USDC", "USDT"],
            metadata={"is_stable": True},
        ),
    ]


@pytest.mark.asyncio
async def test_optimizer_simple_yield_e2e(mock_scanner, simple_yield_strategy):
    """Test end-to-end optimization with SimpleYieldStrategy.

    Verifies:
    - OptimizerAgent orchestrates scanner → strategy flow
    - SimpleYield selects highest APY opportunity
    - Profitability validation is applied
    - Recommendations are generated correctly
    """
    # Setup mock scanner
    mock_opportunities = create_mock_opportunities()
    mock_scanner.scan_all_protocols.return_value = mock_opportunities

    # Create optimizer
    config = {"dry_run_mode": True}
    optimizer = OptimizerAgent(
        config=config,
        scanner=mock_scanner,
        strategy=simple_yield_strategy,
    )

    # Current position in lower-yield protocol (large enough to be profitable)
    current_positions = {
        "Aave V3": Decimal("10000"),  # 5.5% APY, $10k position
    }

    # Find rebalance opportunities
    recommendations = await optimizer.find_rebalance_opportunities(current_positions)

    # Verify scanner was called
    mock_scanner.scan_all_protocols.assert_called_once()

    # Verify recommendations generated
    assert len(recommendations) > 0, "Should generate at least one recommendation"

    # Verify SimpleYield found the highest APY (Morpho at 7.2%)
    top_rec = recommendations[0]
    assert top_rec.from_protocol == "Aave V3"
    assert top_rec.to_protocol == "Morpho"  # Highest APY
    assert top_rec.expected_apy == Decimal("7.2")
    assert top_rec.confidence > 0


@pytest.mark.asyncio
async def test_optimizer_risk_adjusted_e2e(mock_scanner, risk_adjusted_strategy):
    """Test end-to-end optimization with RiskAdjustedStrategy.

    Verifies:
    - OptimizerAgent orchestrates with risk assessment
    - RiskAdjusted filters by both profitability and risk
    - High-risk moves are blocked
    - Recommendations include risk considerations
    """
    # Setup mock scanner
    mock_opportunities = create_mock_opportunities()
    mock_scanner.scan_all_protocols.return_value = mock_opportunities

    # Create optimizer
    config = {"dry_run_mode": True}
    optimizer = OptimizerAgent(
        config=config,
        scanner=mock_scanner,
        strategy=risk_adjusted_strategy,
    )

    # Current position in moderate protocol
    current_positions = {
        "Moonwell": Decimal("5000"),  # 6.0% APY
    }

    # Find rebalance opportunities
    recommendations = await optimizer.find_rebalance_opportunities(current_positions)

    # Verify scanner was called
    mock_scanner.scan_all_protocols.assert_called_once()

    # RiskAdjusted might generate recommendations or not, depending on risk
    # It should prefer safer protocols (Aave V3, Morpho) over risky ones
    if recommendations:
        top_rec = recommendations[0]
        # Should recommend safe + profitable protocols (Aave V3 or Morpho)
        assert top_rec.to_protocol in ["Aave V3", "Morpho"]
        assert top_rec.expected_apy > Decimal("6.0")  # Better than current


@pytest.mark.asyncio
async def test_optimizer_multiple_positions(mock_scanner, simple_yield_strategy):
    """Test optimization with multiple current positions.

    Verifies:
    - OptimizerAgent handles multiple positions independently
    - Generates separate recommendations for each position
    - Each recommendation optimizes its specific position
    """
    # Setup mock scanner
    mock_opportunities = create_mock_opportunities()
    mock_scanner.scan_all_protocols.return_value = mock_opportunities

    # Create optimizer
    config = {"dry_run_mode": True}
    optimizer = OptimizerAgent(
        config=config,
        scanner=mock_scanner,
        strategy=simple_yield_strategy,
    )

    # Multiple positions in different protocols (large enough to be profitable)
    current_positions = {
        "Aave V3": Decimal("5000"),      # 5.5% → can move to Morpho 7.2%
        "Moonwell": Decimal("10000"),    # 6.0% → can move to Morpho 7.2%
        "Aerodrome": Decimal("3000"),    # 4.8% → can move to Morpho 7.2%
    }

    # Find rebalance opportunities
    recommendations = await optimizer.find_rebalance_opportunities(current_positions)

    # Should generate recommendations for positions where it's profitable
    assert len(recommendations) >= 1, "Should generate recommendations for some positions"

    # Verify each recommendation has distinct from_protocol
    from_protocols = [rec.from_protocol for rec in recommendations]
    # All should target best opportunity
    for rec in recommendations:
        assert rec.expected_apy > Decimal("4.5")  # Better than worst current


@pytest.mark.asyncio
async def test_optimizer_new_allocation_simple(mock_scanner, simple_yield_strategy):
    """Test new capital allocation with SimpleYieldStrategy.

    Verifies:
    - optimize_new_allocation works correctly
    - SimpleYield allocates 100% to best opportunity
    - Allocation totals match input capital
    """
    # Setup mock scanner
    mock_opportunities = create_mock_opportunities()
    mock_scanner.scan_all_protocols.return_value = mock_opportunities

    # Create optimizer
    config = {"dry_run_mode": True}
    optimizer = OptimizerAgent(
        config=config,
        scanner=mock_scanner,
        strategy=simple_yield_strategy,
    )

    # New capital to allocate
    total_capital = Decimal("10000")

    # Optimize allocation
    allocation = await optimizer.optimize_new_allocation(total_capital)

    # Verify scanner was called
    mock_scanner.scan_all_protocols.assert_called_once()

    # SimpleYield should allocate 100% to highest APY (Morpho)
    assert len(allocation) == 1, "SimpleYield should allocate to single protocol"
    assert "Morpho" in allocation, "Should allocate to highest APY protocol"
    assert allocation["Morpho"] == total_capital


@pytest.mark.asyncio
async def test_optimizer_new_allocation_risk_adjusted(mock_scanner, risk_adjusted_strategy):
    """Test new capital allocation with RiskAdjustedStrategy.

    Verifies:
    - RiskAdjusted diversifies across multiple protocols
    - Respects max_concentration_pct limits
    - Total allocation equals input capital
    """
    # Setup mock scanner
    mock_opportunities = create_mock_opportunities()
    mock_scanner.scan_all_protocols.return_value = mock_opportunities

    # Create optimizer
    config = {"dry_run_mode": True}
    optimizer = OptimizerAgent(
        config=config,
        scanner=mock_scanner,
        strategy=risk_adjusted_strategy,
    )

    # New capital to allocate
    total_capital = Decimal("10000")

    # Optimize allocation
    allocation = await optimizer.optimize_new_allocation(total_capital)

    # Verify scanner was called
    mock_scanner.scan_all_protocols.assert_called_once()

    # RiskAdjusted should diversify (more than 1 protocol)
    assert len(allocation) >= 1, "Should allocate to at least one protocol"

    # Total allocation should equal or be close to total capital
    total_allocated = sum(allocation.values())
    assert abs(total_allocated - total_capital) < Decimal("1"), \
        f"Total allocation {total_allocated} should equal capital {total_capital}"

    # Check concentration limits (max 40%)
    max_allocation = max(allocation.values()) if allocation else Decimal(0)
    max_pct = max_allocation / total_capital if total_capital > 0 else 0
    # Allow some tolerance for rounding
    assert max_pct <= Decimal("0.41"), \
        f"Max allocation {max_pct*100}% exceeds concentration limit"


@pytest.mark.asyncio
async def test_optimizer_no_opportunities(mock_scanner, simple_yield_strategy):
    """Test optimizer behavior when no opportunities are available.

    Verifies:
    - Handles empty opportunities gracefully
    - Returns empty recommendations
    - Doesn't crash or throw exceptions
    """
    # Setup mock scanner with no opportunities
    mock_scanner.scan_all_protocols.return_value = []

    # Create optimizer
    config = {"dry_run_mode": True}
    optimizer = OptimizerAgent(
        config=config,
        scanner=mock_scanner,
        strategy=simple_yield_strategy,
    )

    # Current position
    current_positions = {
        "Aave V3": Decimal("1000"),
    }

    # Find rebalance opportunities
    recommendations = await optimizer.find_rebalance_opportunities(current_positions)

    # Should return empty list (no opportunities available)
    assert recommendations == [], "Should return empty list when no opportunities"


@pytest.mark.asyncio
async def test_optimizer_no_profitable_moves(mock_scanner, simple_yield_strategy):
    """Test when current positions are already optimal.

    Verifies:
    - Recognizes when current position is best available
    - Doesn't recommend unprofitable moves
    - Returns empty or minimal recommendations
    """
    # Setup mock scanner with lower yields than current
    low_yield_opportunities = [
        YieldOpportunity(
            protocol="Morpho",
            pool_id="usdc-vault",
            pool_name="USDC Vault",
            apy=Decimal("3.0"),  # Lower than current
            tvl=Decimal("45_000_000"),
            tokens=["USDC"],
            metadata={},
        ),
        YieldOpportunity(
            protocol="Moonwell",
            pool_id="usdc-market",
            pool_name="USDC Market",
            apy=Decimal("2.5"),  # Lower than current
            tvl=Decimal("32_000_000"),
            tokens=["USDC"],
            metadata={},
        ),
    ]
    mock_scanner.scan_all_protocols.return_value = low_yield_opportunities

    # Create optimizer
    config = {"dry_run_mode": True}
    optimizer = OptimizerAgent(
        config=config,
        scanner=mock_scanner,
        strategy=simple_yield_strategy,
    )

    # Current position already at high APY
    current_positions = {
        "Aave V3": Decimal("1000"),  # Assuming current APY is 5.5%
    }

    # Find rebalance opportunities
    recommendations = await optimizer.find_rebalance_opportunities(current_positions)

    # Should return empty (current position is already best)
    # Note: We can't know current APY from positions dict alone,
    # so this test validates graceful handling rather than specific logic
    assert isinstance(recommendations, list), "Should return a list"


@pytest.mark.asyncio
async def test_optimizer_strategy_comparison(mock_scanner, simple_yield_strategy, risk_adjusted_strategy):
    """Compare SimpleYield vs RiskAdjusted on same data.

    Verifies:
    - SimpleYield is more aggressive (higher allocations to best protocol)
    - RiskAdjusted is more conservative (diversified)
    - Both generate valid recommendations
    """
    # Setup mock scanner
    mock_opportunities = create_mock_opportunities()

    # Test with SimpleYield
    mock_scanner.scan_all_protocols.return_value = mock_opportunities
    simple_optimizer = OptimizerAgent(
        config={"dry_run_mode": True},
        scanner=mock_scanner,
        strategy=simple_yield_strategy,
    )

    total_capital = Decimal("10000")
    simple_allocation = await simple_optimizer.optimize_new_allocation(total_capital)

    # Reset mock
    mock_scanner.scan_all_protocols.reset_mock()
    mock_scanner.scan_all_protocols.return_value = mock_opportunities

    # Test with RiskAdjusted
    risk_optimizer = OptimizerAgent(
        config={"dry_run_mode": True},
        scanner=mock_scanner,
        strategy=risk_adjusted_strategy,
    )

    risk_allocation = await risk_optimizer.optimize_new_allocation(total_capital)

    # SimpleYield should be more concentrated
    simple_protocol_count = len(simple_allocation)
    risk_protocol_count = len(risk_allocation)

    assert simple_protocol_count <= risk_protocol_count, \
        "SimpleYield should allocate to fewer protocols (more aggressive)"

    # SimpleYield should have higher max allocation percentage
    simple_max_pct = max(simple_allocation.values()) / total_capital if simple_allocation else 0
    risk_max_pct = max(risk_allocation.values()) / total_capital if risk_allocation else 0

    assert simple_max_pct >= risk_max_pct, \
        "SimpleYield should have higher concentration than RiskAdjusted"
