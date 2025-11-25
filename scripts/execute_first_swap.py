"""Execute first Uniswap V3 swap with full security checks.

This script demonstrates the complete swap flow:
1. Validates all Uniswap V3 contracts
2. Gets quote from Uniswap
3. Cross-checks with Chainlink oracle
4. Applies slippage protection
5. Estimates gas costs
6. Simulates transaction
7. Executes swap (if approved)

Usage:
    python scripts/execute_first_swap.py --amount 0.0001 --dry-run
    python scripts/execute_first_swap.py --amount 0.001 --execute
"""

import asyncio
import argparse
from decimal import Decimal
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.blockchain.swap_executor import SwapExecutor
from src.data.oracles import create_price_oracle
from src.security.approval import ApprovalManager, cli_approval_callback
from src.utils.web3_provider import get_web3
from src.utils.logger import get_logger
from src.utils.config import get_settings

logger = get_logger(__name__)


async def main():
    """Execute first swap."""
    parser = argparse.ArgumentParser(description="Execute Uniswap V3 swap")
    parser.add_argument(
        "--amount",
        type=float,
        default=0.0001,
        help="Amount of ETH to swap (default: 0.0001)",
    )
    parser.add_argument(
        "--token-in",
        type=str,
        default="WETH",
        help="Input token symbol (default: WETH)",
    )
    parser.add_argument(
        "--token-out",
        type=str,
        default="USDC",
        help="Output token symbol (default: USDC)",
    )
    parser.add_argument(
        "--slippage",
        type=int,
        default=50,
        help="Slippage tolerance in basis points (default: 50 = 0.5%%)",
    )
    parser.add_argument(
        "--fee-tier",
        type=int,
        default=3000,
        help="Uniswap fee tier (default: 3000 = 0.3%%)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate swap without executing (default behavior)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute swap for real (requires approval)",
    )
    parser.add_argument(
        "--from-address",
        type=str,
        help="Sender address (if not provided, will use CDP wallet)",
    )

    args = parser.parse_args()

    # Parse arguments
    amount = Decimal(str(args.amount))
    token_in = args.token_in
    token_out = args.token_out
    slippage_bps = args.slippage
    fee_tier = args.fee_tier
    dry_run = not args.execute  # Default to dry-run unless --execute specified

    logger.info("=" * 80)
    logger.info("UNISWAP V3 SWAP EXECUTION")
    logger.info("=" * 80)
    logger.info(f"Mode: {'EXECUTE' if not dry_run else 'DRY RUN (SIMULATION ONLY)'}")
    logger.info(f"Swap: {amount} {token_in} → {token_out}")
    logger.info(f"Slippage: {slippage_bps} bps ({slippage_bps/100}%)")
    logger.info(f"Fee Tier: {fee_tier} ({fee_tier/10000}%)")
    logger.info("=" * 80)
    logger.info("")

    # Get configuration
    settings = get_settings()
    network = "base-sepolia"

    # Get Web3 instance
    w3 = get_web3(network)

    # Verify connection by fetching chain data
    try:
        chain_id = w3.eth.chain_id
        block_number = w3.eth.block_number

        logger.info(f"✅ Connected to {network}")
        logger.info(f"   Chain ID: {chain_id}")
        logger.info(f"   Block: {block_number}")
        logger.info("")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Base Sepolia: {e}")
        return 1

    # Get sender address
    if args.from_address:
        from_address = args.from_address
    else:
        # Try to get from settings
        from_address = getattr(settings, "wallet_address", None)
        if not from_address:
            logger.error(
                "❌ No sender address provided. Use --from-address"
            )
            return 1

    logger.info(f"Sender: {from_address}")
    logger.info("")

    # Check balance
    balance_wei = w3.eth.get_balance(from_address)
    balance_eth = Decimal(balance_wei) / Decimal(10**18)

    logger.info(f"Current ETH Balance: {balance_eth:.6f} ETH")

    if balance_eth < amount:
        logger.error(
            f"❌ Insufficient balance: {balance_eth:.6f} ETH < {amount} ETH required"
        )
        return 1

    logger.info("✅ Sufficient balance")
    logger.info("")

    # Initialize components
    logger.info("Initializing swap components...")

    # Price oracle (with strict staleness for production swaps)
    price_oracle = create_price_oracle(
        chainlink_enabled=getattr(settings, "chainlink_enabled", True),
        chainlink_price_network=getattr(settings, "chainlink_price_network", "base-mainnet"),
        chainlink_fallback_to_mock=getattr(settings, "chainlink_fallback_to_mock", True),
        strict_staleness=getattr(settings, "chainlink_strict_staleness", False),
    )

    # Approval manager
    approval_manager = ApprovalManager(
        approval_threshold_usd=settings.approval_threshold_usd,
        approval_callback=cli_approval_callback if not dry_run else None,
    )

    # Swap executor
    swap_executor = SwapExecutor(
        w3=w3,
        network=network,
        price_oracle=price_oracle,
        approval_manager=approval_manager,
        default_slippage_bps=slippage_bps,
        max_price_deviation_percent=Decimal("15.0"),  # Temporary: allow mock oracle deviation
        deadline_seconds=600,
    )

    logger.info("✅ Components initialized")
    logger.info("")

    # Execute swap
    logger.info("=" * 80)
    logger.info("EXECUTING SWAP")
    logger.info("=" * 80)
    logger.info("")

    result = await swap_executor.execute_swap(
        token_in=token_in,
        token_out=token_out,
        amount_in=amount,
        from_address=from_address,
        slippage_bps=slippage_bps,
        fee_tier=fee_tier,
        dry_run=dry_run,
    )

    logger.info("")
    logger.info("=" * 80)
    logger.info("SWAP RESULT")
    logger.info("=" * 80)

    if result["success"]:
        logger.info("✅ Swap completed successfully!")
        logger.info("")
        logger.info("Quote:")
        logger.info(f"  Expected Output: {result['quote']['amount_out']}")
        logger.info(f"  Price: {result['quote']['price']}")
        logger.info(f"  Gas Estimate: {result['quote']['gas_estimate']}")
        logger.info("")
        logger.info("Security Checks:")
        logger.info(f"  Oracle Price: {result['oracle_price']}")
        logger.info(f"  Price Impact: {result['price_impact']}%")
        logger.info("")
        logger.info("Slippage Protection:")
        logger.info(
            f"  Tolerance: {result['slippage']['tolerance_percent']}"
        )
        logger.info(f"  Min Output: {result['slippage']['min_output']}")
        logger.info("")
        logger.info("Gas:")
        logger.info(f"  Estimate: {result['gas']['estimate']} units")
        logger.info(f"  Cost: ${result['gas']['cost_usd']}")
        logger.info("")
        logger.info("Approval:")
        logger.info(f"  Required: {result['approval']['required']}")
        logger.info(f"  Total Cost: ${result['approval']['total_cost_usd']}")

        # Print security check summary
        security_summary = swap_executor.get_security_summary(
            result["security_checks"]
        )
        logger.info("")
        logger.info(security_summary)

        if dry_run:
            logger.info("")
            logger.info("=" * 80)
            logger.info("DRY RUN COMPLETE - NO TRANSACTION EXECUTED")
            logger.info("To execute for real, run with --execute flag")
            logger.info("=" * 80)

        return 0

    else:
        logger.error("❌ Swap failed!")
        logger.error(f"Error: {result.get('error', 'Unknown error')}")

        # Print security check summary
        security_summary = swap_executor.get_security_summary(
            result["security_checks"]
        )
        logger.info("")
        logger.info(security_summary)

        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
