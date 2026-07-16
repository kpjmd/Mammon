#!/usr/bin/env python3
"""Back up the MAMMON SQLite database (position/transaction/decision ledger).

STDLIB-ONLY and app-independent so it can run from cron / a systemd timer on the
droplet without importing the app. Uses SQLite's online backup API, which is
safe against a live writer.

    0 3 * * * cd /root/mammon && /usr/bin/python3 scripts/backup_db.py \
        && rclone copy data/backups remote:mammon-backups

Off-droplet copy (rclone/scp) is intentionally left to the cron line above so
the destination stays configurable; losing the droplet must not lose the ledger.
"""

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = "data/mammon.db"
DEFAULT_BACKUP_DIR = "data/backups"
DEFAULT_KEEP = 14


def _read_env(key: str) -> str:
    if key in os.environ:
        return os.environ[key]
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.split("#", 1)[0].strip().strip('"').strip("'")
    return ""


def _post_error(title: str, message: str) -> None:
    webhook = _read_env("ALERT_WEBHOOK")
    if not webhook:
        return
    text = f"[ERROR] MAMMON: {title}\n{message}"
    payload = json.dumps({"content": text, "text": text, "level": "error"}).encode()
    req = urllib.request.Request(
        webhook, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:  # noqa: BLE001
        pass


def _prune(backup_dir: Path, keep: int) -> None:
    backups = sorted(backup_dir.glob("mammon_*.db.gz"))
    for old in backups[:-keep] if keep > 0 else []:
        try:
            old.unlink()
            print(f"Pruned old backup: {old.name}")
        except Exception as e:  # noqa: BLE001
            print(f"Could not prune {old}: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the MAMMON SQLite DB")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        msg = f"database not found: {db_path}"
        print(f"ERROR: {msg}", file=sys.stderr)
        _post_error("DB backup failed", msg)
        return 1

    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    raw = backup_dir / f"mammon_{stamp}.db"
    gz = backup_dir / f"mammon_{stamp}.db.gz"

    try:
        # Online backup API: consistent snapshot even with a live writer.
        src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        dst = sqlite3.connect(str(raw))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()

        with open(raw, "rb") as f_in, gzip.open(gz, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        raw.unlink()
    except Exception as e:  # noqa: BLE001
        msg = f"backup failed: {e}"
        print(f"ERROR: {msg}", file=sys.stderr)
        _post_error("DB backup failed", msg)
        return 1

    size_kb = gz.stat().st_size / 1024
    print(f"OK: wrote {gz} ({size_kb:.1f} KB)")
    _prune(backup_dir, args.keep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
