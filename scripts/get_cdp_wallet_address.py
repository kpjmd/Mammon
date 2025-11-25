"""Get CDP wallet address using CDP SDK.

This script initializes the CDP wallet and prints the address.
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cdp import Cdp, Wallet
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    """Get CDP wallet address."""
    print("\n🔧 Initializing CDP Wallet...")
    print("=" * 60)

    # Get CDP credentials
    api_key = os.getenv("CDP_API_KEY")
    api_secret = os.getenv("CDP_API_SECRET")
    wallet_secret = os.getenv("CDP_WALLET_SECRET")

    if not all([api_key, api_secret]):
        print("❌ Missing CDP credentials in .env file")
        print("   Required: CDP_API_KEY, CDP_API_SECRET")
        return 1

    # Configure CDP
    Cdp.configure(api_key, api_secret)
    print("✅ CDP configured")

    # Import or create wallet
    if wallet_secret:
        print("📥 Importing existing wallet...")
        try:
            wallet = Wallet.import_data({"seed": wallet_secret})
            print("✅ Wallet imported")
        except Exception as e:
            print(f"❌ Error importing wallet: {e}")
            return 1
    else:
        print("❌ CDP_WALLET_SECRET not found in .env")
        print("   Cannot import wallet without secret")
        return 1

    # Get default address
    address = wallet.default_address.address_id

    print(f"\n{'=' * 60}")
    print(f"✅ CDP Wallet Address")
    print(f"{'=' * 60}\n")
    print(f"📍 Address: {address}")
    print(f"🌐 Network: base-sepolia")
    print(f"\n{'=' * 60}")
    print(f"💡 Use this address for the swap script with --from-address flag")
    print(f"{'=' * 60}\n")

    return 0


if __name__ == "__main__":
    exit(main())
