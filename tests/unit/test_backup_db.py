"""Tests for the stdlib SQLite backup script (WS4)."""

import gzip
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP = REPO_ROOT / "scripts" / "backup_db.py"


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, token TEXT)")
    conn.execute("INSERT INTO positions (token) VALUES ('USDC')")
    conn.commit()
    conn.close()


def _run_backup(tmp_path, db, keep=14):
    return subprocess.run(
        [
            sys.executable,
            str(BACKUP),
            "--db",
            str(db),
            "--backup-dir",
            str(tmp_path / "backups"),
            "--keep",
            str(keep),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )


def test_backup_roundtrip_preserves_row(tmp_path):
    db = tmp_path / "mammon.db"
    _make_db(db)
    result = _run_backup(tmp_path, db)
    assert result.returncode == 0, result.stderr

    backups = list((tmp_path / "backups").glob("mammon_*.db.gz"))
    assert len(backups) == 1

    # Decompress and confirm the row survived.
    raw = tmp_path / "restored.db"
    with gzip.open(backups[0], "rb") as f_in:
        raw.write_bytes(f_in.read())
    conn = sqlite3.connect(str(raw))
    tokens = [r[0] for r in conn.execute("SELECT token FROM positions")]
    conn.close()
    assert tokens == ["USDC"]


def test_missing_db_exits_one(tmp_path):
    result = _run_backup(tmp_path, tmp_path / "absent.db")
    assert result.returncode == 1
    assert "ERROR" in result.stderr


def test_prune_keeps_only_n(tmp_path):
    db = tmp_path / "mammon.db"
    _make_db(db)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    # Seed 3 fake older backups.
    for stamp in ("20260101_000000", "20260102_000000", "20260103_000000"):
        (backup_dir / f"mammon_{stamp}.db.gz").write_bytes(b"old")
    result = _run_backup(tmp_path, db, keep=2)
    assert result.returncode == 0
    remaining = sorted((backup_dir).glob("mammon_*.db.gz"))
    assert len(remaining) == 2  # pruned down to the 2 newest (incl. the new one)
