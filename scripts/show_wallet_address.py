"""Display wallet address derived from seed phrase.

Shows the Ethereum address for the local wallet without requiring network connection.
Useful for funding the wallet before first transaction.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eth_account import Account
from eth_account.hdaccount import ETHEREUM_DEFAULT_PATH
from src.utils.config import get_settings


def main():
    """Display wallet address from configured seed phrase."""
    # Load configuration
    config = get_settings()

    if not config.wallet_seed:
        print("\n❌ ERROR: WALLET_SEED not found in .env")
        print("\nPlease either:")
        print("1. Run: poetry run python scripts/generate_seed.py")
        print("2. Or add existing seed to .env as: WALLET_SEED=\"your twelve words\"")
        print()
        sys.exit(1)

    # Enable HD wallet features
    Account.enable_unaudited_hdwallet_features()

    # Derive account from seed
    try:
        account = Account.from_mnemonic(
            config.wallet_seed,
            account_path=ETHEREUM_DEFAULT_PATH
        )
    except Exception as e:
        print(f"\n❌ ERROR: Invalid seed phrase: {e}\n")
        sys.exit(1)

    # Display wallet info
    print("\n" + "="*70)
    print("MAMMON LOCAL WALLET")
    print("="*70)
    print(f"\nAddress: {account.address}")
    print(f"Network: {config.network}")
    print(f"Derivation Path: {ETHEREUM_DEFAULT_PATH}")
    print("\n" + "="*70)
    print("\n📤 To fund this wallet:")
    print(f"   1. Send ETH to: {account.address}")
    print(f"   2. Network: {config.network}")
    print("   3. Minimum: 0.002 ETH (for testing)")
    print("\n💡 Tip: This address is persistent - it will be the same every time")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
