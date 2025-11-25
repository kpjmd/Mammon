#!/usr/bin/env python3
"""Test Uniswap V3 swap on Base Sepolia testnet.

Tests cross-token swap capability for rebalances between different tokens.

Usage:
    poetry run python scripts/test_swap.py --amount 1 --from USDC --to WETH
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
from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.data.oracles import create_price_oracle
from src.utils.logger import get_logger
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings

load_dotenv()
logger = get_logger(__name__)


def print_header(title: str):
    """Print formatted section header."""
    print("\n" + "=" * 60)
    print(title.center(60))
    print("=" * 60 + "\n")


async def test_swap(amount: Decimal, token_in: str, token_out: str, network: str):
    """Test Uniswap V3 swap.

    Args:
        amount: Amount to swap
        token_in: Input token symbol
        token_out: Output token symbol
        network: Network to use
    """
    print_header(f"MAMMON - Uniswap V3 Swap Test")
    print(f"Network: {network}")
    print(f"Swap: {amount} {token_in} → {token_out}\n")

    config = {
        "wallet_seed": os.getenv("WALLET_SEED"),
        "network": network,
        "read_only": False,
        "dry_run_mode": False,
        "use_mock_data": False,
        "chainlink_enabled": False,  # Use mock to avoid 429
        "max_transaction_value_usd": Decimal("10000"),
        "daily_spending_limit_usd": Decimal("50000"),
    }

    # Initialize
    print("Initializing...")

    oracle = create_price_oracle(
        "mock",
        network=config["network"],
    )

    wallet = WalletManager(config=config, price_oracle=oracle)
    await wallet.initialize()

    wallet_address = wallet.address
    print(f"Wallet: {wallet_address}")

    settings = get_settings()
    w3 = get_web3(network, config=settings)

    # Check balances
    from src.blockchain.protocol_action_executor import TOKEN_ADDRESSES, ERC20_ABI

    token_in_address = TOKEN_ADDRESSES[network].get(token_in)
    token_out_address = TOKEN_ADDRESSES[network].get(token_out)

    if not token_in_address:
        print(f"❌ Token {token_in} not configured for {network}")
        return
    if not token_out_address:
        print(f"❌ Token {token_out} not configured for {network}")
        return

    token_in_contract = w3.eth.contract(address=token_in_address, abi=ERC20_ABI)
    token_out_contract = w3.eth.contract(address=token_out_address, abi=ERC20_ABI)

    token_in_decimals = token_in_contract.functions.decimals().call()
    token_out_decimals = token_out_contract.functions.decimals().call()

    balance_in = token_in_contract.functions.balanceOf(wallet_address).call()
    balance_out = token_out_contract.functions.balanceOf(wallet_address).call()

    balance_in_formatted = Decimal(str(balance_in)) / Decimal(10**token_in_decimals)
    balance_out_formatted = Decimal(str(balance_out)) / Decimal(10**token_out_decimals)

    print(f"\nInitial balances:")
    print(f"  {token_in}: {balance_in_formatted}")
    print(f"  {token_out}: {balance_out_formatted}")

    if balance_in_formatted < amount:
        print(f"\n❌ Insufficient {token_in}! Need {amount}, have {balance_in_formatted}")
        return

    # Execute swap
    executor = ProtocolActionExecutor(
        wallet_manager=wallet,
        config=config,
    )

    print(f"\nExecuting swap...")

    try:
        result = await executor.execute_swap(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount,
            slippage_percent=Decimal("1.0"),  # 1% slippage for testnet
            fee_tier=3000,  # 0.3% pool
        )

        if result.get("success"):
            tx_hash = result.get("tx_hash")
            gas_used = result.get("gas_used", 0)
            expected_out = result.get("expected_out", "?")

            print(f"\n✅ SWAP SUCCESSFUL!")
            print(f"TX: {tx_hash}")

            if network == "base-sepolia":
                print(f"URL: https://sepolia.basescan.org/tx/{tx_hash}")
            else:
                print(f"URL: https://basescan.org/tx/{tx_hash}")

            print(f"Gas: {gas_used:,}")
            print(f"Amount in: {amount} {token_in}")
            print(f"Expected out: {expected_out} {token_out}")

            # Check final balances
            final_in = token_in_contract.functions.balanceOf(wallet_address).call()
            final_out = token_out_contract.functions.balanceOf(wallet_address).call()

            final_in_formatted = Decimal(str(final_in)) / Decimal(10**token_in_decimals)
            final_out_formatted = Decimal(str(final_out)) / Decimal(10**token_out_decimals)

            print(f"\nFinal balances:")
            print(f"  {token_in}: {final_in_formatted}")
            print(f"  {token_out}: {final_out_formatted}")

            actual_out = final_out_formatted - balance_out_formatted
            print(f"\nActual received: {actual_out} {token_out}")

        else:
            print(f"\n❌ SWAP FAILED!")
            print(f"Error: {result.get('error')}")

    except Exception as e:
        print(f"\n❌ Error during swap: {e}")
        logger.error(f"Swap error: {e}", exc_info=True)

    print("\n" + "=" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test Uniswap V3 swap"
    )
    parser.add_argument(
        "--amount",
        type=str,
        default="1",
        help="Amount to swap"
    )
    parser.add_argument(
        "--from",
        dest="token_in",
        type=str,
        default="USDC",
        help="Input token (default: USDC)"
    )
    parser.add_argument(
        "--to",
        dest="token_out",
        type=str,
        default="WETH",
        help="Output token (default: WETH)"
    )
    parser.add_argument(
        "--network",
        type=str,
        default="base-sepolia",
        help="Network (default: base-sepolia)"
    )

    args = parser.parse_args()

    try:
        amount = Decimal(args.amount)
    except:
        print(f"Error: Invalid amount '{args.amount}'")
        return

    asyncio.run(test_swap(amount, args.token_in, args.token_out, args.network))


if __name__ == "__main__":
    main()
