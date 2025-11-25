"""List all wallets in CDP account and find the funded one.

This script uses the CDP API to list all wallets and their balances,
helping you identify which wallet to import for persistence.
"""

import sys
import requests
import json
from pathlib import Path
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import get_settings
from src.utils.web3_provider import get_web3


def list_cdp_wallets():
    """List all wallets in CDP account."""
    config = get_settings()

    print("=" * 80)
    print("CDP WALLET LISTING")
    print("=" * 80)
    print(f"Network: {config.network}")
    print(f"Target wallet: 0x448a8502Cc51204662AafD9ac22ECaB794C2eB28")
    print()

    # CDP API endpoint
    # Based on: https://docs.cdp.coinbase.com/server-wallets/v2/using-the-wallet-api/list-wallets
    base_url = "https://api.cdp.coinbase.com/platform"

    # Note: The exact endpoint depends on CDP API version
    # This is a placeholder - actual implementation needs CDP SDK
    print("⚠️  NOTE: CDP AgentKit doesn't expose wallet listing API directly")
    print("   We'll use Web3 to check balances of known wallet addresses")
    print()

    # Known wallet addresses from your dashboard
    known_wallets = [
        "0x448a8502Cc51204662AafD9ac22ECaB794C2eB28",  # Your funded wallet
        "0xf05DE660025dE90eFD1E394868a1f541825Ae56D",
        "0xA759e212eE641502f2d31b0401D2Fd358c026028",
        "0xd803Ee866bA6Af7536bACdA1b404fe4B08cDB96F",
        "0xEc282069814Ed78c48FcBeFcFf6020D2871A7c03",
    ]

    # Check balances using Web3
    w3 = get_web3(config.network)

    print("🔍 CHECKING WALLET BALANCES:")
    print("-" * 80)

    funded_wallets = []

    for address in known_wallets:
        try:
            balance_wei = w3.eth.get_balance(address)
            balance_eth = Decimal(balance_wei) / Decimal(10**18)

            status = "💰 FUNDED" if balance_eth > 0 else "   Empty"
            print(f"{status} | {address} | {balance_eth} ETH")

            if balance_eth > 0:
                funded_wallets.append((address, balance_eth))

        except Exception as e:
            print(f"   ERROR | {address} | {e}")

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if funded_wallets:
        print(f"✅ Found {len(funded_wallets)} funded wallet(s):")
        print()
        for address, balance in funded_wallets:
            print(f"   {address}")
            print(f"   Balance: {balance} ETH")
            print()

        if len(funded_wallets) == 1:
            target_address = funded_wallets[0][0]
            print("📋 NEXT STEPS:")
            print(f"   1. This wallet will be imported: {target_address}")
            print(f"   2. Run: poetry run python scripts/export_cdp_wallet.py {target_address}")
            print()
    else:
        print("⚠️  No funded wallets found")
        print("   Please fund one of the wallets above before proceeding")

    print("=" * 80)


if __name__ == "__main__":
    list_cdp_wallets()
