"""Generate new BIP-39 seed phrase for local wallet.

One-time utility to create a new seed phrase. Save the output securely offline.

SECURITY WARNING:
- Anyone with this seed phrase can access your wallet and funds
- Never commit this to version control
- Never share with anyone
- Store securely offline (paper backup recommended)
"""

from eth_account import Account
from eth_account.hdaccount import generate_mnemonic, ETHEREUM_DEFAULT_PATH


def main():
    """Generate and display new wallet seed phrase."""
    # Enable HD wallet features
    Account.enable_unaudited_hdwallet_features()

    # Generate new 12-word mnemonic
    mnemonic = generate_mnemonic(12, "english")

    # Derive account to show address
    account = Account.from_mnemonic(mnemonic, account_path=ETHEREUM_DEFAULT_PATH)

    print("\n" + "="*70)
    print("NEW WALLET GENERATED")
    print("="*70)
    print(f"\nAddress: {account.address}")
    print(f"Derivation Path: {ETHEREUM_DEFAULT_PATH}")
    print(f"\nSeed Phrase (KEEP SECURE):")
    print(f"{mnemonic}")
    print("\nAdd to .env:")
    print(f'WALLET_SEED="{mnemonic}"')
    print("\n" + "="*70)
    print("\n⚠️  CRITICAL SECURITY WARNINGS:")
    print("⚠️  1. Save this seed phrase securely offline (write on paper)")
    print("⚠️  2. Anyone with this phrase can access your funds")
    print("⚠️  3. Never commit to version control or share")
    print("⚠️  4. This terminal output will not be saved")
    print("⚠️  5. Test with small amounts first")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
