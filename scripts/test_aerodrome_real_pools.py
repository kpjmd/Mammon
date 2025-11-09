#!/usr/bin/env python3
"""Test script for querying REAL Aerodrome pools from Base mainnet.

This script demonstrates:
1. Connecting to Base mainnet (read-only)
2. Querying real Aerodrome pool data
3. Displaying pool information (reserves, tokens, fees)
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.protocols.aerodrome import AerodromeProtocol
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def test_real_aerodrome_pools():
    """Test querying real Aerodrome pools from Base mainnet."""
    print("\n" + "=" * 70)
    print("Testing REAL Aerodrome Pool Queries (Base Mainnet - Read Only)")
    print("=" * 70)

    # Initialize protocol with Base mainnet and dry_run_mode=False
    config = {
        "network": "base-mainnet",
        "dry_run_mode": False,  # Enable real queries!
    }

    protocol = AerodromeProtocol(config)

    try:
        print("\n📡 Fetching real pools from Base mainnet...")
        print("(This will query the blockchain directly)\n")

        # Fetch real pools
        pools = await protocol.get_pools()

        print(f"\n✅ Successfully fetched {len(pools)} real Aerodrome pools!\n")
        print("=" * 70)

        # Display pool information
        for i, pool in enumerate(pools[:10], 1):  # Show first 10 pools
            print(f"\n🌊 Pool #{i}: {pool.name}")
            print(f"   Pool ID: {pool.pool_id}")
            print(f"   Tokens: {' / '.join(pool.tokens)}")
            print(f"   TVL: ${pool.tvl:,.2f} (estimated)")
            print(f"   APY: {pool.apy}% (requires historical data)")

            # Show detailed metadata
            metadata = pool.metadata
            print(f"   Pool Address: {metadata.get('pool_address', 'N/A')}")
            print(f"   Fee: {metadata.get('fee_percent', 'N/A')}%")
            print(f"   Stable Pool: {metadata.get('is_stable', False)}")
            print(
                f"   Reserve0: {float(metadata.get('reserve0', 0)) / 10**metadata.get('decimals0', 18):,.2f} {pool.tokens[0]}"
            )
            print(
                f"   Reserve1: {float(metadata.get('reserve1', 0)) / 10**metadata.get('decimals1', 18):,.2f} {pool.tokens[1]}"
            )

        if len(pools) > 10:
            print(f"\n... and {len(pools) - 10} more pools")

        print("\n" + "=" * 70)
        print("✅ Real data fetching successful!")
        print("=" * 70)

        return True

    except Exception as e:
        print(f"\n❌ Error fetching real pools: {e}")
        logger.error(f"Real pool query failed: {e}", exc_info=True)
        return False


async def main():
    """Run the test."""
    print("\n🚀 Aerodrome Real Pool Query Test")
    print("This script queries LIVE data from Base mainnet blockchain\n")

    success = await test_real_aerodrome_pools()

    print("\n" + "=" * 70)
    print(f"{'✅ Test PASSED!' if success else '❌ Test FAILED'}")
    print("=" * 70 + "\n")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
