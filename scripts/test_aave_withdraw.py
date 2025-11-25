#!/usr/bin/env python3
"""Test Aave V3 withdrawal on Base Sepolia testnet.

This script tests withdrawing from the existing Aave V3 position:
- We have ~10 aBasSepUSDC deposited
- Test partial withdraw (5 USDC) first
- Then test full withdraw

Usage:
    poetry run python scripts/test_aave_withdraw.py --amount 5
    poetry run python scripts/test_aave_withdraw.py --amount max
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


async def check_aave_balance(wallet_address: str):
    """Check current Aave V3 position (aToken balance).

    Args:
        wallet_address: Wallet address to check

    Returns:
        Balance in USDC equivalent
    """
    w3 = get_web3("base-sepolia")

    # aBasSepUSDC token address (queried from Aave V3 Pool getReserveData)
    ausdc_address = "0xf53B60F4006cab2b3C4688ce41fD5362427A2A66"

    # ERC20 ABI for balanceOf
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
    balance = Decimal(str(balance_wei)) / Decimal(10 ** decimals)

    print(f"Current aBasSepUSDC Balance: {balance}")
    print(f"(Represents ~{balance} USDC deposited in Aave V3)\n")

    return balance


async def test_aave_withdraw(amount: Decimal, is_max: bool = False):
    """Test Aave V3 withdrawal.

    Args:
        amount: Amount to withdraw in USDC
        is_max: If True, withdraw all available
    """
    print_header("MAMMON - Test Aave V3 Withdraw")
    print(f"Network: Base Sepolia")
    print(f"Action: Withdraw {amount if not is_max else 'ALL'} USDC from Aave V3\n")

    # Configuration
    config = {
        "wallet_seed": os.getenv("WALLET_SEED"),
        "network": "base-sepolia",
        "read_only": False,
        "dry_run_mode": False,  # REAL TRANSACTION
        "use_mock_data": False,
        "chainlink_enabled": True,
        # Safety limits
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

    # Check current balance
    print("\nChecking current Aave V3 position...")
    current_balance = await check_aave_balance(wallet_address)

    if current_balance == 0:
        print("❌ No Aave V3 position found!")
        print("   You need to deposit USDC into Aave V3 first.")
        return

    # Determine withdraw amount
    if is_max:
        withdraw_amount = current_balance
        print(f"✅ Will withdraw ALL: {withdraw_amount} USDC")
    else:
        if amount > current_balance:
            print(f"⚠️  Requested {amount} USDC but only {current_balance} available")
            print(f"   Withdrawing maximum: {current_balance} USDC")
            withdraw_amount = current_balance
        else:
            withdraw_amount = amount
            print(f"✅ Will withdraw: {withdraw_amount} USDC")

    # Initialize protocol executor
    executor = ProtocolActionExecutor(
        wallet_manager=wallet,
        config=config,
    )

    # Execute withdrawal
    print("\n" + "─" * 80)
    print("EXECUTING WITHDRAWAL")
    print("─" * 80 + "\n")

    try:
        result = await executor.execute_withdraw(
            protocol_name="Aave V3",
            token="USDC",
            amount=withdraw_amount,
        )

        if result.get("success"):
            tx_hash = result.get("tx_hash")
            gas_used = result.get("gas_used", 0)

            print("\n✅ WITHDRAWAL SUCCESSFUL!\n")
            print(f"Transaction Hash: {tx_hash}")
            print(f"BaseScan URL: https://sepolia.basescan.org/tx/{tx_hash}")
            print(f"Gas Used: {gas_used:,}")
            print(f"Amount Withdrawn: {withdraw_amount} USDC")

            # Check new balance
            print("\nChecking new balance...")
            new_balance = await check_aave_balance(wallet_address)
            print(f"Remaining in Aave V3: {new_balance} USDC")

            # Record position update in tracker
            print("\nUpdating position tracker...")
            position_tracker = PositionTracker()

            if new_balance == 0:
                # Position closed
                print("Position fully closed")
            else:
                # Update position
                await position_tracker.record_position(
                    wallet_address=wallet_address,
                    protocol="Aave V3",
                    pool_id="usdc-pool",
                    token="USDC",
                    amount=new_balance,
                    value_usd=new_balance,  # 1:1 for stablecoin
                    current_apy=Decimal("0"),  # Would fetch real APY
                )
                print("✅ Position updated in database")

            position_tracker.close()

        else:
            print("\n❌ WITHDRAWAL FAILED!")
            print(f"Error: {result.get('error')}")

    except Exception as e:
        print(f"\n❌ Error during withdrawal: {e}")
        logger.error(f"Withdrawal error: {e}", exc_info=True)

    print("\n" + "=" * 80 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test Aave V3 withdrawal on Base Sepolia"
    )
    parser.add_argument(
        "--amount",
        type=str,
        default="5",
        help="Amount to withdraw (or 'max' for all)"
    )

    args = parser.parse_args()

    if args.amount.lower() == "max":
        amount = Decimal("0")
        is_max = True
    else:
        try:
            amount = Decimal(args.amount)
            is_max = False
        except:
            print(f"Error: Invalid amount '{args.amount}'")
            print("Use a number (e.g., 5) or 'max'")
            return

    asyncio.run(test_aave_withdraw(amount, is_max))


if __name__ == "__main__":
    main()
