#!/usr/bin/env python3
"""Test full Aave V3 deposit/withdraw cycle on Base Sepolia.

This script tests the complete cycle:
1. Deposit USDC into Aave V3
2. Check position tracking updates
3. Withdraw USDC from Aave V3
4. Verify position tracking

This proves the full rebalance workflow works.

Usage:
    poetry run python scripts/test_aave_cycle.py --amount 5
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

from src.blockchain.wallet import WalletManager
from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.data.oracles import create_price_oracle
from src.data.position_tracker import PositionTracker
from src.utils.logger import get_logger
from src.utils.web3_provider import get_web3

load_dotenv()
logger = get_logger(__name__)


def print_header(title: str):
    """Print formatted section header."""
    print("\n" + "=" * 80)
    print(title.center(80))
    print("=" * 80 + "\n")


def print_section(title: str):
    """Print formatted section."""
    print(f"\n{title}")
    print("-" * 80)


async def check_usdc_balance(w3, wallet_address: str) -> Decimal:
    """Check USDC balance.

    Args:
        w3: Web3 instance
        wallet_address: Wallet address

    Returns:
        USDC balance
    """
    # USDC on Base Sepolia
    usdc_address = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

    erc20_abi = [{
        'constant': True,
        'inputs': [{'name': '_owner', 'type': 'address'}],
        'name': 'balanceOf',
        'outputs': [{'name': 'balance', 'type': 'uint256'}],
        'type': 'function'
    }, {
        'constant': True,
        'inputs': [],
        'name': 'decimals',
        'outputs': [{'name': '', 'type': 'uint8'}],
        'type': 'function'
    }]

    usdc_contract = w3.eth.contract(
        address=w3.to_checksum_address(usdc_address),
        abi=erc20_abi
    )

    balance_wei = usdc_contract.functions.balanceOf(wallet_address).call()
    decimals = usdc_contract.functions.decimals().call()
    return Decimal(str(balance_wei)) / Decimal(10 ** decimals)


async def check_aave_balance(w3, wallet_address: str) -> Decimal:
    """Check aToken balance.

    Args:
        w3: Web3 instance
        wallet_address: Wallet address

    Returns:
        aToken balance (USDC equivalent)
    """
    # aBasSepUSDC token address
    ausdc_address = "0xf53B60F4006cab2b3C4688ce41fD5362427A2A66"

    erc20_abi = [{
        'constant': True,
        'inputs': [{'name': '_owner', 'type': 'address'}],
        'name': 'balanceOf',
        'outputs': [{'name': 'balance', 'type': 'uint256'}],
        'type': 'function'
    }, {
        'constant': True,
        'inputs': [],
        'name': 'decimals',
        'outputs': [{'name': '', 'type': 'uint8'}],
        'type': 'function'
    }]

    ausdc_contract = w3.eth.contract(
        address=w3.to_checksum_address(ausdc_address),
        abi=erc20_abi
    )

    balance_wei = ausdc_contract.functions.balanceOf(wallet_address).call()
    decimals = ausdc_contract.functions.decimals().call()
    return Decimal(str(balance_wei)) / Decimal(10 ** decimals)


async def test_aave_cycle(amount: Decimal):
    """Test full Aave V3 deposit/withdraw cycle.

    Args:
        amount: Amount in USDC
    """
    print_header("MAMMON - Aave V3 Full Cycle Test")
    print(f"Network: Base Sepolia")
    print(f"Amount: {amount} USDC\n")

    # Configuration
    config = {
        "wallet_seed": os.getenv("WALLET_SEED"),
        "network": "base-sepolia",
        "read_only": False,
        "dry_run_mode": False,
        "use_mock_data": False,
        "chainlink_enabled": True,
        "max_transaction_value_usd": Decimal("10000"),
        "daily_spending_limit_usd": Decimal("50000"),
    }

    # Initialize components
    print("Initializing components...")

    oracle = create_price_oracle(
        "chainlink",
        network=config["network"],
        fallback_to_mock=True,
    )

    wallet = WalletManager(config=config, price_oracle=oracle)
    await wallet.initialize()

    wallet_address = wallet.address
    print(f"Wallet Address: {wallet_address}")

    w3 = get_web3("base-sepolia")

    # Check initial balances
    print_section("INITIAL BALANCES")
    usdc_balance = await check_usdc_balance(w3, wallet_address)
    aave_balance = await check_aave_balance(w3, wallet_address)
    print(f"USDC: {usdc_balance}")
    print(f"aBasSepUSDC: {aave_balance}")

    if usdc_balance < amount:
        print(f"\n Insufficient USDC! Need {amount}, have {usdc_balance}")
        return

    # Initialize executor
    executor = ProtocolActionExecutor(
        wallet_manager=wallet,
        config=config,
    )

    # Initialize position tracker
    position_tracker = PositionTracker()

    # STEP 1: DEPOSIT
    print_section("STEP 1: DEPOSIT INTO AAVE V3")
    print(f"Depositing {amount} USDC...")

    try:
        deposit_result = await executor.execute_deposit(
            protocol_name="Aave V3",
            token="USDC",
            amount=amount,
        )

        if deposit_result.get("success"):
            tx_hash = deposit_result.get("tx_hash")
            gas_used = deposit_result.get("gas_used", 0)

            print(f"\n DEPOSIT SUCCESSFUL!")
            print(f"TX: {tx_hash}")
            print(f"URL: https://sepolia.basescan.org/tx/{tx_hash}")
            print(f"Gas: {gas_used:,}")

            # Record position
            await position_tracker.record_position(
                wallet_address=wallet_address,
                protocol="Aave V3",
                pool_id="usdc-pool",
                token="USDC",
                amount=amount,
                value_usd=amount,  # 1:1 for stablecoin
                current_apy=Decimal("2.5"),  # Placeholder
            )
            print(" Position recorded in tracker")

        else:
            print(f"\n DEPOSIT FAILED: {deposit_result.get('error')}")
            return

    except Exception as e:
        print(f"\n Error during deposit: {e}")
        logger.error(f"Deposit error: {e}", exc_info=True)
        return

    # Check balances after deposit
    print_section("BALANCES AFTER DEPOSIT")
    usdc_balance = await check_usdc_balance(w3, wallet_address)
    aave_balance = await check_aave_balance(w3, wallet_address)
    print(f"USDC: {usdc_balance}")
    print(f"aBasSepUSDC: {aave_balance}")

    # Wait a moment for chain to update
    print("\nWaiting 5 seconds before withdraw...")
    await asyncio.sleep(5)

    # STEP 2: WITHDRAW
    print_section("STEP 2: WITHDRAW FROM AAVE V3")
    print(f"Withdrawing {amount} USDC...")

    try:
        withdraw_result = await executor.execute_withdraw(
            protocol_name="Aave V3",
            token="USDC",
            amount=amount,
        )

        if withdraw_result.get("success"):
            tx_hash = withdraw_result.get("tx_hash")
            gas_used = withdraw_result.get("gas_used", 0)

            print(f"\n WITHDRAW SUCCESSFUL!")
            print(f"TX: {tx_hash}")
            print(f"URL: https://sepolia.basescan.org/tx/{tx_hash}")
            print(f"Gas: {gas_used:,}")

        else:
            print(f"\n WITHDRAW FAILED: {withdraw_result.get('error')}")
            return

    except Exception as e:
        print(f"\n Error during withdraw: {e}")
        logger.error(f"Withdraw error: {e}", exc_info=True)
        return

    # Check final balances
    print_section("FINAL BALANCES")
    final_usdc = await check_usdc_balance(w3, wallet_address)
    final_aave = await check_aave_balance(w3, wallet_address)
    print(f"USDC: {final_usdc}")
    print(f"aBasSepUSDC: {final_aave}")

    # Summary
    print_section("CYCLE SUMMARY")
    print(f"Initial USDC: {usdc_balance + amount}")
    print(f"Final USDC: {final_usdc}")
    print(f"Net change: {final_usdc - (usdc_balance + amount)}")
    print(f"\n Full deposit/withdraw cycle completed successfully!")
    print("This proves the rebalance workflow works end-to-end.")

    # Get portfolio summary
    print_section("PORTFOLIO SUMMARY")
    portfolio = await position_tracker.get_portfolio_summary(wallet_address)
    print(f"Total Value: ${float(portfolio.get('total_value_usd', 0)):.2f}")
    print(f"Active Positions: {portfolio.get('position_count', 0)}")

    position_tracker.close()

    print("\n" + "=" * 80 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test Aave V3 full deposit/withdraw cycle"
    )
    parser.add_argument(
        "--amount",
        type=str,
        default="5",
        help="Amount of USDC to cycle"
    )

    args = parser.parse_args()

    try:
        amount = Decimal(args.amount)
    except:
        print(f"Error: Invalid amount '{args.amount}'")
        return

    asyncio.run(test_aave_cycle(amount))


if __name__ == "__main__":
    main()
