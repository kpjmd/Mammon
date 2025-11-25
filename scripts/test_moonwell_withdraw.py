#!/usr/bin/env python3
"""Withdraw from Moonwell on Base mainnet.

Usage:
    poetry run python scripts/test_moonwell_withdraw.py --amount 2
"""

import sys
from pathlib import Path

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

MUSDC_ADDRESS = "0xEdc817A28E8B93B03976FBd4a3dDBc9f7D176c22"
USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

ERC20_ABI = [
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
]

MTOKEN_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "redeemAmount", "type": "uint256"}],
        "name": "redeemUnderlying",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
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
]


async def withdraw_moonwell(amount: Decimal):
    """Withdraw from Moonwell."""
    print("\n" + "=" * 60)
    print("MOONWELL WITHDRAW".center(60))
    print("=" * 60 + "\n")

    config = {
        "wallet_seed": os.getenv("WALLET_SEED"),
        "network": "base-mainnet",
        "read_only": False,
        "dry_run_mode": False,
        "use_mock_data": False,
        "chainlink_enabled": False,  # Disable to avoid 429 errors
        "max_transaction_value_usd": Decimal("10000"),
        "daily_spending_limit_usd": Decimal("50000"),
    }

    # Use mock oracle to avoid Chainlink 429 errors
    oracle = create_price_oracle(
        "mock",
        network=config["network"],
    )

    wallet = WalletManager(config=config, price_oracle=oracle)
    await wallet.initialize()

    wallet_address = wallet.address
    print(f"Wallet: {wallet_address}")

    w3 = get_web3("base-mainnet")

    usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
    musdc_contract = w3.eth.contract(address=MUSDC_ADDRESS, abi=MTOKEN_ABI)

    # Check balances
    usdc_balance = usdc_contract.functions.balanceOf(wallet_address).call()
    musdc_balance = musdc_contract.functions.balanceOf(wallet_address).call()
    decimals = usdc_contract.functions.decimals().call()

    print(f"USDC: {Decimal(str(usdc_balance)) / Decimal(10**decimals)}")
    print(f"mUSDC: {musdc_balance}")

    if musdc_balance == 0:
        print("\n❌ No mUSDC to withdraw!")
        return

    amount_wei = int(amount * Decimal(10**decimals))

    print(f"\nWithdrawing {amount} USDC...")

    try:
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

        receipt = w3.eth.wait_for_transaction_receipt(redeem_tx_hash)

        if receipt["status"] == 1:
            print(f"\n✅ WITHDRAW SUCCESSFUL!")
            print(f"TX: {redeem_tx_hash}")
            print(f"URL: https://basescan.org/tx/{redeem_tx_hash}")
            print(f"Gas: {receipt['gasUsed']:,}")

            # Final balances
            final_usdc = usdc_contract.functions.balanceOf(wallet_address).call()
            final_musdc = musdc_contract.functions.balanceOf(wallet_address).call()
            print(f"\nFinal USDC: {Decimal(str(final_usdc)) / Decimal(10**decimals)}")
            print(f"Final mUSDC: {final_musdc}")
            print("\n✅ Moonwell cycle complete! Multi-protocol validated!")
        else:
            print(f"❌ Withdraw failed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"Withdraw error: {e}", exc_info=True)

    print("\n" + "=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--amount", type=str, default="2")
    args = parser.parse_args()
    asyncio.run(withdraw_moonwell(Decimal(args.amount)))


if __name__ == "__main__":
    main()
