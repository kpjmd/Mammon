"""Export CDP wallet data for a specific address.

This script attempts to load a wallet from CDP and export its data
so it can be imported for persistence.

NOTE: This requires the CDP API key to have Export scope enabled.
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import get_settings
from src.blockchain.wallet import WalletManager
from src.data.oracles import create_price_oracle


async def export_wallet():
    """Export current CDP wallet data."""
    config = get_settings()

    print("=" * 80)
    print("CDP WALLET EXPORT")
    print("=" * 80)
    print(f"Network: {config.network}")
    print()

    # Initialize wallet
    print("🔍 Initializing CDP wallet...")
    wallet_config = {
        "cdp_api_key": config.cdp_api_key,
        "cdp_api_secret": config.cdp_api_secret,
        "cdp_wallet_secret": config.cdp_wallet_secret,
        "network": config.network,
        "dry_run_mode": config.dry_run_mode,
        "max_transaction_value_usd": float(config.max_transaction_value_usd),
        "daily_spending_limit_usd": float(config.daily_spending_limit_usd),
        "approval_threshold_usd": float(config.approval_threshold_usd),
        "max_gas_price_gwei": float(config.max_gas_price_gwei),
    }

    wallet = WalletManager(
        config=wallet_config,
        price_oracle=create_price_oracle("mock"),
        approval_manager=None,
    )

    await wallet.initialize()

    print(f"   Address: {wallet.address}")
    print()

    # Check if this is the target wallet
    target = "0x448a8502Cc51204662AafD9ac22ECaB794C2eB28"
    if wallet.address.lower() != target.lower():
        print(f"⚠️  WARNING: Loaded wallet {wallet.address}")
        print(f"   Target wallet: {target}")
        print()
        print("   The CDP wallet secret creates different wallets each time.")
        print("   We cannot export a specific wallet - CDP creates ephemeral wallets.")
        print()
        print("💡 ALTERNATIVE SOLUTION:")
        print("   Since CDP doesn't support persistent wallets with current setup,")
        print("   we need to either:")
        print("   1. Use CDP Smart Accounts (requires different CDP setup)")
        print("   2. Export private key from CDP dashboard manually")
        print("   3. Use a different wallet approach (local wallet with seed phrase)")
        print()
        return

    # Try to export wallet data
    print("📤 Exporting wallet data...")
    try:
        wallet_data = await wallet.export_wallet_data(require_confirmation=False)

        # Save to secure location
        export_file = Path(__file__).parent.parent / "wallet_export.json"
        with open(export_file, "w") as f:
            json.dump(wallet_data, f, indent=2)

        print(f"✅ Wallet exported successfully!")
        print(f"   Saved to: {export_file}")
        print()
        print("⚠️  SECURITY WARNING:")
        print("   - This file contains sensitive wallet data")
        print("   - DO NOT commit to git")
        print("   - Store securely and delete after import")
        print()
        print("📋 NEXT STEP:")
        print("   Run: poetry run python scripts/import_cdp_wallet.py")

    except Exception as e:
        print(f"❌ Export failed: {e}")
        print()
        print("This might be because:")
        print("1. CDP API key doesn't have Export scope")
        print("2. CDP AgentKit doesn't support wallet export")
        print("3. Wallet is ephemeral and can't be exported")

    print()
    print("=" * 80)


if __name__ == "__main__":
    import asyncio

    asyncio.run(export_wallet())
