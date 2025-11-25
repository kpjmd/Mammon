"""RPC Usage Monitoring Script

Monitors premium RPC usage during rollout by analyzing audit logs.
Run this periodically during the 24-48 hour monitoring period.

Usage:
    poetry run python scripts/monitor_rpc_usage.py

    # With custom audit log location
    poetry run python scripts/monitor_rpc_usage.py --audit-log /path/to/audit.log

Output:
    - Current usage statistics
    - Cost projections
    - Health status
    - Recommendations for rollout adjustment
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class RpcUsageMonitor:
    """Monitors RPC usage from audit logs."""

    def __init__(self, audit_log_path: str = "audit.log"):
        """Initialize monitor.

        Args:
            audit_log_path: Path to audit log file
        """
        self.audit_log_path = Path(audit_log_path)
        self.events: List[Dict] = []
        self.usage_summaries: List[Dict] = []
        self.rpc_requests: List[Dict] = []
        self.circuit_breaker_events: List[Dict] = []
        self.endpoint_failures: List[Dict] = []

    def load_audit_log(self):
        """Load and parse audit log file."""
        if not self.audit_log_path.exists():
            print(f"⚠️  Audit log not found: {self.audit_log_path}")
            print("ℹ️  No RPC usage data available yet.")
            print("ℹ️  Usage data will be logged once RPC requests are made.")
            return

        print(f"📖 Loading audit log: {self.audit_log_path}")

        with open(self.audit_log_path, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    self.events.append(event)

                    # Categorize events
                    event_type = event.get('event_type')
                    if event_type == 'rpc_usage_summary':
                        self.usage_summaries.append(event)
                    elif event_type == 'rpc_request':
                        self.rpc_requests.append(event)
                    elif event_type == 'rpc_circuit_breaker_opened':
                        self.circuit_breaker_events.append(event)
                    elif event_type == 'rpc_endpoint_failure':
                        self.endpoint_failures.append(event)

                except json.JSONDecodeError:
                    continue  # Skip non-JSON lines

        print(f"✅ Loaded {len(self.events)} audit events")
        print(f"   - {len(self.rpc_requests)} RPC requests")
        print(f"   - {len(self.usage_summaries)} usage summaries")
        print(f"   - {len(self.circuit_breaker_events)} circuit breaker events")
        print(f"   - {len(self.endpoint_failures)} endpoint failures")
        print()

    def get_latest_usage_summary(self) -> Optional[Dict]:
        """Get the most recent usage summary.

        Returns:
            Latest usage summary dict or None
        """
        if not self.usage_summaries:
            return None

        return self.usage_summaries[-1]

    def analyze_request_distribution(self) -> Dict:
        """Analyze distribution of requests across endpoints.

        Returns:
            Dict with request counts per endpoint
        """
        distribution = defaultdict(int)

        for request in self.rpc_requests:
            metadata = request.get('metadata', {})
            endpoint = metadata.get('endpoint', 'unknown')
            distribution[endpoint] += 1

        return dict(distribution)

    def calculate_success_rate(self) -> float:
        """Calculate overall success rate.

        Returns:
            Success rate as percentage (0-100)
        """
        if not self.rpc_requests:
            return 100.0

        successes = sum(
            1 for req in self.rpc_requests
            if req.get('metadata', {}).get('success', False)
        )

        return (successes / len(self.rpc_requests)) * 100

    def get_average_latency(self) -> Dict[str, float]:
        """Calculate average latency per endpoint.

        Returns:
            Dict mapping endpoint to average latency in ms
        """
        latencies = defaultdict(list)

        for request in self.rpc_requests:
            metadata = request.get('metadata', {})
            endpoint = metadata.get('endpoint', 'unknown')
            latency = metadata.get('latency_ms', 0)

            if latency > 0:
                latencies[endpoint].append(latency)

        # Calculate averages
        averages = {}
        for endpoint, values in latencies.items():
            if values:
                averages[endpoint] = sum(values) / len(values)

        return averages

    def check_health_status(self) -> Dict:
        """Check overall health status.

        Returns:
            Dict with health indicators
        """
        latest_summary = self.get_latest_usage_summary()

        if not latest_summary:
            return {
                "status": "unknown",
                "message": "No usage data available yet"
            }

        metadata = latest_summary.get('metadata', {})

        # Check for approaching limits
        approaching_limit = metadata.get('approaching_limit', False)
        alchemy_usage_pct = metadata.get('alchemy_usage_percent', 0)

        # Check success rate
        success_rate = self.calculate_success_rate()

        # Check for circuit breaker events (recent)
        recent_breakers = [
            event for event in self.circuit_breaker_events
            if self._is_recent(event, hours=24)
        ]

        # Determine status
        if len(recent_breakers) > 0:
            status = "warning"
            message = f"{len(recent_breakers)} circuit breaker events in last 24h"
        elif approaching_limit:
            status = "warning"
            message = f"Approaching rate limit ({alchemy_usage_pct:.1f}% of free tier)"
        elif success_rate < 99.0:
            status = "warning"
            message = f"Success rate below 99% ({success_rate:.1f}%)"
        elif success_rate >= 99.9:
            status = "excellent"
            message = "All systems healthy"
        else:
            status = "good"
            message = "Operating normally"

        return {
            "status": status,
            "message": message,
            "success_rate": success_rate,
            "circuit_breakers": len(recent_breakers),
            "approaching_limit": approaching_limit,
        }

    def _is_recent(self, event: Dict, hours: int) -> bool:
        """Check if event is within last N hours.

        Args:
            event: Event dict
            hours: Number of hours to consider recent

        Returns:
            True if event is recent
        """
        timestamp_str = event.get('timestamp', '')
        if not timestamp_str:
            return False

        try:
            event_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            age = now - event_time

            return age < timedelta(hours=hours)

        except Exception:
            return False

    def generate_report(self):
        """Generate comprehensive monitoring report."""
        print("=" * 70)
        print("RPC USAGE MONITORING REPORT")
        print("=" * 70)
        print()

        # 1. Health Status
        print("🏥 HEALTH STATUS")
        print("-" * 70)

        health = self.check_health_status()
        status = health['status']

        if status == 'excellent':
            icon = "✅"
        elif status == 'good':
            icon = "✅"
        elif status == 'warning':
            icon = "⚠️"
        else:
            icon = "❓"

        print(f"{icon} Status: {status.upper()}")
        print(f"   {health['message']}")
        print()

        # 2. Latest Usage Summary
        print("📊 CURRENT USAGE")
        print("-" * 70)

        latest = self.get_latest_usage_summary()

        if latest:
            metadata = latest.get('metadata', {})

            print(f"Premium requests: {metadata.get('premium_requests', 0):,}")
            print(f"Backup requests:  {metadata.get('backup_requests', 0):,}")
            print(f"Public requests:  {metadata.get('public_requests', 0):,}")
            print(f"Total requests:   {metadata.get('total_requests', 0):,}")
            print()

            print(f"Alchemy usage:    {metadata.get('alchemy_usage_percent', 0):.2f}% of free tier")
            print(f"QuickNode usage:  {metadata.get('quicknode_usage_percent', 0):.2f}% of free tier")
            print()

            approaching = metadata.get('approaching_limit', False)
            in_free_tier = metadata.get('in_free_tier', True)

            if approaching:
                print("⚠️  WARNING: Approaching rate limit (>80% of free tier)")
            elif in_free_tier:
                print("✅ Within free tier limits")

            estimated_cost = metadata.get('estimated_cost_usd', 0.00)
            print(f"💰 Estimated cost: ${estimated_cost:.2f}/day")

        else:
            print("ℹ️  No usage data available yet")

        print()

        # 3. Request Distribution
        print("📈 REQUEST DISTRIBUTION")
        print("-" * 70)

        distribution = self.analyze_request_distribution()

        if distribution:
            total = sum(distribution.values())

            for endpoint, count in sorted(distribution.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total) * 100
                bar = "█" * int(percentage / 2)
                print(f"{endpoint:15} {count:6,} requests ({percentage:5.1f}%) {bar}")

        else:
            print("ℹ️  No request data available yet")

        print()

        # 4. Performance Metrics
        print("⚡ PERFORMANCE METRICS")
        print("-" * 70)

        success_rate = self.calculate_success_rate()
        print(f"Success rate: {success_rate:.2f}%")

        if success_rate >= 99.9:
            print("   ✅ Excellent (>= 99.9%)")
        elif success_rate >= 99.0:
            print("   ✅ Good (>= 99%)")
        elif success_rate >= 95.0:
            print("   ⚠️  Acceptable (>= 95%)")
        else:
            print("   ❌ Poor (< 95%)")

        print()

        latencies = self.get_average_latency()

        if latencies:
            print("Average latency:")
            for endpoint, avg_latency in sorted(latencies.items()):
                if avg_latency < 100:
                    status_icon = "✅"
                    status_text = "Excellent"
                elif avg_latency < 200:
                    status_icon = "✅"
                    status_text = "Good"
                elif avg_latency < 500:
                    status_icon = "⚠️"
                    status_text = "Acceptable"
                else:
                    status_icon = "❌"
                    status_text = "Poor"

                print(f"  {endpoint:15} {avg_latency:6.1f}ms {status_icon} {status_text}")
        else:
            print("  ℹ️  No latency data available yet")

        print()

        # 5. Issues & Alerts
        print("🚨 ISSUES & ALERTS")
        print("-" * 70)

        recent_failures = [
            event for event in self.endpoint_failures
            if self._is_recent(event, hours=24)
        ]

        recent_breakers = [
            event for event in self.circuit_breaker_events
            if self._is_recent(event, hours=24)
        ]

        if not recent_failures and not recent_breakers:
            print("✅ No issues detected in last 24 hours")
        else:
            if recent_breakers:
                print(f"⚠️  {len(recent_breakers)} circuit breaker event(s) in last 24h")
                for event in recent_breakers[-3:]:  # Show last 3
                    metadata = event.get('metadata', {})
                    print(f"   - {metadata.get('endpoint', 'unknown')} "
                          f"({metadata.get('failure_count', 0)} failures)")

            if recent_failures:
                print(f"⚠️  {len(recent_failures)} endpoint failure(s) in last 24h")

                # Group by endpoint
                failure_counts = defaultdict(int)
                for event in recent_failures:
                    endpoint = event.get('metadata', {}).get('endpoint', 'unknown')
                    failure_counts[endpoint] += 1

                for endpoint, count in failure_counts.items():
                    print(f"   - {endpoint}: {count} failures")

        print()

        # 6. Recommendations
        print("💡 RECOMMENDATIONS")
        print("-" * 70)

        self._print_recommendations(health, latest)

        print()
        print("=" * 70)

    def _print_recommendations(self, health: Dict, latest_summary: Optional[Dict]):
        """Print recommendations based on current status.

        Args:
            health: Health status dict
            latest_summary: Latest usage summary
        """
        status = health['status']
        success_rate = health.get('success_rate', 100.0)

        if status == 'excellent' and success_rate >= 99.9:
            print("✅ System performing excellently!")
            print()
            print("Next steps:")
            print("  1. Continue monitoring for 24-48 hours")
            print("  2. Consider increasing rollout percentage:")
            print("     PREMIUM_RPC_PERCENTAGE=60  # Increase from 30% to 60%")
            print("  3. Monitor costs to ensure staying in free tier")

        elif status == 'good':
            print("✅ System operating normally")
            print()
            print("Next steps:")
            print("  1. Continue monitoring")
            print("  2. Can proceed with gradual rollout increase after 24-48h")

        elif status == 'warning':
            print("⚠️  Issues detected - investigate before increasing rollout")
            print()

            if health['circuit_breakers'] > 0:
                print("Action required:")
                print("  1. Check audit log for circuit breaker details:")
                print("     grep 'rpc_circuit_breaker_opened' audit.log")
                print("  2. Verify RPC endpoints are accessible")
                print("  3. Consider reducing rollout percentage temporarily")

            if health['approaching_limit']:
                print("Action required:")
                print("  1. Review usage patterns")
                print("  2. Consider upgrading to paid tier if sustained high usage")
                print("  3. Or reduce rollout percentage to stay in free tier")

            if success_rate < 99.0:
                print("Action required:")
                print("  1. Investigate failed requests in audit log")
                print("  2. Check network connectivity")
                print("  3. Verify API keys are valid")

        else:
            print("ℹ️  Insufficient data for recommendations")
            print("   Make some RPC requests to generate usage data")

        print()
        print("Monitoring commands:")
        print("  # Re-run this script anytime")
        print("  poetry run python scripts/monitor_rpc_usage.py")
        print()
        print("  # Run performance tests")
        print("  poetry run python scripts/test_rpc_performance.py")
        print()
        print("  # Check latest usage summary")
        print("  grep 'rpc_usage_summary' audit.log | tail -1 | jq")


def main():
    """Run RPC usage monitoring."""
    parser = argparse.ArgumentParser(
        description="Monitor premium RPC usage during rollout"
    )
    parser.add_argument(
        "--audit-log",
        default="audit.log",
        help="Path to audit log file (default: audit.log)"
    )

    args = parser.parse_args()

    monitor = RpcUsageMonitor(args.audit_log)
    monitor.load_audit_log()
    monitor.generate_report()


if __name__ == "__main__":
    main()
