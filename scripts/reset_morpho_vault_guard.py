#!/usr/bin/env python3
"""Reset the Morpho vault guard latch (operator decision after investigating).

The share-price tripwire and manual exits latch the vault in
data/morpho_vault_guard.json, blocking new deposits across restarts. This
script is the only way to clear it. Resetting also drops the vault's high-water
share price, so the next scan adopts the CURRENT price as the baseline: do it
only once you've confirmed the vault is healthy (or accept the loss).

Can run while the loop is live (state is file-based) or stopped.

Usage:
    python scripts/reset_morpho_vault_guard.py            # show state, do nothing
    python scripts/reset_morpho_vault_guard.py --confirm  # clear the latch
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.protocols.morpho_vault_guard import (  # noqa: E402
    DEFAULT_STATE_FILE,
    GuardStateUnreadable,
    VaultGuardStore,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Reset the Morpho vault guard latch")
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE, help="guard state file")
    parser.add_argument("--vault", help="reset only this vault address (default: all)")
    parser.add_argument("--confirm", action="store_true", help="actually reset")
    args = parser.parse_args(argv)

    store = VaultGuardStore(args.state_file)
    print(f"Morpho vault guard state ({args.state_file}):")
    try:
        records = store.snapshot()
        if not records:
            print("  (no records: nothing latched)")
        for vault, record in records.items():
            print(f"  {vault}: tripped={record.tripped} at={record.tripped_at}")
            print(f"    reason: {record.trip_reason}")
            print(f"    high-water share price: {record.high_water_share_price}")
    except GuardStateUnreadable as e:
        print(f"  UNREADABLE (every vault treated as tripped): {e}")

    if not args.confirm:
        print("\nDry run. Re-run with --confirm to clear the latch.")
        return 0
    store.reset(args.vault)
    print(f"\nReset {'vault ' + args.vault if args.vault else 'all vaults'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
