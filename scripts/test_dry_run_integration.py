"""Test the integration with dry run mode first."""

import asyncio
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.blockchain.swap_executor import SwapExecutor
from src.blockchain.wallet import WalletManager
from src.data.oracles import create_price_oracle
from src.security.approval import ApprovalManager
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings

async def main():
    print("\n" + "=" * 80)
    print("TESTING SWAP INTEGRATION (DRY RUN MODE)")
    print("=" * 80)

    # Initialize components
    network = "base-sepolia"
    w3 = get_web3(network)
    settings = get_settings()

    print(f"✅ Connected to {network}")

    # Get wallet address (from seed)
    from eth_account import Account

    # Derive wallet from seed
    if settings.wallet_seed:
        Account.enable_unaudited_hdwallet_features()
        account = Account.from_mnemonic(settings.wallet_seed)
        wallet_address = account.address
    else:
        wallet_address = "0x81A2933C185e45f72755B35110174D57b5E1FC88"
    balance_eth = Decimal(str(w3.eth.get_balance(wallet_address))) / Decimal(10**18)
    print(f"💰 Wallet: {wallet_address}")
    print(f"💰 Balance: {balance_eth:.6f} ETH")

    # Create oracle
    oracle = create_price_oracle(
        chainlink_enabled=True,
        chainlink_price_network="base-mainnet",
        chainlink_fallback_to_mock=True,
    )
    print("✅ Price oracle initialized")

    # Create approval manager
    approval_manager = ApprovalManager(
        approval_threshold_usd=Decimal("1000"),
    )
    print("✅ Approval manager initialized")

    # Create wallet manager for dry run
    wallet_manager = WalletManager(
        config={
            "wallet_seed": settings.wallet_seed,
            "network": network,
            "dry_run_mode": True,  # DRY RUN MODE
        },
        price_oracle=oracle,
        approval_manager=approval_manager,
    )
    await wallet_manager.initialize()
    print("✅ Wallet manager initialized (DRY RUN MODE)")

    # Create swap executor with wallet manager
    executor = SwapExecutor(
        w3=w3,
        network=network,
        price_oracle=oracle,
        approval_manager=approval_manager,
        wallet_manager=wallet_manager,
        default_slippage_bps=50,
        max_price_deviation_percent=Decimal("15.0"),
        deadline_seconds=600,
    )
    print("✅ Swap executor initialized with wallet manager")
    print()

    print("=" * 80)
    print("EXECUTING DRY RUN TEST")
    print("=" * 80)
    print()

    # Execute dry run
    result = await executor.execute_swap(
        token_in="WETH",
        token_out="USDC",
        amount_in=Decimal("0.0001"),
        from_address=wallet_address,
        dry_run=True,  # DRY RUN
    )

    if result['success']:
        print("✅ DRY RUN SUCCESSFUL!")
        print()

        # Show security checks
        security = result.get('security_checks')
        if security and hasattr(security, 'checks'):
            checks = security.checks
        else:
            checks = {}

        print("Security Checks:")
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check}")

        print()
        print("Quote Details:")
        quote = result.get('quote', {})
        print(f"  Amount In: {quote.get('amount_in', 'N/A')} ETH")
        print(f"  Expected Output: {quote.get('amount_out', 'N/A')} USDC")
        print(f"  Price: ${quote.get('price', 'N/A')} per ETH")

        print()
        print("Ready for real execution!")
    else:
        print("❌ DRY RUN FAILED")
        print(f"Error: {result.get('error', 'Unknown error')}")
        return 1

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)