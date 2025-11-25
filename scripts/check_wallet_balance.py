"""Check local wallet balance on network.

Verifies the wallet is funded and ready for transactions.
"""

import sys
from pathlib import Path
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from eth_account import Account
from eth_account.hdaccount import ETHEREUM_DEFAULT_PATH
from src.utils.config import get_settings
from src.utils.web3_provider import get_web3


def main():
    """Check and display wallet balance."""
    # Load configuration
    config = get_settings()

    if not config.wallet_seed:
        print("\n❌ ERROR: WALLET_SEED not found in .env\n")
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

    # Get Web3 instance
    try:
        w3 = get_web3(config.network)
    except Exception as e:
        print(f"\n❌ ERROR: Failed to connect to network: {e}\n")
        sys.exit(1)

    # Get balance
    try:
        balance_wei = w3.eth.get_balance(account.address)
        balance_eth = Decimal(balance_wei) / Decimal(10**18)
    except Exception as e:
        print(f"\n❌ ERROR: Failed to get balance: {e}\n")
        sys.exit(1)

    # Display results
    print("\n" + "="*70)
    print("MAMMON WALLET BALANCE")
    print("="*70)
    print(f"\nAddress: {account.address}")
    print(f"Network: {config.network}")
    print(f"Balance: {balance_eth} ETH")
    print("\n" + "="*70)

    # Check if sufficient for transactions
    min_balance = Decimal("0.002")
    recommended_balance = Decimal("0.05")

    if balance_eth >= recommended_balance:
        print("\n✅ Balance is excellent! Ready for multiple transactions.")
    elif balance_eth >= min_balance:
        print("\n✅ Balance sufficient for test transactions.")
        print(f"💡 Recommended balance: {recommended_balance} ETH")
    else:
        print("\n⚠️  Balance too low for transactions")
        print(f"   Current: {balance_eth} ETH")
        print(f"   Minimum: {min_balance} ETH")
        print(f"   Recommended: {recommended_balance} ETH")
        print(f"\n📤 Send ETH to: {account.address}")
        print(f"   Network: {config.network}")

    print("="*70 + "\n")


if __name__ == "__main__":
    main()
