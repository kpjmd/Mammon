"""Simple test of swap execution."""

import asyncio
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.blockchain.swap_executor import SwapExecutor
from src.data.oracles import create_price_oracle
from src.security.approval import ApprovalManager
from src.utils.web3_provider import get_web3

async def main():
    print("=" * 60)
    print("SIMPLE SWAP TEST")
    print("=" * 60)

    network = "base-sepolia"
    w3 = get_web3(network)

    print(f"Connected to {network}")
    print(f"Chain ID: {w3.eth.chain_id}")
    print()

    # Create oracle
    oracle = create_price_oracle(
        chainlink_enabled=True,
        chainlink_price_network="base-mainnet",
        chainlink_fallback_to_mock=True,
    )

    print("Oracle created")

    # Create approval manager
    approval_manager = ApprovalManager(
        approval_threshold_usd=Decimal("1000"),  # High threshold
    )

    print("Approval manager created")

    # Create swap executor
    executor = SwapExecutor(
        w3=w3,
        network=network,
        price_oracle=oracle,
        approval_manager=approval_manager,
        default_slippage_bps=50,
        max_price_deviation_percent=Decimal("15.0"),
        deadline_seconds=600,
    )

    print("Swap executor created")
    print()

    # Execute swap
    print("Executing swap...")
    result = await executor.execute_swap(
        token_in="WETH",
        token_out="USDC",
        amount_in=Decimal("0.0001"),
        from_address="0x81A2933C185e45f72755B35110174D57b5E1FC88",
        dry_run=True,
    )

    print()
    print("=" * 60)
    print("RESULT:")
    print("=" * 60)
    print(f"Success: {result['success']}")
    if result['success']:
        print(f"Quote: {result.get('quote', {})}")
        print(f"Gas: {result.get('gas', {})}")
    else:
        print(f"Error: {result.get('error', 'Unknown')}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
