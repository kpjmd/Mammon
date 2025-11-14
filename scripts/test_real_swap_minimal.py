"""Minimal test for real swap execution."""

import asyncio
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.blockchain.swap_executor import SwapExecutor
from src.blockchain.wallet import WalletManager
from src.data.oracles import create_price_oracle
from src.security.approval import ApprovalManager
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings
from eth_account import Account

async def main():
    print("\n🚀 TESTING REAL SWAP EXECUTION...")

    # Initialize
    network = "base-sepolia"
    w3 = get_web3(network)
    settings = get_settings()

    # Get wallet address
    if settings.wallet_seed:
        Account.enable_unaudited_hdwallet_features()
        account = Account.from_mnemonic(settings.wallet_seed)
        wallet_address = account.address
    else:
        wallet_address = "0x81A2933C185e45f72755B35110174D57b5E1FC88"

    balance = Decimal(str(w3.eth.get_balance(wallet_address))) / Decimal(10**18)
    print(f"Wallet: {wallet_address}")
    print(f"Balance: {balance:.6f} ETH")

    # Create components
    oracle = create_price_oracle(
        chainlink_enabled=True,
        chainlink_price_network="base-mainnet",
        chainlink_fallback_to_mock=True,
    )

    approval_manager = ApprovalManager(
        approval_threshold_usd=Decimal("1000"),
    )

    # Create wallet manager for REAL execution
    print("\n⚠️  Creating wallet manager for REAL EXECUTION...")
    wallet_manager = WalletManager(
        config={
            "wallet_seed": settings.wallet_seed,
            "network": network,
            "dry_run_mode": False,  # REAL EXECUTION
        },
        price_oracle=oracle,
        approval_manager=approval_manager,
    )
    await wallet_manager.initialize()
    print("✅ Wallet manager ready for real transactions")

    # Create swap executor
    executor = SwapExecutor(
        w3=w3,
        network=network,
        price_oracle=oracle,
        approval_manager=approval_manager,
        wallet_manager=wallet_manager,
        default_slippage_bps=50,
        max_price_deviation_percent=Decimal("15.0"),
        deadline_seconds=600,
    )

    print("\n🔄 Executing REAL swap (0.0001 ETH → USDC)...")
    print("⚠️  THIS WILL USE REAL FUNDS ON BASE SEPOLIA\n")

    # Execute REAL swap
    result = await executor.execute_swap(
        token_in="WETH",
        token_out="USDC",
        amount_in=Decimal("0.0001"),
        from_address=wallet_address,
        dry_run=False,  # REAL EXECUTION
    )

    if result.get('success'):
        print("\n✅ SWAP SUCCESSFUL!")

        if result.get('executed'):
            print(f"🎉 TRANSACTION EXECUTED!")
            print(f"TX Hash: {result.get('tx_hash', 'N/A')}")
            print(f"Confirmations: {result.get('confirmations', 0)}")
            print(f"Balance change: {result.get('balance_change_eth', 'N/A')} ETH")
        else:
            print("Note:", result.get('note', 'Transaction not executed'))
    else:
        print(f"\n❌ SWAP FAILED: {result.get('error', 'Unknown error')}")

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)