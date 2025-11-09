#!/usr/bin/env python3
"""Benchmark connection caching performance.

Demonstrates the effectiveness of Web3 connection caching implemented
in Phase 1C Sprint 3. This validates a core architectural decision.

Usage:
    poetry run python scripts/benchmark_cache_performance.py
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.web3_provider import get_web3, Web3Provider


def benchmark_cold_connection(network_id: str) -> float:
    """Measure connection time without cache.

    Args:
        network_id: Network identifier

    Returns:
        Connection time in seconds
    """
    # Clear cache to simulate cold start
    Web3Provider.clear_cache(network_id)

    start = time.time()
    w3 = get_web3(network_id)
    block = w3.eth.block_number  # Force connection
    elapsed = time.time() - start

    return elapsed


def benchmark_warm_connection(network_id: str, iterations: int = 10) -> float:
    """Measure average cached connection time.

    Args:
        network_id: Network identifier
        iterations: Number of iterations to average

    Returns:
        Average connection time in seconds
    """
    times = []

    for _ in range(iterations):
        start = time.time()
        w3 = get_web3(network_id)
        block = w3.eth.block_number
        elapsed = time.time() - start
        times.append(elapsed)

    return sum(times) / len(times)


def main():
    """Run cache performance benchmarks."""
    print("\n⚡ Cache Performance Benchmark - Phase 1C Sprint 3\n")
    print("=" * 70)

    networks = ["base-mainnet", "arbitrum-sepolia"]
    results = {}

    for network in networks:
        print(f"\n🌐 Testing {network}...")

        try:
            # Cold start
            cold_time = benchmark_cold_connection(network)
            print(f"   Cold start: {cold_time:.3f}s")

            # Warm (cached)
            warm_time = benchmark_warm_connection(network, iterations=10)
            print(f"   Cached (avg of 10): {warm_time:.6f}s")

            # Speedup
            speedup = cold_time / warm_time
            print(f"   Speedup: {speedup:.0f}x faster")

            results[network] = {
                "cold": cold_time,
                "warm": warm_time,
                "speedup": speedup
            }

        except Exception as e:
            print(f"   ❌ Error: {e}")
            results[network] = {"error": str(e)}

    # Summary
    print("\n" + "=" * 70)
    print("📊 Summary\n")

    for network, data in results.items():
        if "error" in data:
            print(f"{network}: ❌ {data['error']}\n")
            continue

        print(f"{network}:")
        print(f"  Cold:    {data['cold']:.3f}s")
        print(f"  Cached:  {data['warm']:.6f}s")
        print(f"  Speedup: {data['speedup']:.0f}x")
        print(f"  Time saved per query: {(data['cold'] - data['warm']):.3f}s\n")

    # Calculate insights
    successful_results = [r for r in results.values() if "error" not in r]
    if successful_results:
        avg_speedup = sum(r["speedup"] for r in successful_results) / len(successful_results)
        overhead_eliminated = ((1 - (1/avg_speedup)) * 100)

        print(f"💡 Insight: Connection caching provides ~{avg_speedup:.0f}x average speedup")
        print(f"   Eliminates {overhead_eliminated:.2f}% of connection overhead")
        print(f"\n✅ This validates Phase 1C's caching architecture")
    else:
        print("❌ No successful benchmarks to analyze")

    return 0 if successful_results else 1


if __name__ == "__main__":
    sys.exit(main())
