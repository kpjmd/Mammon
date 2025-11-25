"""Integration tests for multi-protocol yield scanning.

Phase 3 Sprint 2: Tests for scanning all 4 protocols (Aerodrome, Morpho, Aave V3, Moonwell).
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from src.agents.yield_scanner import YieldScannerAgent, YieldOpportunity


@pytest.fixture
def scanner_config():
    """Configuration for yield scanner with all protocols."""
    return {
        "network": "base-sepolia",
        "read_only": True,
        "dry_run_mode": True,
        "use_mock_data": True,  # Use mock data for predictable tests
        "chainlink_enabled": False,
    }


# ===== INITIALIZATION TESTS =====


@pytest.mark.asyncio
async def test_scanner_initialization(scanner_config):
    """Test that YieldScanner initializes with all 4 protocols."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Should have 4 protocols: Aerodrome, Morpho, Aave V3, Moonwell
        assert len(scanner.protocols) == 4
        protocol_names = [p.name for p in scanner.protocols]
        assert "Aerodrome" in protocol_names
        assert "Morpho" in protocol_names
        assert "Aave V3" in protocol_names
        assert "Moonwell" in protocol_names


@pytest.mark.asyncio
async def test_scanner_dry_run_mode_enabled(scanner_config):
    """Test that scanner respects dry run mode."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)
        assert scanner.dry_run_mode is True


# ===== MULTI-PROTOCOL SCANNING TESTS =====


@pytest.mark.asyncio
async def test_scan_all_protocols_returns_opportunities(scanner_config):
    """Test that scan_all_protocols returns opportunities from all protocols."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)
        opportunities = await scanner.scan_all_protocols()

        # Should return a list
        assert isinstance(opportunities, list)
        # Should have opportunities from mock data
        assert len(opportunities) > 0


@pytest.mark.asyncio
async def test_scan_all_protocols_sorted_by_apy(scanner_config):
    """Test that opportunities are sorted by APY (highest first)."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)
        opportunities = await scanner.scan_all_protocols()

        # Check that opportunities are sorted descending by APY
        for i in range(len(opportunities) - 1):
            assert opportunities[i].apy >= opportunities[i + 1].apy


@pytest.mark.asyncio
async def test_scan_includes_all_protocol_types(scanner_config):
    """Test that scan includes both DEX and Lending protocols."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)
        opportunities = await scanner.scan_all_protocols()

        protocols_found = {opp.protocol for opp in opportunities}

        # Should have opportunities from multiple protocols
        assert len(protocols_found) >= 2


@pytest.mark.asyncio
async def test_scan_handles_protocol_failure_gracefully(scanner_config):
    """Test that scan continues if one protocol fails."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Make one protocol fail
        scanner.protocols[0].get_pools = MagicMock(side_effect=Exception("Protocol error"))

        # Should still return opportunities from other protocols
        opportunities = await scanner.scan_all_protocols()
        assert isinstance(opportunities, list)


# ===== FIND BEST YIELD TESTS =====


@pytest.mark.asyncio
async def test_find_best_yield_for_token(scanner_config):
    """Test finding best yield for a specific token across all protocols."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Find best USDC yield
        best = await scanner.find_best_yield("USDC")

        # Should return an opportunity
        assert best is not None
        assert isinstance(best, YieldOpportunity)
        assert "USDC" in [t.upper() for t in best.tokens]


@pytest.mark.asyncio
async def test_find_best_yield_returns_highest_apy(scanner_config):
    """Test that find_best_yield returns the highest APY for the token."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        best = await scanner.find_best_yield("USDC")

        # Get all USDC opportunities
        all_opps = await scanner.scan_all_protocols()
        usdc_opps = [opp for opp in all_opps if "USDC" in [t.upper() for t in opp.tokens]]

        # Best should have the highest APY
        if len(usdc_opps) > 0:
            max_apy = max(opp.apy for opp in usdc_opps)
            assert best.apy == max_apy


@pytest.mark.asyncio
async def test_find_best_yield_nonexistent_token(scanner_config):
    """Test finding best yield for a token that doesn't exist."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Try to find yield for non-existent token
        best = await scanner.find_best_yield("NONEXISTENT")

        # Should return None
        assert best is None


# ===== FILTERING TESTS =====


