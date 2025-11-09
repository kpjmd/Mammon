#!/usr/bin/env python3
"""Extended performance benchmarks for Phase 1C Sprint 3.

Benchmarks:
1. Pool query latency breakdown (where time is spent)
2. Network comparison (Base vs Arbitrum)
3. Token query performance
4. Memory usage

Usage:
    poetry run python scripts/benchmark_extended.py
    poetry run python scripts/benchmark_extended.py --full  # All benchmarks (may hit rate limits)
"""

import asyncio
import sys
import time
import argparse
import os
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

# Optional: psutil for memory benchmarks
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from src.utils.web3_provider import get_web3, Web3Provider
from src.protocols.aerodrome import AerodromeProtocol
from src.tokens import ERC20Token
from src.utils.contracts import ContractHelper
from src.utils.aerodrome_abis import AERODROME_FACTORY_ABI, AERODROME_POOL_ABI


def print_section(title: str):
    """Print formatted section."""
    print(f"\n{'=' * 70}")
    print(f"{title}")
    print(f"{'=' * 70}\n")


async def benchmark_latency_breakdown():
    """Break down pool query latency into components."""
    print_section("📊 BENCHMARK 1: Latency Breakdown")

    w3 = get_web3("base-mainnet")
    factory_address = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
    factory = ContractHelper.get_contract(w3, factory_address, AERODROME_FACTORY_ABI)

    # 1. Factory call
    start = time.time()
    pool_address = factory.functions.allPools(0).call()
    factory_time = time.time() - start

    # 2. Pool metadata
    pool = ContractHelper.get_contract(w3, pool_address, AERODROME_POOL_ABI)
    start = time.time()
    metadata = pool.functions.metadata().call()
    metadata_time = time.time() - start

    # 3. Token symbols (2 calls)
    token0_addr = metadata[5]
    token1_addr = metadata[6]

    start = time.time()
    token0 = ContractHelper.get_erc20_contract(w3, token0_addr)
    symbol0 = token0.functions.symbol().call()
    token0_time = time.time() - start

    start = time.time()
    token1 = ContractHelper.get_erc20_contract(w3, token1_addr)
    symbol1 = token1.functions.symbol().call()
    token1_time = time.time() - start

    # 4. Fee query
    start = time.time()
    fee = factory.functions.getFee(pool_address, metadata[4]).call()
    fee_time = time.time() - start

    # 5. TVL calculation (local)
    start = time.time()
    from decimal import Decimal
    dec0, dec1, res0, res1 = metadata[0], metadata[1], metadata[2], metadata[3]
    amount0 = Decimal(res0) / Decimal(10**dec0)
    amount1 = Decimal(res1) / Decimal(10**dec1)
    tvl = amount0 + amount1
    calc_time = time.time() - start

    total_time = factory_time + metadata_time + token0_time + token1_time + fee_time + calc_time

    print(f"Per-pool query breakdown (Base mainnet):")
    print(f"  1. Factory.allPools(i):         {factory_time*1000:>7.2f} ms ({factory_time/total_time*100:>5.1f}%)")
    print(f"  2. Pool.metadata():             {metadata_time*1000:>7.2f} ms ({metadata_time/total_time*100:>5.1f}%)")
    print(f"  3. Token0.symbol():             {token0_time*1000:>7.2f} ms ({token0_time/total_time*100:>5.1f}%)")
    print(f"  4. Token1.symbol():             {token1_time*1000:>7.2f} ms ({token1_time/total_time*100:>5.1f}%)")
    print(f"  5. Factory.getFee():            {fee_time*1000:>7.2f} ms ({fee_time/total_time*100:>5.1f}%)")
    print(f"  6. TVL calculation (local):     {calc_time*1000:>7.2f} ms ({calc_time/total_time*100:>5.1f}%)")
    print(f"  {'─' * 60}")
    print(f"  Total per pool:                 {total_time*1000:>7.2f} ms")

    network_pct = (factory_time + metadata_time + token0_time + token1_time + fee_time) / total_time * 100
    print(f"\n💡 Insight: {network_pct:.1f}% network I/O, {100-network_pct:.1f}% computation")
    print(f"   RPC calls per pool: 5 calls")
    print(f"   Average time per RPC call: {(total_time-calc_time)/5*1000:.2f} ms")


