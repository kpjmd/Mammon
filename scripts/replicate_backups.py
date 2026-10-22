#!/usr/bin/env python3
"""Replicate MAMMON DB backups off the droplet via an rclone *crypt* remote.

Runs as ``ExecStartPost=`` of ``mammon-backup.service``, i.e. only after
``backup_db.py`` wrote a fresh ``data/backups/mammon_*.db.gz``. Losing the
droplet must not lose the position/transaction/decision ledger.

STDLIB-ONLY and app-independent, like ``backup_db.py``. The destination comes
from ``BACKUP_REMOTE`` (env or ``.env``), e.g. ``mammon-crypt:`` where
``mammon-crypt`` is an rclone crypt remote layered over an S3-compatible bucket.
Credentials and crypt passwords live in the droplet's rclone.conf, never here.

Fail-safe: refuses to upload unless the remote's type is ``crypt`` (so a
misconfiguration can never ship the ledger in plaintext), and every failure
posts an ALERT_WEBHOOK error and exits 1 so it is never silent.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from backup_db import DEFAULT_BACKUP_DIR, _post_error, _read_env

BACKUP_GLOB = "mammon_*.db.gz"
LIST_TIMEOUT_S = 30
COPY_TIMEOUT_S = 600


class ReplicationError(Exception):
    """Any condition that means the ledger did not provably reach the remote."""


def _rclone(rclone: str, args: list[str], timeout: int) -> str:
    cmd = [rclone, *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as e:
        raise ReplicationError(f"rclone binary not found: {rclone}") from e
    except subprocess.TimeoutExpired as e:
        raise ReplicationError(f"`rclone {args[0]}` timed out after {timeout}s") from e
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-500:]
        raise ReplicationError(f"`rclone {args[0]}` exited {result.returncode}: {detail}")
    return result.stdout


def _remote_name(remote: str) -> str:
    name, sep, _ = remote.partition(":")
    if not sep or not name:
        raise ReplicationError(
            f"BACKUP_REMOTE must be an rclone remote like 'mammon-crypt:', got {remote!r}"
        )
    return name


def _require_crypt_remote(rclone: str, remote: str) -> None:
    """`listremotes --long` prints `name:  type [description]` (no secrets)."""
    name = _remote_name(remote)
    for line in _rclone(rclone, ["listremotes", "--long"], LIST_TIMEOUT_S).splitlines():
        tokens = line.split()
        if len(tokens) >= 2 and tokens[0].rstrip(":") == name:
            if tokens[1] != "crypt":
                raise ReplicationError(
                    f"remote '{name}' is type '{tokens[1]}', not 'crypt' — "
                    "refusing to upload the ledger unencrypted"
                )
            return
    raise ReplicationError(f"rclone remote '{name}' is not configured")


def _newest_backup(backup_dir: Path) -> Path:
    backups = sorted(backup_dir.glob(BACKUP_GLOB))
    if not backups:
        raise ReplicationError(f"no {BACKUP_GLOB} files in {backup_dir}")
    return backups[-1]


def replicate(rclone: str, remote: str, backup_dir: Path) -> Path:
    """Copy every local backup to ``remote`` and prove the newest one landed."""
    newest = _newest_backup(backup_dir)
    _require_crypt_remote(rclone, remote)
    # copy (not sync): the remote keeps history beyond the local keep-14 prune.
    _rclone(
        rclone,
        ["copy", str(backup_dir), remote, "--include", BACKUP_GLOB],
        COPY_TIMEOUT_S,
    )
    listed = _rclone(rclone, ["lsf", "--files-only", remote], LIST_TIMEOUT_S)
    if newest.name not in listed.splitlines():
        raise ReplicationError(f"{newest.name} not present on {remote} after copy")
    return newest


def main() -> int:
    parser = argparse.ArgumentParser(description="Replicate DB backups off-droplet")
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--rclone", default="rclone", help="rclone binary")
    args = parser.parse_args()

    remote = _read_env("BACKUP_REMOTE")
    try:
        if not remote:
            raise ReplicationError("BACKUP_REMOTE is not set — backups exist only on the droplet")
        newest = replicate(args.rclone, remote, Path(args.backup_dir))
    except ReplicationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        _post_error("DB backup replication failed", str(e))
        return 1

    print(f"OK: replicated {newest.name} to {remote}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
