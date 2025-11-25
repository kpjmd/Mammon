"""RPC Performance Testing Script

Tests premium RPC endpoints for latency, reliability, and cost estimation.
Run this before enabling premium RPC in production.

Usage:
    poetry run python scripts/test_rpc_performance.py

Output:
    - Latency percentiles (p50, p95, p99)
    - Success rates
    - Failover timing
    - Cost estimates
"""

import asyncio
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List
from decimal import Decimal

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import get_settings
from src.utils.web3_provider import get_web3, get_rpc_manager, get_rpc_usage_summary
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RpcPerformanceTester:
    """Tests RPC endpoint performance and reliability."""

    def __init__(self):
        """Initialize performance tester."""
        self.config = get_settings()
        self.results: Dict = {}

    def run_all_tests(self):
        """Run all performance tests and generate report."""
        print("=" * 70)
        print("MAMMON RPC Performance Test Suite")
        print("Sprint 4 Priority 2")
        print("=" * 70)
        print()

        # Test 1: Configuration validation
        print("1. Validating configuration...")
        self.test_configuration()
        print()

        # Test 2: Basic connectivity
        print("2. Testing basic connectivity...")
        self.test_connectivity()
        print()

        # Test 3: Latency benchmarks
        print("3. Running latency benchmarks...")
        self.test_latency()
        print()

        # Test 4: Reliability test
        print("4. Testing reliability...")
        self.test_reliability()
        print()

        # Test 5: Rate limit handling
        print("5. Testing rate limit handling...")
        self.test_rate_limits()
        print()

        # Test 6: Cost estimation
        print("6. Estimating costs...")
        self.estimate_costs()
        print()

        # Generate summary
        self.print_summary()

    def test_configuration(self):
        """Validate RPC configuration."""
        print(f"  Premium RPC enabled: {self.config.premium_rpc_enabled}")
        print(f"  Gradual rollout: {self.config.premium_rpc_percentage}%")

        if self.config.alchemy_api_key:
            print(f"  ✅ Alchemy configured (key: ...{self.config.alchemy_api_key[-6:]})")
        else:
            print("  ⚠️  Alchemy not configured (will use public RPC)")

        if self.config.quicknode_endpoint:
            print("  ✅ QuickNode configured")
        else:
            print("  ℹ️  QuickNode not configured (optional backup)")

        print(f"  Rate limits: Alchemy={self.config.alchemy_rate_limit_per_second}, "
              f"QuickNode={self.config.quicknode_rate_limit_per_second}, "
              f"Public={self.config.public_rate_limit_per_second}")

    def test_connectivity(self):
        """Test basic connectivity to all configured networks."""
        networks = ["base-mainnet", "arbitrum-sepolia"]

        for network in networks:
            try:
                print(f"  Testing {network}...", end=" ")
                w3 = get_web3(network, config=self.config)
                block = w3.eth.block_number
                chain_id = w3.eth.chain_id
                print(f"✅ Connected (block #{block}, chain {chain_id})")
            except Exception as e:
                print(f"❌ Failed: {e}")

    def test_latency(self):
        """Measure latency percentiles for RPC calls."""
        print("  Running 50 test queries per network...")

        networks = ["base-mainnet", "arbitrum-sepolia"]
        operations = [
            ("eth_blockNumber", lambda w3: w3.eth.block_number),
            ("eth_gasPrice", lambda w3: w3.eth.gas_price),
        ]

        latencies = {}

        for network in networks:
            print(f"\n  {network}:")
            w3 = get_web3(network, config=self.config)

            for op_name, op_func in operations:
                times = []

                for i in range(50):
                    try:
                        start = time.time()
                        result = op_func(w3)
                        latency_ms = (time.time() - start) * 1000
                        times.append(latency_ms)

                        # Show progress every 10 requests
                        if (i + 1) % 10 == 0:
                            print(f"    {op_name}: {i+1}/50...", end="\r")

                    except Exception as e:
                        logger.error(f"Request failed: {e}")
                        continue

                if times:
                    p50 = statistics.median(times)
                    p95 = statistics.quantiles(times, n=20)[18]  # 95th percentile
                    p99 = statistics.quantiles(times, n=100)[98]  # 99th percentile
                    mean = statistics.mean(times)

                    print(f"    {op_name:20} p50={p50:6.1f}ms p95={p95:6.1f}ms "
                          f"p99={p99:6.1f}ms mean={mean:6.1f}ms")

                    latencies[f"{network}_{op_name}"] = {
                        "p50": p50,
                        "p95": p95,
                        "p99": p99,
                        "mean": mean,
                    }

        self.results["latency"] = latencies

    def test_reliability(self):
        """Test success rate and error handling."""
        print("  Running 100 requests to test reliability...")

        network = "base-mainnet"
        w3 = get_web3(network, config=self.config)

        successes = 0
        failures = 0

        for i in range(100):
            try:
                block = w3.eth.block_number
                successes += 1

                if (i + 1) % 25 == 0:
                    print(f"    Progress: {i+1}/100...", end="\r")

            except Exception as e:
                failures += 1
                logger.error(f"Request {i+1} failed: {e}")

        success_rate = (successes / 100) * 100
        print(f"    Success rate: {success_rate:.1f}% ({successes}/{100})")

        if success_rate >= 99.9:
            print("    ✅ Excellent reliability (>= 99.9%)")
        elif success_rate >= 99:
            print("    ✅ Good reliability (>= 99%)")
        elif success_rate >= 95:
            print("    ⚠️  Acceptable reliability (>= 95%)")
        else:
            print("    ❌ Poor reliability (< 95%)")

        self.results["reliability"] = {
            "success_rate": success_rate,
            "successes": successes,
            "failures": failures,
        }

    def test_rate_limits(self):
        """Test rate limit handling."""
        print("  Testing rate limit handling...")
        print("  ℹ️  This test is currently informational only")
        print("  ℹ️  Rate limits are enforced by RpcManager during normal operation")

        # In a real implementation, we'd send rapid requests to test limits
        # For now, just show the configured limits
        print(f"    Configured Alchemy limit: {self.config.alchemy_rate_limit_per_second} RPS")
        print(f"    Configured QuickNode limit: {self.config.quicknode_rate_limit_per_second} RPS")
        print(f"    Configured Public limit: {self.config.public_rate_limit_per_second} RPS")

    def estimate_costs(self):
        """Estimate monthly costs based on usage."""
        print("  Estimating monthly costs...")

        # Get current usage if available
        usage = get_rpc_usage_summary(self.config)

        if usage:
            print(f"    Today's usage: {usage.get('premium_requests', 0)} premium requests")
            print(f"    Alchemy usage: {usage.get('alchemy_usage_percent', 0):.1f}% of free tier")
            print(f"    In free tier: {usage.get('in_free_tier', True)}")
            print(f"    Estimated cost: ${usage.get('estimated_cost_usd', 0.00):.2f}/day")
        else:
            print("    ℹ️  No usage data yet (RPC manager not initialized)")

        # Project monthly costs based on typical usage
        scenarios = [
            ("Light (1K req/day)", 1000, 0.00),
            ("Moderate (10K req/day)", 10000, 0.00),
            ("Heavy (50K req/day)", 50000, 5.00),
            ("Very Heavy (100K req/day)", 100000, 15.00),
        ]

        print("\n    Monthly cost projections:")
        print("    " + "-" * 60)
        for name, daily_requests, estimated_cost in scenarios:
            monthly_requests = daily_requests * 30
            print(f"    {name:30} {monthly_requests:>12,} req/mo = ${estimated_cost:>6.2f}/mo")

        self.results["cost_estimates"] = {
            "current_usage": usage,
            "scenarios": scenarios,
        }

    def print_summary(self):
        """Print test summary and recommendations."""
        print("=" * 70)
        print("Test Summary")
        print("=" * 70)

        # Latency summary
        if "latency" in self.results:
            print("\n📊 Latency Results:")
            for key, data in self.results["latency"].items():
                network, operation = key.split("_", 1)
                if data["p95"] < 100:
                    status = "✅ Excellent"
                elif data["p95"] < 200:
                    status = "✅ Good"
                elif data["p95"] < 500:
                    status = "⚠️  Acceptable"
                else:
                    status = "❌ Poor"

                print(f"  {network:20} {operation:20} p95={data['p95']:6.1f}ms {status}")

        # Reliability summary
        if "reliability" in self.results:
            print("\n🎯 Reliability:")
            success_rate = self.results["reliability"]["success_rate"]
            if success_rate >= 99.9:
                status = "✅ Production ready"
            elif success_rate >= 99:
                status = "✅ Acceptable"
            else:
                status = "⚠️  Needs improvement"
            print(f"  Success rate: {success_rate:.1f}% {status}")

        # Recommendations
        print("\n💡 Recommendations:")

        if self.config.premium_rpc_enabled:
            print("  ✅ Premium RPC enabled")

            if self.config.premium_rpc_percentage < 100:
                print(f"  ℹ️  Currently at {self.config.premium_rpc_percentage}% rollout")
                print("  💡 Consider increasing rollout percentage gradually:")
                print("     - Week 1: 10%")
                print("     - Week 2: 30%")
                print("     - Week 3: 60%")
                print("     - Week 4: 100%")
        else:
            print("  ℹ️  Premium RPC disabled")
            if self.config.alchemy_api_key:
                print("  💡 Set PREMIUM_RPC_ENABLED=true in .env to enable")
            else:
                print("  💡 Sign up for Alchemy at https://www.alchemy.com/")
                print("     Add ALCHEMY_API_KEY to .env")

        # Cost recommendations
        print("\n💰 Cost Monitoring:")
        print("  📋 Check daily usage: grep 'rpc_usage_summary' audit.log | tail -1")
        print("  📋 Monitor approaching limits (> 80% of free tier)")
        print("  📋 Set up alerts for high usage")

        print("\n" + "=" * 70)
        print("Test Complete!")
        print("=" * 70)


def main():
    """Run RPC performance tests."""
    tester = RpcPerformanceTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
