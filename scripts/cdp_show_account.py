#!/usr/bin/env python3
"""Resolve and print the persistent CDP MPC account address. READ-ONLY.

Use this before cutting over to CDP custody:

    poetry run python scripts/cdp_show_account.py

Run it twice. The address MUST be identical both times -- that is the proof
that the "new wallet every run" persistence bug is dead. Then fund that
address, set CDP_EXPECTED_ADDRESS to it, and set USE_LOCAL_WALLET=false.

This script only reads. It never transfers, signs, or spends. It prints no
secret material -- only the public address.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import get_settings  # noqa: E402
from src.utils.web3_provider import get_web3  # noqa: E402
from src.wallet.cdp_mpc_provider import CdpMpcWalletProvider  # noqa: E402


def main() -> int:
    """Resolve the named CDP account and report its address and balance.

    Returns:
        Process exit code: 0 on success, 1 on failure.
    """
    settings = get_settings()

    print("=" * 70)
    print("CDP MPC Server Wallet - account resolution (READ-ONLY)")
    print("=" * 70)
    print(f"Network:      {settings.network}")
    print(f"Account name: {settings.cdp_account_name}")
    if settings.cdp_expected_address:
        print(f"Expected:     {settings.cdp_expected_address}")
    print("-" * 70)

    provider = None
    try:
        provider = CdpMpcWalletProvider(
            api_key_id=settings.cdp_api_key,
            api_key_secret=settings.cdp_api_secret,
            wallet_secret=settings.cdp_wallet_secret,
            network=settings.network,
            web3=get_web3(settings.network, config=settings),
            account_name=settings.cdp_account_name,
            expected_address=settings.cdp_expected_address,
        )

        address = provider.get_address()
        balance = provider.get_balance("ETH")

        print(f"✅ Resolved address: {address}")
        print(f"   ETH balance:     {balance}")
        print("-" * 70)
        print("Run this script again -- the address must be IDENTICAL.")
        print("If it is, custody is persistent and safe to fund.")
        if not settings.cdp_expected_address:
            print("")
            print("Once funded, set CDP_EXPECTED_ADDRESS to this address so a")
            print("mistyped account name can never silently run against an")
            print("empty wallet.")
        return 0

    except Exception as e:
        print(f"❌ Failed to resolve CDP account: {e}")
        print("")
        print("Check that CDP_API_KEY / CDP_API_SECRET / CDP_WALLET_SECRET are")
        print("set and that the network is supported by CDP.")
        return 1

    finally:
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    sys.exit(main())
