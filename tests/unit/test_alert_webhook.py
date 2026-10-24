"""Webhook delivery from the stdlib ops scripts (heartbeat, backup, replication).

Regression: Discord's Cloudflare front end rejects urllib's default
``Python-urllib/x.y`` User-Agent with ``403 error code: 1010``, so no heartbeat
or backup alert was ever delivered (backup_db swallowed the error silently).

A local HTTP server mimics that front end: 403 for a ``Python-urllib`` UA, else
the configured status. The scripts run as subprocesses (real CLI) with
ALERT_WEBHOOK pointed at it, so nothing ever reaches a real webhook.
"""

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


class _FakeDiscord:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.status = 204
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server API
                body = self.rfile.read(int(self.headers["Content-Length"]))
                agent = self.headers.get("User-Agent", "")
                fake.requests.append({"agent": agent, "payload": json.loads(body)})
                blocked = agent.startswith("Python-urllib")
                self.send_response(403 if blocked else fake.status)
                self.end_headers()
                if blocked:
                    self.wfile.write(b"error code: 1010\n")

            def log_message(self, *args) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/webhooks/1/x"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def discord():
    fake = _FakeDiscord()
    yield fake
    fake.server.shutdown()


def _run(script: str, cwd: Path, webhook: str, *args: str, **env):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "ALERT_WEBHOOK": webhook, **env},
    )


def _stale_heartbeat(tmp_path: Path) -> Path:
    hb = tmp_path / "heartbeat.json"
    ts = datetime.now(timezone.utc) - timedelta(hours=5)
    hb.write_text(json.dumps({"timestamp": ts.isoformat(), "pid": 1}))
    return hb


def test_heartbeat_alert_is_delivered(tmp_path, discord):
    hb = _stale_heartbeat(tmp_path)

    result = _run("heartbeat_check.py", tmp_path, discord.url, "--file", str(hb))

    assert result.returncode == 1
    assert "Alert POST failed" not in result.stderr
    [req] = discord.requests
    assert not req["agent"].startswith("Python-urllib")
    assert req["payload"]["content"].startswith("[CRITICAL] MAMMON: MAMMON heartbeat stale")
    assert Path(str(hb) + ".stale_alerted").exists()


def test_heartbeat_failed_post_is_retried_next_run(tmp_path, discord):
    """A failed POST must not write the one-shot marker, or the outage goes unreported."""
    hb = _stale_heartbeat(tmp_path)
    discord.status = 500

    first = _run("heartbeat_check.py", tmp_path, discord.url, "--file", str(hb))
    assert "Alert POST failed" in first.stderr
    assert not Path(str(hb) + ".stale_alerted").exists()

    discord.status = 204
    _run("heartbeat_check.py", tmp_path, discord.url, "--file", str(hb))

    assert len(discord.requests) == 2
    assert Path(str(hb) + ".stale_alerted").exists()


def test_backup_failure_alert_is_delivered(tmp_path, discord):
    result = _run("backup_db.py", tmp_path, discord.url, "--db", str(tmp_path / "absent.db"))

    assert result.returncode == 1
    [req] = discord.requests
    assert not req["agent"].startswith("Python-urllib")
    assert req["payload"]["content"].startswith("[ERROR] MAMMON: DB backup failed")


def test_backup_alert_post_failure_is_not_silent(tmp_path, discord):
    discord.status = 500

    result = _run("backup_db.py", tmp_path, discord.url, "--db", str(tmp_path / "absent.db"))

    assert "Alert POST failed" in result.stderr


def test_replication_failure_alert_is_delivered(tmp_path, discord):
    (tmp_path / "backups").mkdir()

    result = _run(
        "replicate_backups.py",
        tmp_path,
        discord.url,
        "--backup-dir",
        str(tmp_path / "backups"),
        BACKUP_REMOTE="",
    )

    assert result.returncode == 1
    assert "Alert POST failed" not in result.stderr
    [req] = discord.requests
    assert not req["agent"].startswith("Python-urllib")
    assert "DB backup replication failed" in req["payload"]["content"]