@pytest.mark.asyncio
async def test_filter_by_min_apy(scanner_config):
    """Test filtering opportunities by minimum APY."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Get opportunities with minimum APY
        min_apy = Decimal("5.0")
        filtered = await scanner.get_best_opportunities(min_apy=min_apy)

        # All returned opportunities should meet minimum
        for opp in filtered:
            assert opp.apy >= min_apy


@pytest.mark.asyncio
async def test_filter_by_min_tvl(scanner_config):
    """Test filtering opportunities by minimum TVL."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Get opportunities with minimum TVL
        min_tvl = Decimal("500000")  # $500k minimum
        filtered = await scanner.get_best_opportunities(min_tvl=min_tvl)

        # All returned opportunities should meet minimum
        for opp in filtered:
            assert opp.tvl >= min_tvl


@pytest.mark.asyncio
async def test_filter_by_token(scanner_config):
    """Test filtering opportunities by specific token."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Get only USDC opportunities
        filtered = await scanner.get_best_opportunities(token="USDC")

        # All returned opportunities should include USDC
        for opp in filtered:
            assert "USDC" in [t.upper() for t in opp.tokens]


@pytest.mark.asyncio
async def test_filter_combined_criteria(scanner_config):
    """Test filtering with multiple criteria combined."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Filter with multiple criteria
        filtered = await scanner.get_best_opportunities(
            token="USDC",
            min_apy=Decimal("3.0"),
            min_tvl=Decimal("100000"),
        )

        # All opportunities should meet all criteria
        for opp in filtered:
            assert "USDC" in [t.upper() for t in opp.tokens]
            assert opp.apy >= Decimal("3.0")
            assert opp.tvl >= Decimal("100000")


# ===== COMPARISON TESTS =====


@pytest.mark.asyncio
async def test_compare_current_position(scanner_config):
    """Test comparing current position against alternatives."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Compare a hypothetical current position
        comparison = await scanner.compare_current_position(
            current_protocol="Morpho",
            current_pool_id="morpho-usdc-market-1",
            current_apy=Decimal("4.0"),
        )

        # Should return comparison results
        assert "current" in comparison
        assert "recommendation" in comparison
        assert comparison["current"]["apy"] == Decimal("4.0")


@pytest.mark.asyncio
async def test_compare_current_position_optimal(scanner_config):
    """Test comparison when current position is already optimal."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Use a very high APY that's better than anything available
        comparison = await scanner.compare_current_position(
            current_protocol="Morpho",
            current_pool_id="test-pool",
            current_apy=Decimal("100.0"),
        )

        # Should recommend OPTIMAL (no better alternatives)
        assert comparison["recommendation"] == "OPTIMAL"


# ===== ENHANCED YIELD COMPARISON TESTS =====


@pytest.mark.asyncio
async def test_compare_yields_all_tokens(scanner_config):
    """Test enhanced yield comparison analytics across all tokens."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Get comprehensive analytics
        analytics = await scanner.compare_yields()

        # Should return comprehensive statistics
        assert "token" in analytics
        assert "total_opportunities" in analytics
        assert "best" in analytics
        assert "worst" in analytics
        assert "statistics" in analytics
        assert "protocol_breakdown" in analytics


@pytest.mark.asyncio
async def test_compare_yields_specific_token(scanner_config):
    """Test enhanced yield comparison for specific token."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        # Get analytics for USDC
        analytics = await scanner.compare_yields(token="USDC")

        # Should return USDC-specific analytics
        assert analytics["token"] == "USDC"
        assert "best" in analytics
        assert "statistics" in analytics


@pytest.mark.asyncio
async def test_compare_yields_statistics(scanner_config):
    """Test that yield comparison includes all required statistics."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        analytics = await scanner.compare_yields()
        stats = analytics["statistics"]

        # Should include all key statistics
        assert "average_apy" in stats
        assert "median_apy" in stats
        assert "spread" in stats
        assert "volatility" in stats
        assert "advantage_over_avg" in stats
        assert "advantage_pct" in stats


@pytest.mark.asyncio
async def test_compare_yields_protocol_breakdown(scanner_config):
    """Test that yield comparison includes protocol breakdown."""
    with patch("src.protocols.aave.get_web3"), \
         patch("src.protocols.moonwell.get_web3"), \
         patch("src.protocols.morpho.get_web3"):

        scanner = YieldScannerAgent(scanner_config)

        analytics = await scanner.compare_yields()
        breakdown = analytics["protocol_breakdown"]

        # Should have breakdown for multiple protocols
        assert len(breakdown) > 0

        # Each protocol should have required fields
        for protocol, stats in breakdown.items():
            assert "count" in stats
            assert "avg_apy" in stats
            assert "max_apy" in stats
            assert "min_apy" in stats
            assert "total_tvl" in stats
