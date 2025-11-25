#!/usr/bin/env python3
"""Test Moonwell deposit/withdraw on Base mainnet.

This script tests the Moonwell protocol (Compound V2 fork):
1. Approve mUSDC contract to spend USDC
2. Deposit USDC (mint mUSDC)
3. Withdraw USDC (redeemUnderlying)

Usage:
    poetry run python scripts/test_moonwell_mainnet.py --amount 2
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
from src.data.oracles import create_price_oracle
from src.utils.logger import get_logger
from src.utils.web3_provider import get_web3

load_dotenv()
logger = get_logger(__name__)

# Moonwell mUSDC on Base mainnet
MUSDC_ADDRESS = "0xEdc817A28E8B93B03976FBd4a3dDBc9f7D176c22"
# USDC on Base mainnet
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def print_header(title: str):
    """Print formatted section header."""
    print("\n" + "=" * 80)
    print(title.center(80))
    print("=" * 80 + "\n")


def print_section(title: str):
    """Print formatted section."""
    print(f"\n{title}")
    print("-" * 80)


# Extended ERC20 ABI
ERC20_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Moonwell mToken ABI
MTOKEN_ABI = [
    # mint(uint256 mintAmount) - deposit underlying
    {
        "inputs": [{"internalType": "uint256", "name": "mintAmount", "type": "uint256"}],
        "name": "mint",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # redeemUnderlying(uint256 redeemAmount) - withdraw by underlying amount
    {
        "inputs": [{"internalType": "uint256", "name": "redeemAmount", "type": "uint256"}],
        "name": "redeemUnderlying",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # balanceOf
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # balanceOfUnderlying - get underlying value
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "balanceOfUnderlying",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # exchangeRateStored
    {
        "inputs": [],
        "name": "exchangeRateStored",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


async def test_moonwell(amount: Decimal):
    """Test Moonwell deposit/withdraw on Base mainnet.

    Args:
        amount: Amount in USDC to test with
    """
    print_header("MAMMON - Moonwell Base Mainnet Test")
    print(f"Network: Base Mainnet")
    print(f"Amount: {amount} USDC\n")

    # Configuration for mainnet
    config = {
        "wallet_seed": os.getenv("WALLET_SEED"),
        "network": "base-mainnet",
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

    w3 = get_web3("base-mainnet")

    # Contract instances
    usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
    musdc_contract = w3.eth.contract(address=MUSDC_ADDRESS, abi=MTOKEN_ABI)

    # Check initial balances
    print_section("INITIAL BALANCES")
    usdc_balance_wei = usdc_contract.functions.balanceOf(wallet_address).call()
    usdc_decimals = usdc_contract.functions.decimals().call()
    usdc_balance = Decimal(str(usdc_balance_wei)) / Decimal(10 ** usdc_decimals)

    musdc_balance = musdc_contract.functions.balanceOf(wallet_address).call()

    eth_balance = w3.eth.get_balance(wallet_address)
    eth_balance_dec = Decimal(str(eth_balance)) / Decimal(10**18)

    print(f"USDC: {usdc_balance}")
    print(f"mUSDC: {musdc_balance}")
    print(f"ETH: {eth_balance_dec}")

    if usdc_balance < amount:
        print(f"\n❌ Insufficient USDC! Need {amount}, have {usdc_balance}")
        return

    amount_wei = int(amount * Decimal(10 ** usdc_decimals))

    # STEP 1: APPROVE
    print_section("STEP 1: APPROVE mUSDC CONTRACT")

    # Check current allowance
    current_allowance = usdc_contract.functions.allowance(
        wallet_address, MUSDC_ADDRESS
    ).call()

    print(f"Current allowance: {current_allowance}")
    print(f"Needed: {amount_wei}")

    if current_allowance < amount_wei:
        print("Approving mUSDC to spend USDC (max approval)...")

        max_uint256 = 2**256 - 1
        approve_tx_data = usdc_contract.functions.approve(
            MUSDC_ADDRESS, max_uint256
        ).build_transaction({
            "from": wallet_address,
            "nonce": w3.eth.get_transaction_count(wallet_address),
        })

        approve_tx_hash = await wallet.send_transaction(
            to=USDC_ADDRESS,
            data=approve_tx_data["data"],
            value=Decimal("0"),
        )

        approve_receipt = w3.eth.wait_for_transaction_receipt(approve_tx_hash)

        if approve_receipt["status"] == 1:
            print(f"✅ Approval successful!")
            print(f"TX: {approve_tx_hash}")
            print(f"URL: https://basescan.org/tx/{approve_tx_hash}")
            print(f"Gas: {approve_receipt['gasUsed']:,}")

            # Wait for state to propagate
            print("Waiting for approval to propagate...")
            await asyncio.sleep(3)
        else:
            print(f"❌ Approval failed!")
            return
    else:
        print("✅ Already approved")

    # Verify allowance after approval
    new_allowance = usdc_contract.functions.allowance(
        wallet_address, MUSDC_ADDRESS
    ).call()
    print(f"Verified allowance: {new_allowance}")

    if new_allowance < amount_wei:
        print(f"❌ Allowance still insufficient! {new_allowance} < {amount_wei}")
        print("This may be an RPC caching issue. Try running again.")
        return

    # STEP 2: DEPOSIT (MINT)
    print_section("STEP 2: DEPOSIT INTO MOONWELL")
    print(f"Depositing {amount} USDC...")

    try:
        # Build mint transaction
        mint_tx_data = musdc_contract.functions.mint(amount_wei).build_transaction({
            "from": wallet_address,
            "nonce": w3.eth.get_transaction_count(wallet_address),
        })

        mint_tx_hash = await wallet.send_transaction(
            to=MUSDC_ADDRESS,
            data=mint_tx_data["data"],
            value=Decimal("0"),
        )

        mint_receipt = w3.eth.wait_for_transaction_receipt(mint_tx_hash)

        if mint_receipt["status"] == 1:
            print(f"\n✅ DEPOSIT SUCCESSFUL!")
            print(f"TX: {mint_tx_hash}")
            print(f"URL: https://basescan.org/tx/{mint_tx_hash}")
            print(f"Gas: {mint_receipt['gasUsed']:,}")
        else:
            print(f"❌ Deposit failed!")
            return

    except Exception as e:
        print(f"❌ Error during deposit: {e}")
        logger.error(f"Deposit error: {e}", exc_info=True)
        return

    # Check balances after deposit
    print_section("BALANCES AFTER DEPOSIT")
    usdc_after = usdc_contract.functions.balanceOf(wallet_address).call()
    musdc_after = musdc_contract.functions.balanceOf(wallet_address).call()
    print(f"USDC: {Decimal(str(usdc_after)) / Decimal(10 ** usdc_decimals)}")
    print(f"mUSDC: {musdc_after}")

    # Wait before withdraw
    print("\nWaiting 5 seconds before withdraw...")
    await asyncio.sleep(5)

    # STEP 3: WITHDRAW (REDEEM UNDERLYING)
    print_section("STEP 3: WITHDRAW FROM MOONWELL")
    print(f"Withdrawing {amount} USDC...")

    try:
        # Build redeemUnderlying transaction
        redeem_tx_data = musdc_contract.functions.redeemUnderlying(
            amount_wei
        ).build_transaction({
            "from": wallet_address,
            "nonce": w3.eth.get_transaction_count(wallet_address),
        })

        redeem_tx_hash = await wallet.send_transaction(
            to=MUSDC_ADDRESS,
            data=redeem_tx_data["data"],
            value=Decimal("0"),
        )

        redeem_receipt = w3.eth.wait_for_transaction_receipt(redeem_tx_hash)

        if redeem_receipt["status"] == 1:
            print(f"\n✅ WITHDRAW SUCCESSFUL!")
            print(f"TX: {redeem_tx_hash}")
            print(f"URL: https://basescan.org/tx/{redeem_tx_hash}")
            print(f"Gas: {redeem_receipt['gasUsed']:,}")
        else:
            print(f"❌ Withdraw failed!")
            return

    except Exception as e:
        print(f"❌ Error during withdraw: {e}")
        logger.error(f"Withdraw error: {e}", exc_info=True)
        return

    # Final balances
    print_section("FINAL BALANCES")
    final_usdc = usdc_contract.functions.balanceOf(wallet_address).call()
    final_musdc = musdc_contract.functions.balanceOf(wallet_address).call()
    final_eth = w3.eth.get_balance(wallet_address)

    print(f"USDC: {Decimal(str(final_usdc)) / Decimal(10 ** usdc_decimals)}")
    print(f"mUSDC: {final_musdc}")
    print(f"ETH: {Decimal(str(final_eth)) / Decimal(10**18)}")

    # Summary
    print_section("TEST SUMMARY")
    usdc_change = (Decimal(str(final_usdc)) - Decimal(str(usdc_balance_wei))) / Decimal(10 ** usdc_decimals)
    eth_spent = (Decimal(str(eth_balance)) - Decimal(str(final_eth))) / Decimal(10**18)

    print(f"USDC change: {usdc_change}")
    print(f"ETH spent on gas: {eth_spent}")
    print(f"\n✅ Moonwell deposit/withdraw cycle completed successfully!")
    print("Multi-protocol support validated on mainnet!")

    print("\n" + "=" * 80 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test Moonwell deposit/withdraw on Base mainnet"
    )
    parser.add_argument(
        "--amount",
        type=str,
        default="2",
        help="Amount of USDC to test with (default: 2)"
    )

    args = parser.parse_args()

    try:
        amount = Decimal(args.amount)
    except:
        print(f"Error: Invalid amount '{args.amount}'")
        return

    asyncio.run(test_moonwell(amount))


if __name__ == "__main__":
    main()
