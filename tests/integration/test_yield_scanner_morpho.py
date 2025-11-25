"""Integration tests for YieldScanner with Morpho protocol.

Phase 3 Sprint 1: Tests for multi-protocol yield scanning.
Tests the CORE VALUE PROPOSITION: Finding best yields across protocols.
"""

import pytest
from decimal import Decimal
from src.agents.yield_scanner import YieldScannerAgent


@pytest.fixture
def scanner_config():
    """Configuration for YieldScanner with Morpho enabled."""
    return {
        "network": "base-sepolia",
        "dry_run_mode": True,
        "use_mock_data": True,
        "read_only": True,
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_yield_scanner_with_morpho(scanner_config):
    """Test YieldScanner can successfully scan Morpho protocol.

    This validates that Morpho integration is working and returns data.
    """
    scanner = YieldScannerAgent(scanner_config)
    results = await scanner.scan_all_protocols()

    # Should have opportunities from both Aerodrome and Morpho
    assert len(results) > 0, "Should find opportunities"

    # Check we have Morpho opportunities
    morpho_opps = [opp for opp in results if opp.protocol == "Morpho"]
    assert len(morpho_opps) > 0, "Should have Morpho opportunities"

    # Verify data structure
    morpho_opp = morpho_opps[0]
    assert morpho_opp.pool_id is not None
    assert morpho_opp.pool_name is not None
    assert morpho_opp.apy > 0
    assert morpho_opp.tvl >= 0
    assert len(morpho_opp.tokens) > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_yield_scanner_has_both_protocols(scanner_config):
    """Test YieldScanner returns opportunities from both Aerodrome and Morpho."""
    scanner = YieldScannerAgent(scanner_config)
    results = await scanner.scan_all_protocols()

    protocols = {opp.protocol for opp in results}

    assert "Aerodrome" in protocols, "Should have Aerodrome opportunities"
    assert "Morpho" in protocols, "Should have Morpho opportunities"
    assert len(protocols) == 2, "Should have exactly 2 protocols"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_find_best_usdc_yield(scanner_config):
    """Test finding best USDC yield - CORE VALUE PROPOSITION.

    This is the primary use case: Find the absolute best yield for USDC
    across all protocols (Aerodrome DEX pools + Morpho lending).
    """
    scanner = YieldScannerAgent(scanner_config)
    best_pool = await scanner.find_best_yield("USDC")

    # Should find a USDC opportunity
    assert best_pool is not None, "Should find USDC opportunities"
    assert "USDC" in best_pool.tokens
    assert best_pool.apy > 0

    # Should have valid protocol
    assert best_pool.protocol in ["Aerodrome", "Morpho"]

    # Log for visibility
    print(f"\n✅ Best USDC yield: {best_pool.apy}% on {best_pool.protocol}")
    print(f"   Pool: {best_pool.pool_name}")
    print(f"   TVL: ${best_pool.tvl:,.0f}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_find_best_weth_yield(scanner_config):
    """Test finding best WETH yield across protocols."""
    scanner = YieldScannerAgent(scanner_config)
    best_pool = await scanner.find_best_yield("WETH")

    assert best_pool is not None, "Should find WETH opportunities"
    assert "WETH" in best_pool.tokens
    assert best_pool.apy > 0
    assert best_pool.protocol in ["Aerodrome", "Morpho"]

    print(f"\n✅ Best WETH yield: {best_pool.apy}% on {best_pool.protocol}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_find_best_yield_compares_across_protocols(scanner_config):
    """Test that find_best_yield actually compares across multiple protocols.

    Validates that we're getting the BEST yield, not just the first one.
    """
    scanner = YieldScannerAgent(scanner_config)

    # Get all USDC opportunities
    all_opps = await scanner.scan_all_protocols()
    usdc_opps = [opp for opp in all_opps if "USDC" in opp.tokens]

    # Get best via find_best_yield
    best = await scanner.find_best_yield("USDC")

    # Verify best is actually the highest APY
    assert best is not None
    all_usdc_apys = [opp.apy for opp in usdc_opps]
    max_apy = max(all_usdc_apys)

    assert best.apy == max_apy, "Best yield should have highest APY"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_find_best_yield_nonexistent_token(scanner_config):
    """Test finding best yield for token that doesn't exist returns None."""
    scanner = YieldScannerAgent(scanner_config)
    best_pool = await scanner.find_best_yield("NONEXISTENT")

    assert best_pool is None, "Should return None for nonexistent token"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_best_opportunities_filters_by_token(scanner_config):
    """Test filtering opportunities by specific token."""
    scanner = YieldScannerAgent(scanner_config)

    usdc_opps = await scanner.get_best_opportunities(token="USDC")

    assert len(usdc_opps) > 0, "Should find USDC opportunities"
    for opp in usdc_opps:
        assert "USDC" in opp.tokens, "All opportunities should include USDC"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_best_opportunities_filters_by_min_apy(scanner_config):
    """Test filtering opportunities by minimum APY."""
    scanner = YieldScannerAgent(scanner_config)

    high_yield_opps = await scanner.get_best_opportunities(min_apy=Decimal("5.0"))

    assert all(opp.apy >= Decimal("5.0") for opp in high_yield_opps), \
        "All opportunities should have APY >= 5%"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_best_opportunities_filters_by_min_tvl(scanner_config):
    """Test filtering opportunities by minimum TVL for safety."""
    scanner = YieldScannerAgent(scanner_config)

    safe_opps = await scanner.get_best_opportunities(min_tvl=Decimal("500000"))

    assert all(opp.tvl >= Decimal("500000") for opp in safe_opps), \
        "All opportunities should have TVL >= $500k"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_morpho_opportunities_have_lending_metadata(scanner_config):
    """Test Morpho opportunities include lending-specific metadata."""
    scanner = YieldScannerAgent(scanner_config)
    results = await scanner.scan_all_protocols()

    morpho_opps = [opp for opp in results if opp.protocol == "Morpho"]
    assert len(morpho_opps) > 0

    # Check lending-specific metadata
    morpho_opp = morpho_opps[0]
    assert "borrow_apy" in morpho_opp.metadata
    assert "utilization" in morpho_opp.metadata
    assert "risk_tier" in morpho_opp.metadata


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scanner_initializes_both_protocols(scanner_config):
    """Test scanner correctly initializes both Aerodrome and Morpho."""
    scanner = YieldScannerAgent(scanner_config)

    assert scanner.aerodrome is not None
    assert scanner.morpho is not None
    assert len(scanner.protocols) == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_find_best_yield_case_insensitive(scanner_config):
    """Test find_best_yield works with different token case."""
    scanner = YieldScannerAgent(scanner_config)

    best_upper = await scanner.find_best_yield("USDC")
    best_lower = await scanner.find_best_yield("usdc")
    best_mixed = await scanner.find_best_yield("Usdc")

    # All should find the same pool
    assert best_upper is not None
    assert best_lower is not None
    assert best_mixed is not None
    assert best_upper.pool_id == best_lower.pool_id == best_mixed.pool_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_opportunities_sorted_by_apy(scanner_config):
    """Test that opportunities are returned sorted by APY (highest first)."""
    scanner = YieldScannerAgent(scanner_config)
    results = await scanner.scan_all_protocols()

    # Verify sorted descending by APY
    for i in range(len(results) - 1):
        assert results[i].apy >= results[i + 1].apy, \
            "Opportunities should be sorted by APY (highest first)"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_compare_dex_vs_lending_yields(scanner_config):
    """Test comparing DEX (Aerodrome) vs Lending (Morpho) yields.

    This demonstrates the value of multi-protocol scanning.
    """
    scanner = YieldScannerAgent(scanner_config)
    all_opps = await scanner.scan_all_protocols()

    aerodrome_opps = [opp for opp in all_opps if opp.protocol == "Aerodrome"]
    morpho_opps = [opp for opp in all_opps if opp.protocol == "Morpho"]

    assert len(aerodrome_opps) > 0, "Should have DEX opportunities"
    assert len(morpho_opps) > 0, "Should have lending opportunities"

    # Log comparison
    avg_dex_apy = sum(opp.apy for opp in aerodrome_opps) / len(aerodrome_opps)
    avg_lending_apy = sum(opp.apy for opp in morpho_opps) / len(morpho_opps)

    print(f"\n📊 DEX vs Lending Comparison:")
    print(f"   Aerodrome (DEX) avg APY: {avg_dex_apy:.2f}%")
    print(f"   Morpho (Lending) avg APY: {avg_lending_apy:.2f}%")
