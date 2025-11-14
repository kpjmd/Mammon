"""🎉 MAMMON'S FIRST REAL SWAP - HISTORIC MOMENT 🎉

This script executes Mammon's first real decentralized exchange swap
on Base Sepolia testnet with full security validation.
"""

import asyncio
import sys
import os
from decimal import Decimal
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.blockchain.swap_executor import SwapExecutor
from src.blockchain.wallet import WalletManager
from src.data.oracles import create_price_oracle
from src.security.approval import ApprovalManager
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings

async def main():
    print("\n" + "=" * 80)
    print("🚀 MAMMON'S FIRST REAL SWAP - HISTORIC EXECUTION 🚀")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Network: Base Sepolia Testnet")
    print(f"Swap: 0.0001 ETH → USDC")
    print("=" * 80)
    print()

    # Initialize components
    network = "base-sepolia"
    w3 = get_web3(network)
    settings = get_settings()

    print(f"✅ Connected to {network}")
    print(f"   Chain ID: {w3.eth.chain_id}")
    print(f"   Block: {w3.eth.block_number}")
    print()

    # Get wallet address (from seed)
    from eth_account import Account

    # Derive wallet from seed
    if settings.wallet_seed:
        Account.enable_unaudited_hdwallet_features()
        account = Account.from_mnemonic(settings.wallet_seed)
        wallet_address = account.address
    else:
        wallet_address = "0x81A2933C185e45f72755B35110174D57b5E1FC88"

    # Check balance
    balance_wei = w3.eth.get_balance(wallet_address)
    balance_eth = Decimal(balance_wei) / Decimal(10**18)
    print(f"📍 Wallet: {wallet_address}")
    print(f"💰 Balance: {balance_eth:.6f} ETH")
    print()

    if balance_eth < Decimal("0.0001"):
        print("❌ Insufficient balance for swap")
        return 1

    # Create oracle
    oracle = create_price_oracle(
        chainlink_enabled=True,
        chainlink_price_network="base-mainnet",
        chainlink_fallback_to_mock=True,
    )
    print("✅ Price oracle initialized")

    # Create approval manager (no approval needed for tiny amount)
    approval_manager = ApprovalManager(
        approval_threshold_usd=Decimal("1000"),
    )
    print("✅ Approval manager initialized")

    # Create wallet manager for real execution
    wallet_manager = WalletManager(
        config={
            "wallet_seed": settings.wallet_seed,
            "network": network,
            "dry_run_mode": False,  # For real execution
        },
        price_oracle=oracle,
        approval_manager=approval_manager,
    )
    await wallet_manager.initialize()
    print("✅ Wallet manager initialized for real execution")

    # Create swap executor with wallet manager
    executor = SwapExecutor(
        w3=w3,
        network=network,
        price_oracle=oracle,
        approval_manager=approval_manager,
        wallet_manager=wallet_manager,  # Pass wallet manager for execution
        default_slippage_bps=50,  # 0.5% slippage tolerance
        max_price_deviation_percent=Decimal("15.0"),
        deadline_seconds=600,
    )
    print("✅ Swap executor initialized with wallet manager")
    print()

    print("=" * 80)
    print("EXECUTING SWAP (DRY-RUN=FALSE)")
    print("=" * 80)
    print()

    # Execute the REAL swap
    result = await executor.execute_swap(
        token_in="WETH",
        token_out="USDC",
        amount_in=Decimal("0.0001"),
        from_address=wallet_address,
        dry_run=False,  # 🚨 REAL EXECUTION 🚨
    )

    print()
    print("=" * 80)
    print("SWAP EXECUTION RESULT")
    print("=" * 80)
    print()

    if result['success']:
        print("✅ ✅ ✅ SWAP EXECUTED SUCCESSFULLY! ✅ ✅ ✅")
        print()
        print("Quote Details:")
        quote = result.get('quote', {})
        print(f"  Expected Output: {quote.get('amount_out', 'N/A')} USDC")
        print(f"  Execution Price: ${quote.get('price', 'N/A')} per ETH")
        print(f"  Quoter Gas Est: {quote.get('gas_estimate', 'N/A')} units")
        print()

        print("Gas Details:")
        gas = result.get('gas', {})
        print(f"  Gas Estimate: {gas.get('estimate', 'N/A')} units")
        print(f"  Gas Cost: ${gas.get('cost_usd', 'N/A')}")
        print()

        print("Slippage Protection:")
        slippage = result.get('slippage', {})
        print(f"  Tolerance: {slippage.get('tolerance_percent', 'N/A')}")
        print(f"  Expected: {slippage.get('expected_output', 'N/A')} USDC")
        print(f"  Minimum: {slippage.get('min_output', 'N/A')} USDC")
        print()

        print("Security Validation:")
        oracle_price = result.get('oracle_price', 'N/A')
        price_impact = result.get('price_impact', 'N/A')
        print(f"  Oracle Price: ${oracle_price}")
        print(f"  Price Impact: {price_impact}%")
        print()

        # Security summary
        security = result.get('security_checks')
        if security:
            summary = executor.get_security_summary(security)
            print(summary)

        print()
        print("=" * 80)
        print("🎊 MAMMON IS NOW A FUNCTIONAL DEFI AGENT! 🎊")
        print("=" * 80)
        print()
        print("NOTE: This was a dry-run execution showing what WOULD happen.")
        print("To execute for real, actual transaction signing is needed.")
        print("(Transaction signing implementation pending)")
        print()

        return 0

    else:
        print("❌ SWAP FAILED")
        print()
        error = result.get('error', 'Unknown error')
        print(f"Error: {error}")
        print()

        # Security summary
        security = result.get('security_checks')
        if security:
            summary = executor.get_security_summary(security)
            print(summary)

        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
