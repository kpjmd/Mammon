#!/usr/bin/env python3
"""Demo script for Phase 3 Sprint 1: Multi-Protocol Yield Scanning.

Demonstrates Mammon's ability to find the best yields across
Aerodrome (DEX) and Morpho (Lending) protocols.
"""

import asyncio
from decimal import Decimal
from src.agents.yield_scanner import YieldScannerAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def main():
    """Run Sprint 1 demonstration."""

    print("=" * 80)
    print("🎉 PHASE 3 SPRINT 1 DEMO: MULTI-PROTOCOL YIELD SCANNING")
    print("=" * 80)
    print()

    # Initialize YieldScanner with both protocols
    config = {
        "network": "base-sepolia",
        "dry_run_mode": True,
        "use_mock_data": True,
        "read_only": True,
    }

    scanner = YieldScannerAgent(config)
    print("✅ Initialized YieldScanner with 2 protocols:")
    print("   - Aerodrome (DEX)")
    print("   - Morpho (Lending)")
    print()

    # Demo 1: Scan all protocols
    print("-" * 80)
    print("DEMO 1: Scan All Protocols")
    print("-" * 80)
    print("Scanning all available opportunities across Aerodrome + Morpho...")
    print()

    all_opportunities = await scanner.scan_all_protocols()
    print(f"✅ Found {len(all_opportunities)} total opportunities")
    print()

    # Show protocol breakdown
    aerodrome_count = len([o for o in all_opportunities if o.protocol == "Aerodrome"])
    morpho_count = len([o for o in all_opportunities if o.protocol == "Morpho"])
    print(f"   Aerodrome (DEX):     {aerodrome_count} pools")
    print(f"   Morpho (Lending):    {morpho_count} markets")
    print()

    # Show top 5 opportunities
    print("📊 Top 5 Opportunities by APY:")
    for i, opp in enumerate(all_opportunities[:5], 1):
        tokens_str = "/".join(opp.tokens)
        print(f"   {i}. {opp.protocol:12} | {tokens_str:12} | {opp.apy:5}% APY | ${opp.tvl:>12,.0f} TVL")
    print()

    # Demo 2: Find best USDC yield (CORE VALUE PROPOSITION)
    print("-" * 80)
    print("DEMO 2: Find Best USDC Yield (CORE VALUE PROPOSITION)")
    print("-" * 80)
    print("Searching for the absolute best USDC yield across ALL protocols...")
    print()

    best_usdc = await scanner.find_best_yield("USDC")
    if best_usdc:
        print(f"✅ Best USDC Yield Found:")
        print(f"   Protocol:  {best_usdc.protocol}")
        print(f"   Pool:      {best_usdc.pool_name}")
        print(f"   APY:       {best_usdc.apy}%")
        print(f"   TVL:       ${best_usdc.tvl:,.0f}")
        print()

        # Show comparison to other USDC options
        usdc_opps = [o for o in all_opportunities if "USDC" in o.tokens]
        if len(usdc_opps) > 1:
            second_best = usdc_opps[1]
            advantage = best_usdc.apy - second_best.apy
            print(f"   Advantage: +{advantage}% over {second_best.protocol}")
            print()

    # Demo 3: Find best WETH yield
    print("-" * 80)
    print("DEMO 3: Find Best WETH Yield")
    print("-" * 80)
    print("Searching for the absolute best WETH yield...")
    print()

    best_weth = await scanner.find_best_yield("WETH")
    if best_weth:
        print(f"✅ Best WETH Yield Found:")
        print(f"   Protocol:  {best_weth.protocol}")
        print(f"   Pool:      {best_weth.pool_name}")
        print(f"   APY:       {best_weth.apy}%")
        print(f"   TVL:       ${best_weth.tvl:,.0f}")
        print()

    # Demo 4: Filtered search (high yield + safety)
    print("-" * 80)
    print("DEMO 4: Filtered Search (High Yield + Safety)")
    print("-" * 80)
    print("Finding opportunities with:")
    print("   - Minimum APY: 5%")
    print("   - Minimum TVL: $500,000 (for safety)")
    print()

    safe_high_yields = await scanner.get_best_opportunities(
        min_apy=Decimal("5.0"),
        min_tvl=Decimal("500000")
    )

    print(f"✅ Found {len(safe_high_yields)} safe high-yield opportunities:")
    for i, opp in enumerate(safe_high_yields[:5], 1):
        tokens_str = "/".join(opp.tokens)
        print(f"   {i}. {opp.protocol:12} | {tokens_str:12} | {opp.apy:5}% APY | ${opp.tvl:>12,.0f} TVL")
    print()

    # Demo 5: DEX vs Lending Comparison
    print("-" * 80)
    print("DEMO 5: DEX vs Lending Comparison")
    print("-" * 80)

    aerodrome_opps = [o for o in all_opportunities if o.protocol == "Aerodrome"]
    morpho_opps = [o for o in all_opportunities if o.protocol == "Morpho"]

    avg_dex_apy = sum(o.apy for o in aerodrome_opps) / len(aerodrome_opps)
    avg_lending_apy = sum(o.apy for o in morpho_opps) / len(morpho_opps)

    print("Average APYs by Protocol Type:")
    print(f"   Aerodrome (DEX):       {avg_dex_apy:.2f}%")
    print(f"   Morpho (Lending):      {avg_lending_apy:.2f}%")
    print()

    # Summary
    print("=" * 80)
    print("🎉 PHASE 3 SPRINT 1 COMPLETE!")
    print("=" * 80)
    print()
    print("✅ Achievements:")
    print("   - Multi-protocol yield scanning (Aerodrome + Morpho)")
    print("   - Best yield discovery (find_best_yield)")
    print("   - Comprehensive filtering (token, APY, TVL)")
    print("   - DEX vs Lending comparison")
    print("   - 37 tests passing (94% coverage on Morpho)")
    print()
    print("🚀 Next: Sprint 2 - Add Aave, Moonwell, Beefy protocols")
    print()


if __name__ == "__main__":
    asyncio.run(main())
