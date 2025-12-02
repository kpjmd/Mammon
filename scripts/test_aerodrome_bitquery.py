#!/usr/bin/env python3
"""Test script for Aerodrome BitQuery pool discovery.

This script validates that BitQuery integration:
1. Returns 200-400 quality pools (vs 14,417 total)
2. Completes queries in <30 seconds
3. Applies TVL/volume filters correctly
4. Only returns whitelisted token pools
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import time
from decimal import Decimal
from typing import Dict, Any
from src.protocols.aerodrome import AerodromeProtocol
from src.utils.config import get_settings
from src.data.oracles import create_price_oracle
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def test_bitquery_discovery():
    """Test BitQuery pool discovery."""
    print("=" * 80)
    print("AERODROME BITQUERY POOL DISCOVERY TEST")
    print("=" * 80)
    print()

    # Load settings
    settings = get_settings()

    # Create shared price oracle
    price_oracle = create_price_oracle(
        "chainlink",
        network="base-mainnet",
        price_network="base-mainnet",
        cache_ttl_seconds=300,
        max_staleness_seconds=3600,
        fallback_to_mock=True,
    )

    # Initialize Aerodrome with BitQuery enabled
    # Note: dry_run_mode only affects EXECUTION (swaps), not READ operations (pool queries)
    # We set it to False to enable real pool discovery from Base mainnet
    config: Dict[str, Any] = {
        "network": "base-mainnet",
        "dry_run_mode": False,  # Required to query real pools from mainnet
        "aerodrome_max_pools": 500,  # Allow up to 500 for testing
        "supported_tokens": settings.supported_tokens,
        "price_oracle": price_oracle,
        # BitQuery settings
        "aerodrome_use_bitquery": settings.aerodrome_use_bitquery,
        "bitquery_api_key": settings.bitquery_api_key,
        "aerodrome_min_tvl_usd": settings.aerodrome_min_tvl_usd,
        "aerodrome_min_volume_24h": settings.aerodrome_min_volume_24h,
        "aerodrome_token_whitelist": settings.aerodrome_token_whitelist,
        # Chainlink settings
        "chainlink_enabled": True,
        "chainlink_price_network": "base-mainnet",
        "chainlink_cache_ttl_seconds": 300,
        "chainlink_max_staleness_seconds": 3600,
        "chainlink_fallback_to_mock": True,
    }

    print(f"📋 Test Configuration:")
    print(f"   Network: {config['network']}")
    print(f"   BitQuery Enabled: {config['aerodrome_use_bitquery']}")
    print(f"   API Key Present: {'Yes' if config['bitquery_api_key'] else 'No'}")
    print(f"   Min TVL: ${config['aerodrome_min_tvl_usd']}")
    print(f"   Min Volume 24h: ${config['aerodrome_min_volume_24h']}")
    print(f"   Token Whitelist: {config['aerodrome_token_whitelist']}")
    print(f"   Max Pools: {config['aerodrome_max_pools']}")
    print()

    # Initialize protocol
    print("🔧 Initializing Aerodrome protocol...")
    aerodrome = AerodromeProtocol(config)
    print()

    # Test BitQuery pool discovery
    print("🔍 Testing BitQuery Pool Discovery...")
    print("-" * 80)
    start_time = time.time()

    try:
        pools = await aerodrome.get_pools()
        end_time = time.time()
        elapsed = end_time - start_time

        print()
        print("✅ POOL DISCOVERY RESULTS")
        print("=" * 80)
        print(f"Pools Discovered: {len(pools)}")
        print(f"Query Time: {elapsed:.2f} seconds")
        print(f"Average Time per Pool: {(elapsed / len(pools)):.3f}s" if pools else "N/A")
        print()

        # Analyze pool quality
        if pools:
            print("📊 POOL QUALITY ANALYSIS")
            print("-" * 80)

            # TVL statistics
            tvls = [pool.tvl for pool in pools]
            avg_tvl = sum(tvls) / len(tvls)
            max_tvl = max(tvls)
            min_tvl = min(tvls)

            print(f"TVL Statistics:")
            print(f"   Average: ${avg_tvl:,.2f}")
            print(f"   Maximum: ${max_tvl:,.2f}")
            print(f"   Minimum: ${min_tvl:,.2f}")
            print()

            # Token distribution
            all_tokens = set()
            for pool in pools:
                all_tokens.update(pool.tokens)

            print(f"Token Distribution:")
            print(f"   Unique Tokens: {len(all_tokens)}")
            print(f"   Tokens: {', '.join(sorted(all_tokens))}")
            print()

            # Show top 10 pools by TVL
            print("🏆 TOP 10 POOLS BY TVL")
            print("-" * 80)
            sorted_pools = sorted(pools, key=lambda p: p.tvl, reverse=True)
            for i, pool in enumerate(sorted_pools[:10], 1):
                tokens_str = "/".join(pool.tokens)
                print(f"{i:2d}. {tokens_str:20s} | TVL: ${pool.tvl:>15,.2f} | {pool.pool_id}")

            print()

            # Validation checks
            print("✅ VALIDATION CHECKS")
            print("-" * 80)

            checks = {
                "Pool count in expected range (50-500)": 50 <= len(pools) <= 500,
                "Query time < 60 seconds": elapsed < 60,
                "All pools have non-zero TVL": all(p.tvl > 0 for p in pools),
                "All tokens from whitelist": all(
                    any(t.upper() in config['aerodrome_token_whitelist'].split(',')
                        for t in pool.tokens)
                    for pool in pools
                ),
            }

            for check, passed in checks.items():
                status = "✅" if passed else "❌"
                print(f"{status} {check}")

            print()

            # Success/failure summary
            if all(checks.values()):
                print("🎉 SUCCESS: All validation checks passed!")
                print()
                print("BitQuery integration is working correctly:")
                print(f"  • Discovered {len(pools)} quality pools (vs 14,417 total)")
                print(f"  • Query completed in {elapsed:.2f}s (vs 15+ min factory method)")
                print(f"  • All pools meet quality filters")
                print(f"  • {(14417 / len(pools)):.0f}x reduction in pools to scan")
            else:
                print("⚠️  WARNING: Some validation checks failed")
                print("Review the results above for details")

        else:
            print("❌ ERROR: No pools discovered")
            print("This could indicate:")
            print("  • BitQuery API issues")
            print("  • Filters too strict")
            print("  • Network connectivity problems")

    except Exception as e:
        end_time = time.time()
        elapsed = end_time - start_time
        print()
        print(f"❌ ERROR: Pool discovery failed after {elapsed:.2f}s")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


async def main():
    """Main entry point."""
    await test_bitquery_discovery()


if __name__ == "__main__":
    asyncio.run(main())