async def benchmark_pool_query_timing(protocol: AerodromeProtocol, counts: List[int]):
    """Benchmark pool queries at different scales."""
    print_section("📊 BENCHMARK 2: Pool Query Timing")

    for count in counts:
        print(f"Querying {count} pools...")

        try:
            start = time.time()
            pools = await protocol._get_real_pools_from_mainnet(max_pools=count)
            elapsed = time.time() - start

            avg_per_pool = elapsed / len(pools) if pools else 0

            print(f"  ✅ {len(pools)} pools in {elapsed:.2f}s (avg {avg_per_pool:.3f}s/pool)")

            # Add delay to avoid rate limiting
            if count < max(counts):
                print(f"  ⏱  Waiting 10s to avoid rate limits...")
                await asyncio.sleep(10)

        except Exception as e:
            print(f"  ❌ Failed: {e}")


async def benchmark_network_comparison():
    """Compare Base mainnet vs Arbitrum Sepolia performance."""
    print_section("📊 BENCHMARK 3: Network Comparison")

    # Note: Arbitrum Sepolia doesn't have Aerodrome, so just test connections
    print("Connection speed comparison:")

    for network in ["base-mainnet", "arbitrum-sepolia"]:
        Web3Provider.clear_cache(network)

        start = time.time()
        w3 = get_web3(network)
        block = w3.eth.block_number
        elapsed = time.time() - start

        print(f"  {network:20s}: {elapsed:.3f}s")

    print(f"\n💡 Insight: Network latency varies by RPC endpoint and traffic")


async def benchmark_token_queries():
    """Benchmark ERC20 token query performance."""
    print_section("📊 BENCHMARK 4: Token Query Performance")

    usdc_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

    # Cold query
    token = ERC20Token("base-mainnet", usdc_address)
    token._symbol = None  # Clear cache
    token._decimals = None
    token._name = None

    start = time.time()
    symbol = token.get_symbol()
    cold_time = time.time() - start

    # Warm query (cached)
    start = time.time()
    symbol = token.get_symbol()
    warm_time = time.time() - start

    print(f"USDC metadata query (symbol):")
    print(f"  Cold (first query):  {cold_time*1000:.2f} ms")
    print(f"  Warm (cached):       {warm_time*1000:.6f} ms")
    print(f"  Speedup:             {cold_time/warm_time:.0f}x")

    # Query all metadata
    token._symbol = None
    token._decimals = None
    token._name = None

    start = time.time()
    info = token.get_info()
    full_time = time.time() - start

    print(f"\nFull metadata query (symbol, decimals, name):")
    print(f"  Cold (all 3 fields): {full_time*1000:.2f} ms")
    print(f"  RPC calls:           3")
    print(f"  Avg per call:        {full_time/3*1000:.2f} ms")

    print(f"\n💡 Insight: Token metadata caching eliminates redundant RPC calls")


def benchmark_memory_usage():
    """Measure memory usage."""
    print_section("📊 BENCHMARK 5: Memory Usage")

    if not PSUTIL_AVAILABLE:
        print("⚠️  psutil not installed - skipping memory benchmark")
        print("   Install with: pip install psutil")
        return

    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / 1024 / 1024

    print(f"Current process memory: {mem_mb:.1f} MB")
    print(f"\n💡 Insight: Baseline memory footprint is minimal")
    print(f"   Suitable for long-running agent processes")


async def main():
    """Run extended benchmarks."""
    parser = argparse.ArgumentParser(description="Extended performance benchmarks")
    parser.add_argument("--full", action="store_true", help="Run all benchmarks (may hit rate limits)")
    args = parser.parse_args()

    print("⚡ Phase 1C Extended Performance Benchmarks")
    print("⚠️  Note: Some benchmarks may hit rate limits on public Base RPC")

    try:
        # Always run these
        await benchmark_latency_breakdown()
        await benchmark_network_comparison()
        await benchmark_token_queries()
        benchmark_memory_usage()

        # Pool query timing (potentially rate limited)
        if args.full:
            print_section("📊 BENCHMARK 6: Pool Query Timing (Full)")
            protocol = AerodromeProtocol({
                "network": "base-mainnet",
                "dry_run_mode": False
            })
            await benchmark_pool_query_timing(protocol, [10, 25])
        else:
            print_section("📊 BENCHMARK: Pool Query Timing (SKIPPED)")
            print("Run with --full flag to include pool query benchmarks")
            print("⚠️  Warning: May hit rate limits on public RPC")

        print("\n" + "=" * 70)
        print("✅ Benchmarks complete!")
        print("=" * 70)

        return 0

    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
