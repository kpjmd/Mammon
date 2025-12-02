"""Quick test script for Moonwell position detection."""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.protocols.moonwell import MoonwellProtocol
from src.utils.config import get_settings

async def main():
    """Test Moonwell get_user_balance implementation."""
    import os
    print("🧪 Testing Moonwell position detection...")

    settings = get_settings()

    # Initialize Moonwell protocol
    moonwell = MoonwellProtocol({
        "network": "base-mainnet",
        "read_only": True,
    })

    # Get wallet address from environment
    wallet_address = os.getenv("WALLET_ADDRESS")
    if not wallet_address:
        print("❌ WALLET_ADDRESS not found in environment")
        return
    print(f"📍 Wallet: {wallet_address}")

    # Test USDC balance (where the position should be)
    print("\n🔍 Checking Moonwell USDC balance...")
    try:
        balance = await moonwell.get_user_balance("moonwell-usdc", wallet_address)
        print(f"✅ USDC Balance: {balance}")

        if balance > Decimal("0"):
            print(f"🎉 SUCCESS! Detected {balance} USDC in Moonwell")
        else:
            print("⚠️  No USDC position found (balance = 0)")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
