#!/usr/bin/env python3
"""Detect existing DeFi positions on Base mainnet.

This script scans Aave V3 and other protocols to find existing positions
and automatically records them in the PositionTracker for autonomous optimization.

Usage:
    poetry run python scripts/detect_existing_positions.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from decimal import Decimal

from src.blockchain.wallet import WalletManager
from src.agents.yield_scanner import YieldScannerAgent
from src.data.position_tracker import PositionTracker
from src.data.oracles import create_price_oracle
from src.data.database import Database
from src.security.audit import AuditLogger
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def main():
    """Detect and record existing positions."""
    settings = get_settings()

    print("=" * 60)
    print("     MAMMON - Position Detection on Base Mainnet")
    print("=" * 60)
    print(f"Network: {settings.network}")
    print()

    # Build config - must match run_autonomous_optimizer.py structure
    config = {
        "network": settings.network,
        "wallet_seed": settings.wallet_seed,
        "read_only": False,
        "dry_run_mode": settings.dry_run_mode,
        "use_mock_data": False,
        "use_local_wallet": settings.use_local_wallet,
        "base_rpc_url": settings.base_rpc_url,
        "chainlink_enabled": settings.chainlink_enabled,
        "chainlink_price_network": settings.chainlink_price_network,
        "chainlink_fallback_to_mock": settings.chainlink_fallback_to_mock,
        "max_transaction_value_usd": settings.max_transaction_value_usd,
        "daily_spending_limit_usd": settings.daily_spending_limit_usd,
        "min_apy_improvement": float(settings.min_apy_improvement),
        "min_profit_usd": float(settings.min_profit_usd),
        "max_break_even_days": settings.max_break_even_days,
        "max_cost_pct": float(settings.max_cost_pct),
    }

    # Initialize components
    print("Initializing components...")

    # Price oracle
    oracle = create_price_oracle(
        "chainlink" if config["chainlink_enabled"] else "mock",
        network=config["network"],
    )
    print("  ✅ Price oracle")

    # Wallet
    wallet = WalletManager(config=config, price_oracle=oracle)
    await wallet.initialize()
    wallet_address = wallet.address
    print(f"  ✅ Wallet: {wallet_address}")

    # Database & Position Tracker
    db_path = settings.database_url.replace("sqlite:///", "")
    database = Database(settings.database_url)
    database.create_all_tables()
    position_tracker = PositionTracker(db_path)
    print("  ✅ Position tracker")

    # Close all active positions before re-scanning to clear stale data
    closed_count = await position_tracker.close_all_positions(wallet_address=wallet_address)
    if closed_count > 0:
        print(f"  🧹 Closed {closed_count} stale position(s)")

    print()
    print("=" * 60)
    print("            Scanning for Existing Positions")
    print("=" * 60)
    print()

    # Track found positions
    total_positions = 0
    total_value_usd = Decimal("0")

    # Use YieldScannerAgent to scan all protocols
    print("🔍 Scanning protocols...")
    try:
        yield_scanner = YieldScannerAgent(config)

        # Scan all protocols (no audit_events parameter needed)
        opportunities = await yield_scanner.scan_all_protocols()
        print(f"Found {len(opportunities)} protocol pools total")
        print()

        # For each protocol, check if user has a position
        for opportunity in opportunities:
            protocol_name = opportunity.protocol
            pool_id = opportunity.pool_id

            try:
                # Get the protocol instance from yield scanner
                protocol_obj = None
                for proto in yield_scanner.protocols:
                    if proto.name == protocol_name:
                        protocol_obj = proto
                        break

                if not protocol_obj:
                    continue

                # Get user balance
                balance = await protocol_obj.get_user_balance(pool_id, wallet_address)

                if balance > 0:
                    # Found a position!
                    token_symbol = opportunity.tokens[0] if opportunity.tokens else "UNKNOWN"
                    current_apy = opportunity.apy

                    # Get USD value
                    token_price = await oracle.get_price(token_symbol)
                    value_usd = balance * token_price

                    print(f"✨ Found position in {protocol_name}:")
                    print(f"   Token: {token_symbol}")
                    print(f"   Amount: {balance:,.4f} {token_symbol}")
                    print(f"   Value: ${value_usd:,.2f}")
                    print(f"   APY: {current_apy:.2f}%")
                    print(f"   Pool: {pool_id}")
                    print()

                    # Record in position tracker
                    position_id = await position_tracker.record_position(
                        wallet_address=wallet_address,
                        protocol=protocol_name,
                        pool_id=pool_id,
                        token=token_symbol,
                        amount=balance,
                        value_usd=value_usd,
                        current_apy=current_apy,
                    )
                    print(f"   📝 Recorded as position #{position_id}")
                    print()

                    total_positions += 1
                    total_value_usd += value_usd

            except Exception as e:
                logger.debug(f"Error checking position in {pool_id}: {e}")
                continue

    except Exception as e:
        logger.error(f"Failed to scan protocols: {e}")
        print(f"❌ Error scanning protocols: {e}")

    print()
    print("=" * 60)
    print("                     Summary")
    print("=" * 60)
    print(f"Total Positions Found: {total_positions}")
    print(f"Total Portfolio Value: ${total_value_usd:,.2f}")
    print()

    if total_positions > 0:
        print("✅ Positions recorded in database")
        print("   MAMMON can now optimize these positions autonomously!")
        print()
        print("Next steps:")
        print("  1. Run: poetry run python scripts/run_autonomous_optimizer.py --duration 0.167 --dry-run")
        print("  2. Verify opportunities are detected")
        print("  3. Run with DRY_RUN=false to execute real rebalances")
    else:
        print("⚠️  No positions found")
        print("   Deploy capital to a protocol first:")
        print("   - Aave V3 USDC: ~3-5% APY (very safe)")
        print("   - Morpho markets: ~4-8% APY (moderate risk)")
        print()

    # Close connections
    position_tracker.close()


if __name__ == "__main__":
    asyncio.run(main())
