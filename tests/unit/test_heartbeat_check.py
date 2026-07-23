"""Tests for the stdlib heartbeat dead-man check (WS3).

Subprocess-driven (like test_backup_db.py) so we exercise the real CLI + exit
codes. Run with cwd=tmp_path and ALERT_WEBHOOK="" so no webhook ever fires.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "scripts" / "heartbeat_check.py"
MARKER_SUFFIX = ".stale_alerted"


def _write_heartbeat(path: Path, age_seconds: int) -> None:
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    path.write_text(json.dumps({"timestamp": ts.isoformat(), "total_scans": 7, "pid": 123}))


def _run(tmp_path: Path, hb: Path, max_age: int = 10800):
    env = {**os.environ, "ALERT_WEBHOOK": ""}  # never POST from a test
    return subprocess.run(
        [sys.executable, str(CHECK), "--file", str(hb), "--max-age", str(max_age)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
    )


def test_fresh_heartbeat_ok(tmp_path):
    hb = tmp_path / "heartbeat.json"
    _write_heartbeat(hb, age_seconds=30)
    result = _run(tmp_path, hb)
    assert result.returncode == 0
    assert "OK" in result.stdout
    assert not Path(str(hb) + MARKER_SUFFIX).exists()


def test_missing_file_is_stale(tmp_path):
    hb = tmp_path / "heartbeat.json"  # never created
    result = _run(tmp_path, hb)
    assert result.returncode == 1
    assert "STALE" in result.stdout
    assert Path(str(hb) + MARKER_SUFFIX).exists()


def test_stale_timestamp_alerts_once(tmp_path):
    hb = tmp_path / "heartbeat.json"
    _write_heartbeat(hb, age_seconds=4 * 3600)  # 4h > 3h default
    result = _run(tmp_path, hb)
    assert result.returncode == 1
    assert "STALE" in result.stdout
    assert Path(str(hb) + MARKER_SUFFIX).exists()


def test_recovery_clears_marker(tmp_path):
    hb = tmp_path / "heartbeat.json"
    # First: stale run creates the marker.
    _write_heartbeat(hb, age_seconds=4 * 3600)
    assert _run(tmp_path, hb).returncode == 1
    marker = Path(str(hb) + MARKER_SUFFIX)
    assert marker.exists()

    # Then: a fresh heartbeat recovers and clears the marker.
    _write_heartbeat(hb, age_seconds=30)
    result = _run(tmp_path, hb)
    assert result.returncode == 0
    assert "OK" in result.stdout
    assert not marker.exists()
