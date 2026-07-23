"""Static lint for the systemd units that supervise the 30-day run.

These are plain-text asserts (no systemd needed) guarding the two regressions
that would silently break a long run: the wrong WorkingDirectory (the live
droplet is a git checkout at ``/root/mammon``; ``/opt/mammon`` is a stale rsync
copy) and ``Restart=on-failure`` (which does not restart on a clean exit at
end_time).
"""

from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _read(name: str) -> str:
    path = SCRIPTS / name
    assert path.exists(), f"missing systemd unit: {name}"
    return path.read_text()


def test_main_service_survivability_and_path():
    text = _read("mammon.service")
    assert "WorkingDirectory=/root/mammon" in text
    assert "Restart=always" in text
    # Must run long enough to cover the 30-day validation.
    assert "--duration 744" in text
    assert "run_autonomous_optimizer.py" in text
    # The stale rsync path and the non-surviving restart mode must not linger.
    assert "WorkingDirectory=/opt/mammon" not in text
    assert "Restart=on-failure" not in text


@pytest.mark.parametrize(
    "unit,script",
    [
        ("mammon-heartbeat.service", "scripts/heartbeat_check.py"),
        ("mammon-backup.service", "scripts/backup_db.py"),
    ],
)
def test_oneshot_services(unit, script):
    text = _read(unit)
    assert "Type=oneshot" in text
    assert "WorkingDirectory=/root/mammon" in text
    assert script in text


@pytest.mark.parametrize(
    "unit,schedule_key",
    [
        ("mammon-heartbeat.timer", "OnUnitActiveSec="),
        ("mammon-backup.timer", "OnCalendar="),
    ],
)
def test_timers(unit, schedule_key):
    text = _read(unit)
    assert schedule_key in text
    assert "Persistent=true" in text
    assert "WantedBy=timers.target" in text
