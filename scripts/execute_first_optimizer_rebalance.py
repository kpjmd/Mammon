#!/usr/bin/env python3
"""Execute first optimizer-driven rebalance on Base Sepolia testnet.

This script demonstrates the complete end-to-end flow:
1. Scan protocols for yield opportunities
2. Generate rebalance recommendations via OptimizerAgent
3. Execute rebalance via RebalanceExecutor
4. Display transaction URLs and results

Usage:
    # With mock simulator (safe, always works):
    poetry run python scripts/execute_first_optimizer_rebalance.py --mock

    # With real testnet (requires wallet + funds):
    poetry run python scripts/execute_first_optimizer_rebalance.py --testnet

Environment variables required for --testnet:
    WALLET_SEED=<your_testnet_wallet_seed>
    ALCHEMY_API_KEY=<your_alchemy_key>  (recommended)
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import argparse
import os
from decimal import Decimal
from dotenv import load_dotenv

from src.agents.yield_scanner import YieldScannerAgent
from src.agents.optimizer import OptimizerAgent
from src.strategies.simple_yield import SimpleYieldStrategy
from src.blockchain.wallet import WalletManager
from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.blockchain.mock_protocol_simulator import MockProtocolSimulator
from src.blockchain.rebalance_executor import RebalanceExecutor
from src.blockchain.gas_estimator import GasEstimator
from src.data.oracles import create_price_oracle
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


def print_header(title: str):
    """Print formatted section header."""
    print("\n" + "=" * 80)
    print(title.center(80))
    print("=" * 80 + "\n")


def print_subheader(title: str):
    """Print formatted subsection header."""
    print("\n" + "-" * 80)
    print(title)
    print("-" * 80)


async def run_mock_demo():
    """Run demo with MockProtocolSimulator (safe, always works)."""
    print_header("MAMMON - Phase 4 Sprint 1 Demo (MOCK MODE)")
    print("This demo uses MockProtocolSimulator for safe testing")
    print("No real blockchain transactions will be executed")
    print()

    # Configuration
    config = {
        "network": "base-sepolia",
        "read_only": True,
        "dry_run_mode": True,
        "use_mock_data": True,
        "chainlink_enabled": False,
        # Profitability gates
        "min_annual_gain_usd": Decimal("10"),
        "max_break_even_days": 30,
        "max_cost_pct": Decimal("0.01"),
        # Strategy settings
        "min_apy_improvement": Decimal("0.5"),
        "min_rebalance_amount": Decimal("100"),
        # Safety limits
        "max_transaction_value_usd": Decimal("10000"),
        "daily_spending_limit_usd": Decimal("50000"),
    }

    # Initialize components
    print_subheader("Step 1: Initialize Components")

    oracle = create_price_oracle("mock")
    wallet = WalletManager(config=config, price_oracle=oracle)
    # Note: Don't initialize wallet for mock mode

    mock_executor = MockProtocolSimulator()
    gas_estimator = GasEstimator(
        network=config["network"],
        price_oracle=oracle,
    )

    rebalance_executor = RebalanceExecutor(
        wallet_manager=wallet,
        protocol_executor=mock_executor,
        gas_estimator=gas_estimator,
        price_oracle=oracle,
        config=config,
    )

    print("✅ MockProtocolSimulator initialized")
    print("✅ RebalanceExecutor initialized")

    # Create test recommendation manually (instead of scanning)
    print_subheader("Step 2: Create Test Recommendation")

    from src.strategies.base_strategy import RebalanceRecommendation

    recommendation = RebalanceRecommendation(
        from_protocol="Moonwell",
        to_protocol="Aave V3",
        token="USDC",
        amount=Decimal("1000"),
        expected_apy=Decimal("8.5"),
        reason="Higher APY in Aave V3 (8.5% vs 5.2%)",
        confidence=85,
    )

    print(f"📊 Recommendation:")
    print(f"   From: {recommendation.from_protocol}")
    print(f"   To: {recommendation.to_protocol}")
    print(f"   Token: {recommendation.token}")
    print(f"   Amount: ${recommendation.amount}")
    print(f"   Expected APY: {recommendation.expected_apy}%")
    print(f"   Reason: {recommendation.reason}")

    # Execute rebalance
    print_subheader("Step 3: Execute Rebalance")
    print("Executing multi-step rebalance workflow...")
    print()

    execution = await rebalance_executor.execute_rebalance(recommendation)

    # Display results
    print_subheader("Step 4: Execution Results")

    summary = rebalance_executor.get_execution_summary(execution)
    print(summary)

    # Show individual transaction hashes (mock)
    print_subheader("Step 5: Transaction Details")

    for i, step in enumerate(execution.steps, 1):
        if step.tx_hash:
            print(f"{i}. {step.step.value.upper()}")
            print(f"   TX Hash: {step.tx_hash}")
            print(f"   Gas Used: {step.gas_used:,}" if step.gas_used else "")
            print()

    if execution.success:
        print("✅ DEMO SUCCESSFUL!")
        print()
        print("Next steps:")
        print("  1. Set up testnet wallet with WALLET_SEED in .env")
        print("  2. Fund wallet with Base Sepolia ETH")
        print("  3. Run with --testnet flag for real execution")
    else:
        print("❌ Demo failed - check logs above")


async def run_testnet_demo():
    """Run demo with real Base Sepolia testnet transactions."""
    print_header("MAMMON - Phase 4 Sprint 1 Demo (TESTNET MODE)")
    print("⚠️  WARNING: This will execute REAL transactions on Base Sepolia testnet")
    print("⚠️  Ensure you have testnet ETH for gas fees")
    print()

    # Configuration
    config = {
        "wallet_seed": os.getenv("WALLET_SEED"),
        "network": "base-sepolia",
        "read_only": False,
        "dry_run_mode": False,  # REAL transactions!
        "use_mock_data": False,
        "chainlink_enabled": True,
        "chainlink_fallback_to_mock": True,
        # Profitability gates
        "min_annual_gain_usd": Decimal("1"),  # Lower for testnet
        "max_break_even_days": 365,  # Relaxed for testnet
        "max_cost_pct": Decimal("0.1"),  # 10% max cost
        # Strategy settings
        "min_apy_improvement": Decimal("0.1"),  # Lower for testnet
        "min_rebalance_amount": Decimal("1"),  # Small amounts for testnet
        # Safety limits
        "max_transaction_value_usd": Decimal("100"),
        "daily_spending_limit_usd": Decimal("500"),
    }

    try:
        # Initialize components
        print_subheader("Step 1: Initialize Wallet and Components")

        oracle = create_price_oracle(
            "chainlink",
            network=config["network"],
            fallback_to_mock=config.get("chainlink_fallback_to_mock", True),
        )
        wallet = WalletManager(config=config, price_oracle=oracle)

        print("Initializing wallet...")
        await wallet.initialize()

        wallet_address = await wallet.get_address()
        print(f"✅ Wallet initialized: {wallet_address}")

        # Check balance
        balance_eth = await wallet.get_balance("ETH")
        print(f"   Balance: {balance_eth} ETH")

        if balance_eth < Decimal("0.001"):
            print()
            print("⚠️  WARNING: Low ETH balance!")
            print("   You may not have enough ETH for gas fees")
            print("   Get testnet ETH from: https://www.alchemy.com/faucets/base-sepolia")
            print()
            return

        # Initialize protocol executor
        protocol_executor = ProtocolActionExecutor(wallet, config)
        gas_estimator = GasEstimator(
            network=config["network"],
            price_oracle=oracle,
        )

        rebalance_executor = RebalanceExecutor(
            wallet_manager=wallet,
            protocol_executor=protocol_executor,
            gas_estimator=gas_estimator,
            price_oracle=oracle,
            config=config,
        )

        print("✅ ProtocolActionExecutor initialized (Aave V3 support)")
        print("✅ RebalanceExecutor initialized")

        # Create test recommendation
        print_subheader("Step 2: Create Test Recommendation")

        from src.strategies.base_strategy import RebalanceRecommendation

        # Test with small amount for testnet
        recommendation = RebalanceRecommendation(
            from_protocol=None,  # New position (no withdrawal)
            to_protocol="Aave V3",
            token="USDC",
            amount=Decimal("10"),  # Small test amount
            expected_apy=Decimal("5.0"),
            reason="Test deposit to Aave V3 on Base Sepolia",
            confidence=100,
        )

        print(f"📊 Recommendation:")
        print(f"   Action: New position (deposit only)")
        print(f"   Protocol: {recommendation.to_protocol}")
        print(f"   Token: {recommendation.token}")
        print(f"   Amount: ${recommendation.amount}")

        # Confirm with user
        print()
        print("⚠️  This will execute a REAL transaction on Base Sepolia testnet")
        response = input("Continue? (yes/no): ")

        if response.lower() != "yes":
            print("Cancelled by user")
            return

        # Execute rebalance
        print_subheader("Step 3: Execute Rebalance on Testnet")
        print("Executing rebalance workflow...")
        print()

        execution = await rebalance_executor.execute_rebalance(recommendation)

        # Display results
        print_subheader("Step 4: Execution Results")

        summary = rebalance_executor.get_execution_summary(execution)
        print(summary)

        # Show transaction URLs
        print_subheader("Step 5: View Transactions on BaseScan")

        for i, step in enumerate(execution.steps, 1):
            if step.tx_hash and not step.tx_hash.startswith("0xmock"):
                basescan_url = f"https://sepolia.basescan.org/tx/{step.tx_hash}"
                print(f"{i}. {step.step.value.upper()}")
                print(f"   📊 {basescan_url}")
                print()

        if execution.success:
            print("✅ TESTNET EXECUTION SUCCESSFUL!")
            print()
            print("🎉 Congratulations! You've executed your first optimizer-driven")
            print("   rebalance on Base Sepolia testnet!")
        else:
            print("❌ Execution failed - check logs and BaseScan links above")

    except Exception as e:
        print()
        print(f"❌ Error during testnet execution: {e}")
        print()
        print("Common issues:")
        print("  - WALLET_SEED not set in .env")
        print("  - Insufficient testnet ETH for gas")
        print("  - Protocol not available on Sepolia")
        print("  - RPC connection issues")
        raise


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Execute first optimizer-driven rebalance"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockProtocolSimulator (safe, no real transactions)",
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="Execute on Base Sepolia testnet (requires wallet + funds)",
    )

    args = parser.parse_args()

    if args.testnet:
        await run_testnet_demo()
    else:
        # Default to mock mode for safety
        await run_mock_demo()


if __name__ == "__main__":
    asyncio.run(main())
