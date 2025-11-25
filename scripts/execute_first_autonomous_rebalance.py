#!/usr/bin/env python3
"""Execute MAMMON's first autonomous rebalance from Aave V3 to Moonwell.

This is a focused script that directly executes the first autonomous rebalance
without the full protocol scanning phase, making it faster and more predictable.

Historic Milestone: First autonomous yield optimization on Base mainnet!
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import os
from datetime import datetime, UTC
from decimal import Decimal
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.blockchain.wallet import WalletManager
from src.blockchain.rebalance_executor import RebalanceExecutor
from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.blockchain.gas_estimator import GasEstimator
from src.data.oracles import create_price_oracle
from src.data.position_tracker import PositionTracker
from src.data.database import Database
from src.strategies.base_strategy import RebalanceRecommendation
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def main():
    """Execute MAMMON's first autonomous rebalance."""

    print("=" * 80)
    print("🚀 MAMMON - FIRST AUTONOMOUS REBALANCE")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print(f"Network: base-mainnet")
    print("")

    # Initialize components
    print("Initializing components...")
    settings = get_settings()

    # Create config for base-mainnet (LIVE MODE)
    config = {
        "network": "base-mainnet",
        "dry_run_mode": False,  # LIVE MODE!
        "simulate_before_execute": True,
        "max_transaction_value_usd": 1000,
        "daily_spending_limit_usd": 5000,
        "approval_threshold_usd": 500,
        "wallet_seed": os.getenv("WALLET_SEED"),  # Load from .env
    }

    # Initialize wallet
    wallet = WalletManager(config=config)
    await wallet.initialize()
    wallet_address = await wallet.get_address()
    print(f"✅ Wallet: {wallet_address}")

    # Initialize oracle and gas estimator
    oracle = create_price_oracle(
        "chainlink" if settings.chainlink_enabled else "mock",
        network=config["network"],
    )
    gas_estimator = GasEstimator(config["network"], oracle)
    print(f"✅ Price oracle and gas estimator")

    # Initialize protocol executor
    protocol_executor = ProtocolActionExecutor(wallet, config)
    print(f"✅ Protocol executor")

    # Initialize rebalance executor
    rebalance_executor = RebalanceExecutor(
        wallet_manager=wallet,
        protocol_executor=protocol_executor,
        gas_estimator=gas_estimator,
        price_oracle=oracle,
        config=config,
    )
    print(f"✅ Rebalance executor")

    # Initialize database and position tracker
    database_url = settings.database_url or "sqlite:///data/mammon.db"
    db = Database(database_url)
    db.create_all_tables()
    db_path = database_url.replace("sqlite:///", "")
    position_tracker = PositionTracker(db_path)
    print(f"✅ Position tracker")
    print("")

    # Get current position from database
    print("Checking current position...")
    positions = await position_tracker.get_current_positions(
        wallet_address=wallet_address,
        protocol="Aave V3"
    )

    if not positions:
        print("❌ No open Aave V3 position found in database!")
        print("Run: poetry run python scripts/detect_existing_positions.py")
        return 1

    aave_position = positions[0]
    print(f"✅ Found position:")
    print(f"   Protocol: {aave_position.protocol}")
    print(f"   Amount: {aave_position.amount} {aave_position.token}")
    print(f"   Value: ${aave_position.value_usd}")
    print(f"   Current APY: {aave_position.current_apy}%")
    print("")

    # Create rebalance recommendation
    # Based on manual observation: Moonwell USDC is at ~5.23% APY
    print("Creating rebalance recommendation...")
    recommendation = RebalanceRecommendation(
        from_protocol="Aave V3",
        to_protocol="Moonwell",
        token="USDC",
        amount=aave_position.amount,
        expected_apy=Decimal("5.23"),  # Moonwell USDC APY
        current_apy=aave_position.current_apy,
        reason=(
            f"APY improvement: {aave_position.current_apy}% → 5.23% "
            f"(+{Decimal('5.23') - aave_position.current_apy}%). "
            f"First autonomous rebalance!"
        ),
        confidence=95,
    )

    print(f"✅ Recommendation created:")
    print(f"   From: {recommendation.from_protocol} @ {recommendation.current_apy}%")
    print(f"   To: {recommendation.to_protocol} @ {recommendation.expected_apy}%")
    print(f"   Amount: {recommendation.amount} {recommendation.token}")
    print(f"   APY Improvement: +{recommendation.expected_apy - recommendation.current_apy}%")
    print("")

    # Confirm execution
    print("=" * 80)
    print("⚠️  READY TO EXECUTE REAL TRANSACTIONS ON BASE MAINNET")
    print("=" * 80)
    print("")
    print("This will:")
    print(f"  1. Withdraw {recommendation.amount} USDC from Aave V3")
    print(f"  2. Approve Moonwell mToken contract")
    print(f"  3. Deposit {recommendation.amount} USDC to Moonwell")
    print("")
    print("Press Ctrl+C now to cancel, or wait 5 seconds to proceed...")
    print("")

    await asyncio.sleep(5)

    # Execute rebalance
    print("=" * 80)
    print("EXECUTING REBALANCE...")
    print("=" * 80)
    print("")

    try:
        execution = await rebalance_executor.execute_rebalance(recommendation)

        print("")
        print("=" * 80)
        print("EXECUTION COMPLETE!")
        print("=" * 80)
        print("")

        # Display results
        print(f"Status: {'✅ SUCCESS' if execution.success else '❌ FAILED'}")
        print(f"Total gas used: {execution.total_gas_used:,}")
        print(f"Gas cost: {execution.total_gas_cost_eth:.6f} ETH (${execution.total_gas_cost_usd:.4f})")
        print("")

        print("Transaction Steps:")
        for i, step in enumerate(execution.steps, 1):
            status = "✅" if step.success else "❌"
            print(f"  {i}. {status} {step.step.value}")
            if step.tx_hash and not step.tx_hash.startswith("0xdryrun"):
                print(f"     TX: https://basescan.org/tx/{step.tx_hash}")
            if step.gas_used:
                print(f"     Gas: {step.gas_used:,}")
            if step.error:
                print(f"     Error: {step.error}")

        print("")

        if execution.success:
            print("🎉 HISTORIC MILESTONE: First autonomous rebalance complete!")
            print("")
            print("Next steps:")
            print("  1. Verify transactions on BaseScan (links above)")
            print("  2. Check database: poetry run python scripts/detect_existing_positions.py")
            print("  3. Verify on-chain balance")
            return 0
        else:
            print("❌ Rebalance failed. Check error messages above.")
            return 1

    except Exception as e:
        print("")
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Cancelled by user")
        sys.exit(1)
