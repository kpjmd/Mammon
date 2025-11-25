"""Get CDP wallet address for funding.

This script initializes the CDP wallet and prints the address
so you can fund it with Base Sepolia testnet ETH.
"""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.config import get_settings
from src.blockchain.wallet import WalletManager
from src.data.oracles import create_price_oracle


async def main():
    """Initialize wallet and print address for funding."""
    print("\n🔧 Initializing CDP Wallet...")
    print("="*60)

    settings = get_settings()

    config = {
        "cdp_api_key": settings.cdp_api_key,
        "cdp_api_secret": settings.cdp_api_secret,
        "cdp_wallet_secret": settings.cdp_wallet_secret,
        "network": settings.network,
        "dry_run_mode": False,  # Need real wallet address
    }

    wallet = WalletManager(
        config=config,
        price_oracle=create_price_oracle("mock"),
        approval_manager=None,
    )

    try:
        await wallet.initialize()

        print(f"\n{'='*60}")
        print(f"✅ CDP Wallet Initialized Successfully")
        print(f"{'='*60}\n")
        print(f"📍 Wallet Address: {wallet.address}")
        print(f"🌐 Network: {wallet.network}")
        print(f"{'='*60}\n")

        # Check current balance
        try:
            balance = await wallet.get_balance("ETH")
            print(f"💰 Current Balance: {balance} ETH")

            if balance > 0:
                print(f"✅ Wallet already funded!")
            else:
                print(f"⚠️  Wallet needs funding")
        except Exception as e:
            print(f"ℹ️  Could not check balance: {e}")

        print(f"\n{'='*60}")
        print(f"📋 Funding Instructions:")
        print(f"{'='*60}\n")
        print(f"Option 1 - Use Faucet:")
        print(f"  https://faucet.quicknode.com/base/sepolia")
        print(f"\nOption 2 - Manual Transfer:")
        print(f"  Transfer 0.5 ETH from your funded wallet")
        print(f"  Network: Base Sepolia")
        print(f"  To: {wallet.address}")
        print(f"\n💡 Minimum needed: 0.01 ETH (tests use ~0.0012 ETH)")
        print(f"{'='*60}\n")

    except Exception as e:
        print(f"\n❌ Error initializing wallet: {e}")
        print(f"\nPlease check your .env configuration:")
        print(f"  - CDP_API_KEY")
        print(f"  - CDP_API_SECRET")
        print(f"  - CDP_WALLET_SECRET")
        raise


if __name__ == "__main__":
    asyncio.run(main())
