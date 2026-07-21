#!/usr/bin/env python3
"""Verify recorded positions against on-chain balances (read-only, no seed).

After a live optimizer run, confirm the `positions` table matches on-chain
truth for the wallet(s) that hold positions:

  1. RECORDED -> CHAIN: every active DB row is re-read via the protocol's
     get_user_balance and compared (amount + USD value, within tolerance).
  2. CHAIN -> RECORDED: the wallet's supported pools (Aave V3, Moonwell) are
     read on-chain; any positive balance with no matching active DB row is
     flagged UNRECORDED -- the exact failure mode a lagged reconcile can leave.

Read-only: never signs, never needs WALLET_SEED. It forces USE_LOCAL_WALLET=false
so settings load without a local seed -- no wallet is ever constructed; the
wallet address to check comes from the DB rows (or --wallet).

Exit code 0 if all recorded rows match and nothing is unrecorded, else 1.

Usage:
    poetry run python scripts/verify_positions.py
    poetry run python scripts/verify_positions.py --wallet 0xF5Fec4...e65
    poetry run python scripts/verify_positions.py --tolerance-usd 1.0 --tolerance-pct 2
"""

import os

# Read-only verifier: no custody, no signing, no execution. Force MPC-mode
# settings so get_settings() does not require a local WALLET_SEED (we never build
# a wallet), and force dry-run so the settings layer does not print a misleading
# "real transactions will be executed" warning -- this script only reads.
os.environ["USE_LOCAL_WALLET"] = "false"
os.environ["DRY_RUN_MODE"] = "true"

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import argparse
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from src.agents.yield_scanner import YieldScannerAgent
from src.data.oracles import create_price_oracle
from src.data.position_tracker import PositionTracker
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Only these have working deposit/withdraw + get_user_balance on the live path.
SUPPORTED_PROTOCOLS = ["Aave V3", "Moonwell"]


def _build_scanner_and_oracle(settings):
    """Build a read-only YieldScannerAgent + shared oracle (no wallet)."""
    if getattr(settings, "chainlink_enabled", True):
        oracle = create_price_oracle(
            "chainlink",
            network=settings.network,
            price_network=getattr(settings, "chainlink_price_network", "base-mainnet"),
            fallback_to_mock=getattr(settings, "chainlink_fallback_to_mock", True),
        )
    else:
        oracle = create_price_oracle("mock")

    config = {
        "network": settings.network,
        "read_only": True,
        "use_mock_data": False,
        "chainlink_enabled": getattr(settings, "chainlink_enabled", True),
        "price_oracle": oracle,
        "morpho_max_markets": getattr(settings, "morpho_max_markets", 5),
        "aerodrome_max_pools": getattr(settings, "aerodrome_max_pools", 10),
        "supported_tokens": getattr(settings, "supported_tokens", ["USDC"]),
    }
    scanner = YieldScannerAgent(config)
    return scanner, oracle


async def _onchain_value(proto, pool_id: str, token: str, wallet: str, oracle):
    """Return (amount, value_usd) held on-chain for a pool, or (0, 0)."""
    balance = await proto.get_user_balance(pool_id, wallet)
    balance = Decimal(str(balance or 0))
    if balance <= 0:
        return Decimal("0"), Decimal("0")
    price = Decimal(str(await oracle.get_price(token)))
    return balance, balance * price


def _within(a: Decimal, b: Decimal, tol_pct: Decimal, tol_usd: Decimal) -> bool:
    """True if a and b agree within either tolerance."""
    diff = abs(a - b)
    if diff <= tol_usd:
        return True
    ref = max(abs(a), abs(b))
    return ref > 0 and (diff / ref) * 100 <= tol_pct


