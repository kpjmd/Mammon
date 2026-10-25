#!/usr/bin/env python3
"""Manually exit the allowlisted Morpho vault (full redeem to the wallet).

For when the vault guard trips (curator/owner/fee/timelock drift or a share
price drop): the guard blocks NEW deposits and drops the vault from scans, so
the optimizer will not move funds out on its own. Withdrawals are never gated
by the guard, so this script can always exit.

Dry-run by default: reads the position and the vault's withdrawable liquidity
and simulates the redeem. Broadcasting requires --live AND typing the
confirmation phrase. Stop mammon.service first so the two processes never
race on the wallet nonce.

Usage (on the droplet, from /root/mammon):
    sudo systemctl stop mammon.service
    /root/.local/bin/poetry run python scripts/morpho_vault_exit.py          # dry run
    /root/.local/bin/poetry run python scripts/morpho_vault_exit.py --live   # broadcast
    sudo systemctl start mammon.service
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import asyncio
from decimal import Decimal

from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.blockchain.wallet import WalletManager
from src.data.oracles import create_price_oracle
from src.protocols.morpho_vault import MorphoVaultProtocol, get_vault_spec
from src.utils.logger import setup_logging

CONFIRMATION = "EXIT MORPHO VAULT"


async def main(live: bool) -> int:
    from scripts.run_autonomous_optimizer import AutonomousRunner

    runner = AutonomousRunner(duration_hours=0.01, scan_interval_hours=1.0, dry_run=not live)
    config = runner._build_config()
    oracle = create_price_oracle("mock")  # no pricing needed for a same-token exit
    wallet = WalletManager(config=config, price_oracle=oracle)
    await wallet.initialize()
    executor = ProtocolActionExecutor(wallet, config)
    protocol = MorphoVaultProtocol({**config, "price_oracle": oracle})

    spec = get_vault_spec("USDC")
    position = await protocol.get_user_balance(spec.pool_id, wallet.address)
    print(f"Wallet {wallet.address}: {position} USDC in {spec.label} ({spec.address})")
    if position <= 0:
        print("Nothing to exit.")
        return 0

    if live:
        typed = input(f'Broadcast a full redeem? Type "{CONFIRMATION}" to proceed: ')
        if typed.strip() != CONFIRMATION:
            print("Aborted; nothing sent.")
            return 1

    # Requesting at least the whole position makes the executor redeem every
    # share; it refuses before broadcasting if vault liquidity is insufficient.
    result = await executor.execute_withdraw("Morpho", "USDC", position + Decimal("1"))
    print(f"Result: {result}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="broadcast (default: dry run)")
    sys.exit(asyncio.run(main(parser.parse_args().live)))
