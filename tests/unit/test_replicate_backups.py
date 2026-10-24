"""Tests for off-droplet backup replication (scripts/replicate_backups.py).

Subprocess-driven (like test_backup_db.py) against a FAKE rclone executable that
logs its argv, so the real CLI, exit codes and exact rclone invocations are
exercised without rclone or a network. Run with cwd=tmp_path (no .env) and
ALERT_WEBHOOK="" so no webhook ever fires. Alert/timeout paths are covered
in-process with the module's collaborators monkeypatched.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
REPLICATE = SCRIPTS / "replicate_backups.py"

FAKE_RCLONE = """\
#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
if args[0] == os.environ.get("FAKE_FAIL_CMD"):
    print("boom", file=sys.stderr)
    sys.exit(3)
if args[0] == "listremotes":
    print("spaces:       s3")
    print("mammon-crypt: " + os.environ.get("FAKE_TYPE", "crypt") + "  offsite ledger")
elif args[0] == "lsf" and not os.environ.get("FAKE_LSF_EMPTY"):
    print("\\n".join(os.environ.get("FAKE_LSF", "").split(",")))
"""


@pytest.fixture
def fake_rclone(tmp_path):
    exe = tmp_path / "rclone"
    exe.write_text(FAKE_RCLONE.format(python=sys.executable))
    exe.chmod(0o755)
    return exe


def _make_backups(tmp_path: Path, names: list[str]) -> Path:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for name in names:
        (backup_dir / name).write_bytes(b"gz")
    return backup_dir


def _run(tmp_path, fake_rclone, remote="mammon-crypt:", **fake_env):
    env = {
        **os.environ,
        "ALERT_WEBHOOK": "",  # never POST from a test
        "BACKUP_REMOTE": remote,
        "FAKE_LOG": str(tmp_path / "calls.jsonl"),
        **fake_env,
    }
    return subprocess.run(
        [
            sys.executable,
            str(REPLICATE),
            "--backup-dir",
            str(tmp_path / "backups"),
            "--rclone",
            str(fake_rclone),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
    )


def _calls(tmp_path: Path) -> list[list[str]]:
    log = tmp_path / "calls.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


NEWEST = "mammon_20261021_030000.db.gz"
OLDER = "mammon_20261020_030000.db.gz"


def test_success_copies_and_confirms_newest(tmp_path, fake_rclone):
    backup_dir = _make_backups(tmp_path, [OLDER, NEWEST])
    result = _run(tmp_path, fake_rclone, FAKE_LSF=f"{OLDER},{NEWEST}")
    assert result.returncode == 0, result.stderr
    assert f"OK: replicated {NEWEST} to mammon-crypt:" in result.stdout

    calls = _calls(tmp_path)
    assert calls[0] == ["listremotes", "--long"]
    # copy (never sync), only backup files, destination solely from BACKUP_REMOTE.
    assert calls[1] == [
        "copy",
        str(backup_dir),
        "mammon-crypt:",
        "--include",
        "mammon_*.db.gz",
    ]
    assert calls[2] == ["lsf", "--files-only", "mammon-crypt:"]
    assert not any("sync" in call for call in calls)


def test_remote_unset_fails_without_calling_rclone(tmp_path, fake_rclone):
    _make_backups(tmp_path, [NEWEST])
    result = _run(tmp_path, fake_rclone, remote="")
    assert result.returncode == 1
    assert "BACKUP_REMOTE is not set" in result.stderr
    assert _calls(tmp_path) == []


def test_non_crypt_remote_refused_before_upload(tmp_path, fake_rclone):
    _make_backups(tmp_path, [NEWEST])
    result = _run(tmp_path, fake_rclone, FAKE_TYPE="s3")
    assert result.returncode == 1
    assert "not 'crypt'" in result.stderr
    assert [c[0] for c in _calls(tmp_path)] == ["listremotes"]


def test_unconfigured_remote_refused(tmp_path, fake_rclone):
    _make_backups(tmp_path, [NEWEST])
    result = _run(tmp_path, fake_rclone, remote="nope:")
    assert result.returncode == 1
    assert "'nope' is not configured" in result.stderr
    assert [c[0] for c in _calls(tmp_path)] == ["listremotes"]


def test_local_path_remote_rejected(tmp_path, fake_rclone):
    _make_backups(tmp_path, [NEWEST])
    result = _run(tmp_path, fake_rclone, remote="/mnt/backups")
    assert result.returncode == 1
    assert "must be an rclone remote" in result.stderr


def test_copy_failure_reported(tmp_path, fake_rclone):
    _make_backups(tmp_path, [NEWEST])
    result = _run(tmp_path, fake_rclone, FAKE_FAIL_CMD="copy")
    assert result.returncode == 1
    assert "`rclone copy` exited 3: boom" in result.stderr


def test_newest_missing_after_copy_reported(tmp_path, fake_rclone):
    _make_backups(tmp_path, [OLDER, NEWEST])
    result = _run(tmp_path, fake_rclone, FAKE_LSF=OLDER)
    assert result.returncode == 1
    assert f"{NEWEST} not present" in result.stderr


def test_no_local_backups_reported(tmp_path, fake_rclone):
    _make_backups(tmp_path, [])
    result = _run(tmp_path, fake_rclone)
    assert result.returncode == 1
    assert "no mammon_*.db.gz files" in result.stderr
    assert _calls(tmp_path) == []


def test_missing_rclone_binary_reported(tmp_path):
    _make_backups(tmp_path, [NEWEST])
    result = _run(tmp_path, tmp_path / "absent-rclone")
    assert result.returncode == 1
    assert "rclone binary not found" in result.stderr


@pytest.fixture
def replicate_mod(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import replicate_backups

    return replicate_backups


def test_failure_posts_alert(tmp_path, monkeypatch, replicate_mod):
    _make_backups(tmp_path, [NEWEST])
    alerts = []
    monkeypatch.setattr(replicate_mod, "_post_error", lambda t, m: alerts.append((t, m)))
    monkeypatch.setenv("BACKUP_REMOTE", "")
    monkeypatch.setattr(
        sys, "argv", ["replicate_backups.py", "--backup-dir", str(tmp_path / "backups")]
    )

    assert replicate_mod.main() == 1
    assert alerts == [
        (
            "DB backup replication failed",
            "BACKUP_REMOTE is not set — backups exist only on the droplet",
        )
    ]


def test_timeout_is_a_replication_error(monkeypatch, replicate_mod):
    def _hang(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(replicate_mod.subprocess, "run", _hang)
    with pytest.raises(replicate_mod.ReplicationError, match="timed out after 600s"):
        replicate_mod._rclone("rclone", ["copy"], replicate_mod.COPY_TIMEOUT_S)