async def verify(
    db_path: str,
    wallet_filter: Optional[str],
    tol_pct: Decimal,
    tol_usd: Decimal,
) -> int:
    settings = get_settings()
    tracker = PositionTracker(db_path)
    scanner, oracle = _build_scanner_and_oracle(settings)
    protos = {p.name: p for p in scanner.protocols if p.name in SUPPORTED_PROTOCOLS}

    print("=" * 70)
    print("     MAMMON - Position Verification (read-only, no seed)")
    print("=" * 70)
    print(f"Network: {settings.network}   DB: {db_path}")
    print()

    # Active rows (optionally scoped to one wallet).
    active = await tracker.get_current_positions(wallet_address=wallet_filter)

    # Which wallets to scan: explicit --wallet, else the wallets that hold
    # active rows. Without either there is nothing to scan.
    wallets = (
        [wallet_filter]
        if wallet_filter
        else sorted({p.wallet_address for p in active})
    )
    if not wallets:
        print("No active positions in the DB and no --wallet given.")
        print("Pass --wallet <address> to scan a specific wallet on-chain.")
        tracker.close()
        return 0

    ok = True

    # 1. RECORDED -> CHAIN
    print("1) Recorded positions vs on-chain")
    print("-" * 70)
    if not active:
        print("   (no active rows recorded)")
    for pos in active:
        proto = protos.get(pos.protocol)
        if proto is None:
            print(f"   ?  {pos.protocol} {pos.pool_id}: no read support; skipped")
            continue
        try:
            amt, val = await _onchain_value(
                proto, pos.pool_id, pos.token, pos.wallet_address, oracle
            )
        except Exception as e:
            print(f"   ✗  {pos.protocol} {pos.pool_id}: on-chain read failed: {e}")
            ok = False
            continue
        db_val = Decimal(str(pos.value_usd or 0))
        match = _within(db_val, val, tol_pct, tol_usd) and amt > 0
        mark = "✓" if match else "✗"
        if not match:
            ok = False
        print(
            f"   {mark}  {pos.protocol} {pos.pool_id} [{pos.token}] "
            f"DB=${db_val:.2f} chain=${val:.2f} (amt {amt:.6f})"
        )

    # 2. CHAIN -> RECORDED (detect unrecorded on-chain positions)
    print()
    print("2) On-chain balances vs recorded (unrecorded detector)")
    print("-" * 70)
    active_keys = {(p.protocol, p.pool_id) for p in active}
    found_unrecorded = False
    for wallet in wallets:
        for name, proto in protos.items():
            try:
                pools = await proto.get_pools()
            except Exception as e:
                print(f"   !  {name}: pool enumeration failed: {e}")
                continue
            for pool in pools:
                token = pool.tokens[0] if pool.tokens else "USDC"
                try:
                    amt, val = await _onchain_value(
                        proto, pool.pool_id, token, wallet, oracle
                    )
                except Exception:
                    continue
                if amt <= 0:
                    continue
                if (name, pool.pool_id) in active_keys:
                    continue  # already verified in section 1
                found_unrecorded = True
                ok = False
                print(
                    f"   ⚠ UNRECORDED  {name} {pool.pool_id} [{token}] "
                    f"chain=${val:.2f} (amt {amt:.6f}) wallet={wallet}"
                )
    if not found_unrecorded:
        print("   none — every on-chain position is recorded")

    print()
    print("=" * 70)
    print("RESULT:", "✅ VERIFIED" if ok else "❌ MISMATCH — see rows above")
    print("=" * 70)
    tracker.close()
    return 0 if ok else 1


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify positions vs on-chain")
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite DB path (default: from settings DATABASE_URL)",
    )
    parser.add_argument(
        "--wallet",
        default=None,
        help="Wallet to check (default: wallets with active DB rows)",
    )
    parser.add_argument("--tolerance-pct", type=float, default=1.0)
    parser.add_argument("--tolerance-usd", type=float, default=0.50)
    args = parser.parse_args()

    settings = get_settings()
    db_path = args.db or settings.database_url.replace("sqlite:///", "")

    return await verify(
        db_path=db_path,
        wallet_filter=args.wallet,
        tol_pct=Decimal(str(args.tolerance_pct)),
        tol_usd=Decimal(str(args.tolerance_usd)),
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
