#!/usr/bin/env python3
"""Manually exit the allowlisted Morpho vault (full redeem to the wallet).

For when the vault guard trips on governance drift (curator/owner/fee/
timelock) or its state file is unreadable: the guard blocks NEW deposits and
drops the vault from scans, and the optimizer holds rather than exiting. (A
share-price/bad-debt latch is exited automatically each cycle; this script is
still the manual path for it.) Withdrawals are never gated by the guard, so
this script can always exit.

Dry-run by default: reads the position and the vault's withdrawable liquidity
and simulates the redeem. Broadcasting requires --live AND typing the
confirmation phrase, and is refused while mammon.service is active (the two
processes would race on the wallet nonce and position) unless --force.

A successful live exit latches the vault guard (persisted), so the restarted
loop will not redeposit into the vault. Clear it only after investigating,
with scripts/reset_morpho_vault_guard.py --confirm.

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
import shutil
import subprocess
from decimal import Decimal
from typing import Optional

from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.blockchain.wallet import WalletManager
from src.data.oracles import create_price_oracle
from src.protocols.morpho_vault import MorphoVaultProtocol, get_vault_spec
from src.protocols.morpho_vault_guard import VaultGuardStore
from src.utils.logger import setup_logging

CONFIRMATION = "EXIT MORPHO VAULT"
SERVICE = "mammon.service"


def service_state() -> Optional[str]:
    """`systemctl is-active` for the loop, or None where systemd is absent."""
    if shutil.which("systemctl") is None:
        return None
    result = subprocess.run(
        ["systemctl", "is-active", SERVICE], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or None


def loop_is_running() -> bool:
    """True if the optimizer service is (or may soon be) running."""
    return service_state() in {"active", "activating", "reloading"}


async def main(live: bool, force: bool = False) -> int:
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
        if loop_is_running() and not force:
            print(
                f"Refusing to broadcast: {SERVICE} is active and would race this "
                f"script on the wallet nonce. Run `sudo systemctl stop {SERVICE}` "
                f"first (or pass --force)."
            )
            return 2
        typed = input(f'Broadcast a full redeem? Type "{CONFIRMATION}" to proceed: ')
        if typed.strip() != CONFIRMATION:
            print("Aborted; nothing sent.")
            return 1

    # Requesting at least the whole position makes the executor redeem every
    # share; it refuses before broadcasting if vault liquidity is insufficient.
    result = await executor.execute_withdraw("Morpho", "USDC", position + Decimal("1"))
    print(f"Result: {result}")
    if not result.get("success"):
        return 1
    if live:
        VaultGuardStore(config.get("morpho_vault_guard_state_file")).latch(
            spec.address, f"{spec.label}: operator exit via scripts/morpho_vault_exit.py"
        )
        print("Vault guard latched: no new deposits until scripts/reset_morpho_vault_guard.py.")
    return 0


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="broadcast (default: dry run)")
    parser.add_argument(
        "--force", action="store_true", help=f"broadcast even if {SERVICE} is active"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.live, args.force)))
