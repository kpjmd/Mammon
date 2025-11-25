#!/usr/bin/env python3
"""Display MAMMON performance metrics dashboard.

This script shows MAMMON's competitive advantages:
- Prediction accuracy (proves the moat)
- Win rate (demonstrates effectiveness)
- ROI attribution (explains profitability)
- 4-gate system validation (shows safety)

Critical for x402 marketplace credibility.

Usage:
    poetry run python scripts/show_performance.py
    poetry run python scripts/show_performance.py --days 7
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import argparse
from decimal import Decimal
from dotenv import load_dotenv

from src.data.position_tracker import PositionTracker
from src.data.performance_tracker import PerformanceTracker
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


def print_header(title: str):
    """Print formatted header."""
    width = 80
    print("\n" + "═" * width)
    print(title.center(width))
    print("═" * width + "\n")


def print_section(title: str):
    """Print formatted section."""
    print(f"\n{title}")
    print("─" * 80)


def format_decimal(value: Decimal, decimals: int = 2) -> str:
    """Format decimal for display."""
    return f"{float(value):.{decimals}f}"


def format_percentage(value: float) -> str:
    """Format percentage for display."""
    return f"{value:.1f}%"


def format_usd(value: Decimal) -> str:
    """Format USD amount for display."""
    return f"${float(value):.2f}"


async def show_performance_dashboard(days: int = 30):
    """Display comprehensive performance dashboard.

    Args:
        days: Number of days to analyze
    """
    print_header("MAMMON PERFORMANCE DASHBOARD")
    print(f"Analysis Period: Last {days} days\n")

    # Initialize trackers
    position_tracker = PositionTracker()
    performance_tracker = PerformanceTracker()

    try:
        # ================================================================
        # PREDICTION ACCURACY - Competitive Moat!
        # ================================================================
        print_section("🎯 PREDICTION ACCURACY (Competitive Moat)")

        prediction_metrics = await position_tracker.get_prediction_accuracy(days=days)
        roi_metrics = await performance_tracker.calculate_roi(days=days)

        accuracy = prediction_metrics.get("apy_prediction_accuracy", 0.0)
        positions_tracked = prediction_metrics.get("positions_tracked", 0)
        avg_error = prediction_metrics.get("avg_prediction_error", 0.0)

        predicted_roi = roi_metrics.get("predicted_30d_roi", Decimal("0"))
        actual_roi = roi_metrics.get("actual_30d_roi", Decimal("0"))
        roi_accuracy = roi_metrics.get("prediction_accuracy", 0.0)

        print(f"├─ APY Prediction Accuracy: {format_percentage(accuracy)}")
        print(f"├─ Average Prediction Error: ±{avg_error:.2f}%")
        print(f"├─ Positions Tracked: {positions_tracked}")
        print(f"├─ Predicted {days}d ROI: {format_decimal(predicted_roi, 2)}%")
        print(f"├─ Actual {days}d ROI: {format_decimal(actual_roi, 2)}%")
        print(f"└─ ROI Prediction Accuracy: {format_percentage(roi_accuracy)}")

        # Competitive advantage indicator
        if accuracy >= 90:
            print(f"\n   ✨ EXCELLENT - Industry-leading prediction accuracy!")
        elif accuracy >= 80:
            print(f"\n   ✅ GOOD - Strong competitive advantage")
        elif accuracy >= 70:
            print(f"\n   ⚠️  FAIR - Needs improvement for x402 credibility")
        else:
            print(f"\n   ❌ POOR - Insufficient data or model needs tuning")

        # ================================================================
        # WIN RATE ANALYSIS
        # ================================================================
        print_section("📊 WIN RATE ANALYSIS")

        win_rate_metrics = await performance_tracker.calculate_win_rate(days=days)

        profitable = win_rate_metrics.get("profitable_rebalances", 0)
        total = win_rate_metrics.get("total_rebalances", 0)
        win_rate = win_rate_metrics.get("win_rate_percentage", 0.0)
        avg_profit = win_rate_metrics.get("average_profit_per_win", Decimal("0"))
        avg_loss = win_rate_metrics.get("average_loss_per_loss", Decimal("0"))

        print(f"├─ Profitable Rebalances: {profitable}/{total} ({format_percentage(win_rate)})")
        print(f"├─ Average Profit per Win: {format_usd(avg_profit)}")
        print(f"├─ Average Loss per Loss: {format_usd(avg_loss)}")

        if total > 0:
            net_per_trade = (avg_profit * profitable - abs(avg_loss) * (total - profitable)) / total
            print(f"└─ Net Profit per Trade: {format_usd(Decimal(str(net_per_trade)))}")

            if win_rate >= 80:
                print(f"\n   ✨ EXCELLENT - Highly profitable strategy!")
            elif win_rate >= 70:
                print(f"\n   ✅ GOOD - Solid profitability")
            elif win_rate >= 60:
                print(f"\n   ⚠️  FAIR - Needs optimization")
            else:
                print(f"\n   ❌ POOR - Strategy needs rework")
        else:
            print(f"\n   ℹ️  No rebalances executed yet")

        # ================================================================
        # OVERALL ROI & GAS EFFICIENCY
        # ================================================================
        print_section("💰 ROI & GAS EFFICIENCY")

        metrics = await performance_tracker.get_metrics(days=days)

        print(f"├─ Total Profit: {format_usd(metrics.total_profit_usd)}")
        print(f"├─ Total Gas Spent: {format_usd(metrics.total_gas_spent_usd)}")
        print(f"├─ Net Profit: {format_usd(metrics.net_profit_usd)}")
        print(f"├─ ROI: {format_decimal(metrics.roi_percentage, 2)}%")
        print(f"├─ Average Gas per Rebalance: {format_usd(metrics.average_gas_per_rebalance)}")
        print(f"└─ Gas to Profit Ratio: {metrics.gas_to_profit_ratio:.1%}")

        if metrics.gas_to_profit_ratio < 0.1:
            print(f"\n   ✨ EXCELLENT - Highly gas-efficient!")
        elif metrics.gas_to_profit_ratio < 0.2:
            print(f"\n   ✅ GOOD - Acceptable gas costs")
        elif metrics.gas_to_profit_ratio < 0.3:
            print(f"\n   ⚠️  FAIR - Gas costs eating into profits")
        else:
            print(f"\n   ❌ POOR - Gas costs too high")

        # ================================================================
        # PROFITABILITY ATTRIBUTION
        # ================================================================
        print_section("📈 PROFITABILITY ATTRIBUTION")

        attribution = await performance_tracker.get_profitability_attribution(days=days)

        # By Protocol
        by_protocol = attribution.get("by_protocol", {})
        if by_protocol:
            print("\nBy Protocol:")
            for protocol, profit in sorted(by_protocol.items(), key=lambda x: x[1], reverse=True):
                print(f"  ├─ {protocol}: {format_usd(profit)}")

        # By Token
        by_token = attribution.get("by_token", {})
        if by_token:
            print("\nBy Token:")
            for token, profit in sorted(by_token.items(), key=lambda x: x[1], reverse=True):
                print(f"  ├─ {token}: {format_usd(profit)}")

        print(f"\nBest Protocol: {metrics.best_protocol}")
        print(f"Most Profitable Token: {metrics.most_profitable_token}")

        # ================================================================
        # 4-GATE SYSTEM VALIDATION
        # ================================================================
        print_section("🛡️  4-GATE PROFITABILITY SYSTEM")

        gate_metrics = await performance_tracker.validate_gate_system(days=days)

        total_decisions = gate_metrics.get("total_decisions", 0)
        approved = gate_metrics.get("approved", 0)
        rejected = gate_metrics.get("rejected", 0)
        gate_1 = gate_metrics.get("gate_1_blocks", 0)
        gate_2 = gate_metrics.get("gate_2_blocks", 0)
        gate_3 = gate_metrics.get("gate_3_blocks", 0)
        gate_4 = gate_metrics.get("gate_4_blocks", 0)
        false_positives = gate_metrics.get("false_positives_avoided", 0)
        roi_impact = gate_metrics.get("roi_impact_usd", Decimal("0"))

        print(f"├─ Total Decisions: {total_decisions}")
        print(f"├─ Approved: {approved}")
        print(f"├─ Blocked by Gates: {rejected}")
        print(f"│  ├─ Gate 1 (Min Annual Gain): {gate_1}")
        print(f"│  ├─ Gate 2 (Break-Even Days): {gate_2}")
        print(f"│  ├─ Gate 3 (Max Cost %): {gate_3}")
        print(f"│  └─ Gate 4 (Gas Efficiency): {gate_4}")
        print(f"├─ False Positives Avoided: {false_positives}")
        print(f"└─ ROI Impact from Gates: {format_usd(roi_impact)}")

        if total_decisions > 0:
            block_rate = rejected / total_decisions * 100
            if block_rate < 5:
                print(f"\n   ℹ️  Gates blocking {block_rate:.1f}% - system is permissive")
            elif block_rate < 15:
                print(f"\n   ✅ Gates blocking {block_rate:.1f}% - good balance")
            elif block_rate < 30:
                print(f"\n   ⚠️  Gates blocking {block_rate:.1f}% - may be too conservative")
            else:
                print(f"\n   ❌ Gates blocking {block_rate:.1f}% - too restrictive!")

        # ================================================================
        # CURRENT POSITIONS
        # ================================================================
        print_section("💼 CURRENT POSITIONS")

        # Get wallet address from config
        import os
        from src.utils.config import load_config

        config = load_config()
        wallet_address = config.get("wallet_address", "")

        if wallet_address:
            portfolio = await position_tracker.get_portfolio_summary(wallet_address)

            total_value = portfolio.get("total_value_usd", Decimal("0"))
            position_count = portfolio.get("position_count", 0)
            avg_apy = portfolio.get("avg_apy", Decimal("0"))
            by_protocol = portfolio.get("positions_by_protocol", {})

            print(f"├─ Total Value: {format_usd(total_value)}")
            print(f"├─ Active Positions: {position_count}")
            print(f"└─ Weighted Average APY: {format_decimal(avg_apy, 2)}%")

            if by_protocol:
                print("\nPositions by Protocol:")
                for protocol, value in sorted(by_protocol.items(), key=lambda x: x[1], reverse=True):
                    pct = (value / total_value * 100) if total_value > 0 else 0
                    print(f"  ├─ {protocol}: {format_usd(value)} ({pct:.1f}%)")
        else:
            print("No wallet address configured")

        # ================================================================
        # SUMMARY
        # ================================================================
        print_section("📋 SUMMARY")

        print("MAMMON's Competitive Advantages:")
        print(f"  1. Prediction Accuracy: {format_percentage(accuracy)}")
        print(f"  2. Win Rate: {format_percentage(win_rate)}")
        print(f"  3. Gas Efficiency: {format_usd(metrics.average_gas_per_rebalance)} per rebalance")
        print(f"  4. Safety System: {false_positives} losses avoided")
        print(f"  5. Total Profit: {format_usd(metrics.net_profit_usd)} (net of gas)")

        print("\nx402 Marketplace Readiness:")
        if accuracy >= 85 and win_rate >= 75:
            print("  ✅ READY - Strong track record for x402 marketplace")
        elif accuracy >= 75 and win_rate >= 65:
            print("  ⏳ NEARLY READY - Build more track record")
        else:
            print("  ❌ NOT READY - Need more data and optimization")

        print("\n" + "═" * 80 + "\n")

    finally:
        position_tracker.close()
        performance_tracker.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Display MAMMON performance metrics dashboard"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)"
    )

    args = parser.parse_args()

    asyncio.run(show_performance_dashboard(days=args.days))


if __name__ == "__main__":
    main()
