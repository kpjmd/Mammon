"""Tests for the heartbeat writer and the dead-man checker script (WS4)."""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


from src.utils.heartbeat import write_heartbeat

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "heartbeat_check.py"


class TestWriter:
    def test_writes_expected_fields(self, tmp_path):
        hb = tmp_path / "hb.json"
        write_heartbeat(hb, last_cycle_ok=True, total_scans=7, breaker_tripped=False)
        data = json.loads(hb.read_text())
        assert data["last_cycle_ok"] is True
        assert data["total_scans"] == 7
        assert data["breaker_tripped"] is False
        assert "timestamp" in data and "pid" in data

    def test_extra_merged(self, tmp_path):
        hb = tmp_path / "hb.json"
        write_heartbeat(hb, last_cycle_ok=False, total_scans=0, extra={"phase": "sleep"})
        assert json.loads(hb.read_text())["phase"] == "sleep"

    def test_never_raises_on_bad_path(self):
        # A path whose parent cannot be created is swallowed, not raised.
        write_heartbeat("/proc/nonexistent/hb.json", last_cycle_ok=True, total_scans=0)


def _run_checker(hb_path, max_age=10800):
    return subprocess.run(
        [sys.executable, str(CHECKER), "--file", str(hb_path), "--max-age", str(max_age)],
        capture_output=True,
        text=True,
        cwd=hb_path.parent,  # avoid picking up the repo .env
    )


class TestChecker:
    def test_fresh_exits_zero(self, tmp_path):
        hb = tmp_path / "hb.json"
        write_heartbeat(hb, last_cycle_ok=True, total_scans=1)
        result = _run_checker(hb)
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_missing_exits_one(self, tmp_path):
        result = _run_checker(tmp_path / "nope.json")
        assert result.returncode == 1
        assert "STALE" in result.stdout

    def test_stale_exits_one(self, tmp_path):
        hb = tmp_path / "hb.json"
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        hb.write_text(json.dumps({"timestamp": old, "pid": 123, "total_scans": 4}))
        result = _run_checker(hb, max_age=3600)
        assert result.returncode == 1
        assert "STALE" in result.stdout

    def test_stale_writes_marker_once(self, tmp_path):
        hb = tmp_path / "hb.json"
        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        hb.write_text(json.dumps({"timestamp": old, "pid": 1, "total_scans": 0}))
        _run_checker(hb, max_age=3600)
        assert (tmp_path / "hb.json.stale_alerted").exists()
