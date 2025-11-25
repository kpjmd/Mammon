"""Simple first transaction execution: ETH → WETH wrap with manual funding.

This is a simplified version for Sprint 3 that works around CDP wallet persistence issues.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import get_settings
from src.blockchain.wallet import WalletManager
from src.utils.web3_provider import get_web3
from src.protocols.weth import WETHProtocol
from src.data.oracles import create_price_oracle


async def execute_first_wrap():
    """Execute first WETH wrap transaction."""
    config = get_settings()
    amount = Decimal("0.001")

    print("=" * 80)
    print("MAMMON FIRST TEST TRANSACTION - SPRINT 3")
    print("=" * 80)
    print(f"Transaction: ETH → WETH Wrap")
    print(f"Amount: {amount} ETH")
    print(f"Network: {config.network}")
    print()

    # Initialize components
    print("🔧 Initializing components...")
    w3 = get_web3(config.network)
    weth = WETHProtocol(w3, config.network)
    oracle = create_price_oracle("mock")  # Use mock for now

    # Initialize wallet
    print("🔧 Initializing wallet...")
    wallet_config = {
        "cdp_api_key": config.cdp_api_key,
        "cdp_api_secret": config.cdp_api_secret,
        "cdp_wallet_secret": config.cdp_wallet_secret,
        "use_local_wallet": config.use_local_wallet,
        "wallet_seed": config.wallet_seed,
        "network": config.network,
        "dry_run_mode": config.dry_run_mode,
        "max_transaction_value_usd": float(config.max_transaction_value_usd),
        "daily_spending_limit_usd": float(config.daily_spending_limit_usd),
        "approval_threshold_usd": float(config.approval_threshold_usd),
        "max_gas_price_gwei": float(config.max_gas_price_gwei),
        "max_priority_fee_gwei": float(config.max_priority_fee_gwei),
        "gas_buffer_simple": config.gas_buffer_simple,
        "gas_buffer_moderate": config.gas_buffer_moderate,
        "gas_buffer_complex": config.gas_buffer_complex,
    }

    wallet = WalletManager(
        config=wallet_config,
        price_oracle=oracle,
        approval_manager=None,
    )

    await wallet.initialize()
    wallet_address = wallet.address

    print(f"✅ Wallet initialized: {wallet_address}")
    print()

    # Check balance
    print("💰 Checking balance...")
    balance_wei = w3.eth.get_balance(wallet_address)
    balance_eth = Decimal(balance_wei) / Decimal(10**18)
    print(f"   Current balance: {balance_eth} ETH")

    min_balance = Decimal("0.002")
    if balance_eth < min_balance:
        print()
        print("=" * 80)
        print("⚠️  WALLET FUNDING REQUIRED")
        print("=" * 80)
        print()
        print(f"Address: {wallet_address}")
        print(f"Network: {config.network}")
        print(f"Need: {min_balance} ETH minimum")
        print()
        print("📤 Please send funds now, then press ENTER...")
        input()

        # Re-check
        balance_wei = w3.eth.get_balance(wallet_address)
        balance_eth = Decimal(balance_wei) / Decimal(10**18)
        print(f"✅ Balance: {balance_eth} ETH")

        if balance_eth < min_balance:
            print(f"❌ Still insufficient! Need {min_balance} ETH")
            return

    print()
    print("=" * 80)
    print("EXECUTING TRANSACTION")
    print("=" * 80)
    print()

    # Build transaction
    print("🔧 Building WETH wrap transaction...")
    tx = weth.build_wrap_transaction(wallet_address, amount)
    print(f"   To: {tx['to']}")
    print(f"   Value: {amount} ETH")
    print(f"   Gas: {tx['gas']}")
    print()

    # Execute via wallet
    print("🚀 Executing transaction...")
    try:
        result = await wallet.execute_transaction(
            to=tx['to'],
            amount=amount,
            data=tx.get('data', '0x'),
            token="ETH",
        )

        if result.get('success'):
            print(f"✅ Transaction successful!")
            print(f"   TX Hash: {result.get('tx_hash')}")
            print()
            print("🎉 SPRINT 3 FIRST TRANSACTION COMPLETE!")
        else:
            print(f"❌ Transaction failed: {result.get('error')}")

    except Exception as e:
        print(f"❌ Execution error: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 80)


if __name__ == "__main__":
    import asyncio
    asyncio.run(execute_first_wrap())
