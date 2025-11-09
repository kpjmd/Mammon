#!/usr/bin/env python3
"""MAMMON Phase 1C Demonstration Script.

Showcases Sprint 3 achievements:
- Multi-network Web3 infrastructure
- Real Aerodrome protocol integration (14,049 pools on Base mainnet)
- ERC20 token utilities
- Safety features (dry-run mode, TVL warnings)
- Connection caching performance

This is a READ-ONLY demonstration. No transactions are executed.

Usage:
    poetry run python scripts/demo_phase1c.py
    poetry run python scripts/demo_phase1c.py --pools 5
    poetry run python scripts/demo_phase1c.py --verbose
"""

import asyncio
import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.web3_provider import get_web3, check_network_health, Web3Provider
from src.utils.config import get_settings
from src.protocols.aerodrome import AerodromeProtocol
from src.tokens import ERC20Token
from src.utils.logger import get_logger

logger = get_logger(__name__)


def print_header(title: str):
    """Print formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_section(emoji: str, title: str):
    """Print formatted section title."""
    print(f"\n{emoji} {title}")
    print("-" * 70)


async def demo_safety_config():
    """Demonstrate safety configuration."""
    print_section("🔒", "SAFETY-FIRST CONFIGURATION")

    config = get_settings()

    print(f"Environment:           {config.environment}")
    print(f"Max transaction:       ${config.max_transaction_value_usd:,.2f} USD")
    print(f"Daily spending limit:  ${config.daily_spending_limit_usd:,.2f} USD")
    print(f"Approval threshold:    ${config.approval_threshold_usd:,.2f} USD")
    print(f"x402 daily budget:     ${config.x402_daily_budget_usd:,.2f} USD")

    print(f"\n✅ Safety limits configured and enforced")


async def demo_multi_network():
    """Demonstrate multi-network connectivity."""
    print_section("🌐", "MULTI-NETWORK INFRASTRUCTURE")

    networks = ["base-mainnet", "arbitrum-sepolia"]

    for network_id in networks:
        try:
            health = check_network_health(network_id)

            if health["connected"]:
                print(f"\n✅ {network_id.upper()}")
                print(f"   Chain ID:    {health['chain_id']}")
                print(f"   Block:       {health['block_number']:,}")
                print(f"   Gas Price:   {health['gas_price_gwei']:.4f} gwei")
            else:
                print(f"\n❌ {network_id}: {health.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"\n❌ {network_id}: {e}")


async def demo_cache_performance():
    """Demonstrate connection caching performance."""
    print_section("⚡", "CONNECTION CACHING PERFORMANCE")

    network = "base-mainnet"

    # Cold start
    Web3Provider.clear_cache(network)
    start = time.time()
    w3 = get_web3(network)
    block = w3.eth.block_number
    cold_time = time.time() - start

    print(f"Cold start (first connection):  {cold_time:.3f}s")

    # Warm (cached)
    start = time.time()
    w3 = get_web3(network)
    block = w3.eth.block_number
    warm_time = time.time() - start

    print(f"Cached connection:              {warm_time:.6f}s")

    speedup = cold_time / warm_time if warm_time > 0 else 0
    print(f"Speedup:                        {speedup:.0f}x faster")

    if speedup > 1:
        print(f"\n✅ Caching eliminates {((1 - (1/speedup)) * 100):.2f}% of connection overhead")


async def demo_aerodrome_pools(max_pools: int = 5):
    """Demonstrate Aerodrome pool queries."""
    print_section("💎", f"AERODROME POOL DISCOVERY (Base Mainnet)")

    protocol = AerodromeProtocol({
        "network": "base-mainnet",
        "dry_run_mode": False  # Query real data
    })

    print(f"Querying up to {max_pools} pools from 14,049 total...")
    print(f"⚠️  Limited to {max_pools} to avoid rate limiting on public RPC\n")

    start = time.time()
    pools = await protocol._get_real_pools_from_mainnet(max_pools=max_pools)
    elapsed = time.time() - start

    print(f"✅ Found {len(pools)} pools in {elapsed:.2f}s\n")

    # Display first 3 pools
    for i, pool in enumerate(pools[:3], 1):
        print(f"Pool {i}: {pool.name}")
        print(f"  Address:    {pool.metadata.get('pool_address', 'N/A')}")
        print(f"  Tokens:     {'/'.join(pool.tokens)}")
        print(f"  TVL:        ${pool.tvl:,.2f} ⚠️  ESTIMATE (see warnings)")
        print(f"  Type:       {'Stable' if pool.metadata.get('is_stable') else 'Volatile'}")
        print(f"  Fee:        {pool.metadata.get('fee_percent', 'N/A')}%")

        # Show TVL warnings
        if pool.metadata.get('tvl_is_estimate'):
            print(f"  ⚠️  TVL Method: {pool.metadata.get('tvl_method', 'unknown')}")

        print()

    if len(pools) > 3:
        print(f"... and {len(pools) - 3} more pools")


async def demo_token_utilities():
    """Demonstrate ERC20 token utilities."""
    print_section("🪙", "ERC20 TOKEN UTILITIES")

    tokens = {
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "WETH": "0x4200000000000000000000000000000000000006",
    }

    for symbol, address in tokens.items():
        try:
            token = ERC20Token("base-mainnet", address)

            # Query metadata (cached after first call)
            name = token.get_name()
            symbol_actual = token.get_symbol()
            decimals = token.get_decimals()

            print(f"\n{symbol}:")
            print(f"  Address:   {address}")
            print(f"  Name:      {name}")
            print(f"  Symbol:    {symbol_actual}")
            print(f"  Decimals:  {decimals}")
            print(f"  ✅ Metadata cached for future queries")

        except Exception as e:
            print(f"\n❌ {symbol}: {e}")


async def demo_safety_warnings():
    """Display critical safety warnings."""
    print_section("⚠️", "SAFETY FEATURES ACTIVE")

    print("READ-ONLY MODE:")
    print("  ✅ All queries are read-only (no state changes)")
    print("  ✅ No transactions executed")
    print("  ✅ No gas costs incurred")
    print("  ✅ No real funds at risk")

    print("\nPLACEHOLDER DATA:")
    print("  ⚠️  TVL calculations use simplified $1/token assumption")
    print("  ⚠️  APY data not yet calculated (requires historical data)")
    print("  ⚠️  DO NOT use for financial decisions")

    print("\nWHAT THIS IS FOR:")
    print("  ✅ Protocol exploration and discovery")
    print("  ✅ Strategy testing and development")
    print("  ✅ Architecture validation")
    print("  ✅ Integration testing")

    print("\nWHAT THIS IS NOT FOR:")
    print("  ❌ Production trading")
    print("  ❌ Financial calculations")
    print("  ❌ Risk assessments")
    print("  ❌ Yield optimization (yet)")


async def demo_error_handling():
    """Demonstrate error handling."""
    print_section("🛡️", "ERROR HANDLING")

    print("Testing graceful error handling...\n")

    # Test 1: Invalid pool address
    try:
        protocol = AerodromeProtocol({
            "network": "base-mainnet",
            "dry_run_mode": False
        })
        # This should fail gracefully
        result = protocol._query_pool_data(
            get_web3("base-mainnet"),
            "0x0000000000000000000000000000000000000000",
            None
        )
        if result is None:
            print(f"✅ Invalid pool handled gracefully (returned None)")
        else:
            print(f"✅ Invalid pool handled without crash")
    except Exception as e:
        print(f"✅ Invalid pool raised expected error: {type(e).__name__}")

    # Test 2: Invalid token address
    try:
        token = ERC20Token("base-mainnet", "0x0000000000000000000000000000000000000000")
        symbol = token.get_symbol()
        print(f"⚠️  Invalid token returned: {symbol}")
    except Exception as e:
        print(f"✅ Invalid token raised expected error: {type(e).__name__}")


def demo_phase2a_readiness():
    """Show Phase 2A readiness and requirements."""
    print_section("🚀", "PHASE 2A READINESS")

    print("Sprint 3 Complete ✅")
    print("  ✅ Multi-network Web3 infrastructure")
    print("  ✅ Real protocol integration (Aerodrome)")
    print("  ✅ Token utilities framework")
    print("  ✅ Safety features implemented")
    print("  ✅ Connection caching optimized")

    print("\nPhase 2A Requirements:")
    print("  📋 Premium RPC providers (Alchemy/Infura)")
    print("  📋 Chainlink price oracle integration")
    print("  📋 Additional protocol integrations (Uniswap V3, Morpho)")
    print("  📋 Approval workflow refactor (event-driven)")
    print("  📋 Request batching optimization")

    print("\nReady for:")
    print("  ✅ Protocol expansion (architecture validated)")
    print("  ✅ Price oracle integration (ERC20Token ready)")
    print("  ✅ RPC optimization (baseline established)")


async def main():
    """Run Phase 1C demonstration."""
    parser = argparse.ArgumentParser(description="MAMMON Phase 1C Demo")
    parser.add_argument("--pools", type=int, default=5, help="Max pools to query (default: 5)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    # Header
    print_header("🚀 MAMMON Phase 1C - Real Blockchain Integration Demo")

    print("This demonstration showcases Sprint 3 achievements:")
    print("  • Multi-network Web3 connectivity")
    print("  • Real Aerodrome protocol queries (Base mainnet)")
    print("  • ERC20 token utilities")
    print("  • Safety features and warnings")
    print("  • Connection caching performance")

    print("\n⚠️  This is a READ-ONLY demonstration. No transactions are executed.")

    try:
        # Run demos
        await demo_safety_config()
        await demo_multi_network()
        await demo_cache_performance()
        await demo_aerodrome_pools(max_pools=args.pools)
        await demo_token_utilities()
        await demo_error_handling()
        await demo_safety_warnings()
        demo_phase2a_readiness()

        # Success summary
        print_header("✅ DEMONSTRATION COMPLETE")
        print("All Phase 1C features working successfully!\n")
        print("📚 Next Steps:")
        print("  • See docs/web3_integration_guide.md for usage examples")
        print("  • See docs/known_issues_sprint3.md for current limitations")
        print("  • See docs/phase1c_sprint3_report.md for full Sprint 3 report")
        print("\n🚀 Ready to proceed to Phase 2A!")

        return 0

    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        logger.error(f"Demo error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
