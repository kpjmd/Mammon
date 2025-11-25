"""Simple first transaction execution: ETH → ETH transfer (to self).

This is a simplified test that sends a small amount of ETH to your own address.
Validates all security layers without complex contract interactions.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import get_settings
from src.blockchain.wallet import WalletManager
from src.utils.web3_provider import get_web3
from src.data.oracles import create_price_oracle


async def execute_first_transfer():
    """Execute first simple ETH transfer (to self)."""
    config = get_settings()
    amount = Decimal("0.0001")  # Very small amount for testing

    print("=" * 80)
    print("MAMMON FIRST SIMPLE TRANSACTION TEST")
    print("=" * 80)
    print(f"Transaction: ETH → ETH Transfer (to self)")
    print(f"Amount: {amount} ETH")
    print(f"Network: {config.network}")
    print()

    # Initialize components
    print("🔧 Initializing components...")
    w3 = get_web3(config.network)
    oracle = create_price_oracle("mock")  # Use mock for now

    # Initialize wallet
    print("🔧 Initializing wallet...")
    wallet_config = {
        "cdp_api_key": config.cdp_api_key,
        "cdp_api_secret": config.cdp_api_secret,
        "cdp_wallet_secret": config.cdp_wallet_secret,
        "use_local_wallet": config.use_local_wallet,
        "wallet_seed": config.wallet_seed,
        "network": config.network,
        "dry_run_mode": config.dry_run_mode,
        "max_transaction_value_usd": float(config.max_transaction_value_usd),
        "daily_spending_limit_usd": float(config.daily_spending_limit_usd),
        "approval_threshold_usd": float(config.approval_threshold_usd),
        "max_gas_price_gwei": float(config.max_gas_price_gwei),
        "max_priority_fee_gwei": float(config.max_priority_fee_gwei),
        "gas_buffer_simple": config.gas_buffer_simple,
        "gas_buffer_moderate": config.gas_buffer_moderate,
        "gas_buffer_complex": config.gas_buffer_complex,
    }

    wallet = WalletManager(
        config=wallet_config,
        price_oracle=oracle,
        approval_manager=None,
    )

    await wallet.initialize()
    wallet_address = wallet.address

    print(f"✅ Wallet initialized: {wallet_address}")
    print()

    # Check balance
    print("💰 Checking balance...")
    balance_wei = w3.eth.get_balance(wallet_address)
    balance_eth = Decimal(balance_wei) / Decimal(10**18)
    print(f"   Current balance: {balance_eth} ETH")

    min_balance = Decimal("0.002")
    if balance_eth < min_balance:
        print()
        print("=" * 80)
        print("⚠️  WALLET FUNDING REQUIRED")
        print("=" * 80)
        print()
        print(f"Address: {wallet_address}")
        print(f"Network: {config.network}")
        print(f"Current: {balance_eth} ETH")
        print(f"Need: {min_balance} ETH minimum")
        print()
        print("📤 Please send funds now, then press ENTER...")
        input()

        # Re-check
        balance_wei = w3.eth.get_balance(wallet_address)
        balance_eth = Decimal(balance_wei) / Decimal(10**18)
        print(f"✅ Balance: {balance_eth} ETH")

        if balance_eth < min_balance:
            print(f"❌ Still insufficient! Need {min_balance} ETH")
            return

    print()
    print("=" * 80)
    print("EXECUTING SIMPLE ETH TRANSFER")
    print("=" * 80)
    print()

    # Simple transfer to self (no contract interaction)
    print(f"🚀 Sending {amount} ETH to self...")
    print(f"   From: {wallet_address}")
    print(f"   To:   {wallet_address}")
    print()

    # Execute via wallet
    try:
        result = await wallet.execute_transaction(
            to=wallet_address,  # Send to self
            amount=amount,
            data="0x",  # No data - simple transfer
            token="ETH",
        )

        if result.get('success'):
            print(f"✅ Transaction successful!")
            print(f"   TX Hash: {result.get('tx_hash')}")
            print()
            print("🎉 FIRST SIMPLE TRANSACTION COMPLETE!")
            print()
            print("Next steps:")
            print("1. Check audit.log for transaction details and gas metrics")
            print("2. Verify transaction on Arbiscan:")
            print(f"   https://sepolia.arbiscan.io/tx/{result.get('tx_hash')}")
        else:
            print(f"❌ Transaction failed: {result.get('error')}")

    except Exception as e:
        print(f"❌ Execution error: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 80)


if __name__ == "__main__":
    import asyncio
    asyncio.run(execute_first_transfer())
