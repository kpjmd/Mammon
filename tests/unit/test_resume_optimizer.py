"""End-to-end test of the operator resume path (WS3 buffer).

Drives scripts/resume_optimizer.py against a tripped breaker state file to
confirm the trip -> inspect -> --confirm reset flow an operator would use.
"""

import json
import subprocess
import sys
from pathlib import Path

from src.utils.cycle_breaker import CycleCircuitBreaker

REPO_ROOT = Path(__file__).resolve().parents[2]
RESUME = REPO_ROOT / "scripts" / "resume_optimizer.py"


def _trip(state_file: Path) -> None:
    b = CycleCircuitBreaker(max_consecutive=1, state_file=state_file)
    b.record_failure("forced failure")
    assert b.is_tripped()


def _run(state_file: Path, *args):
    return subprocess.run(
        [sys.executable, str(RESUME), "--state-file", str(state_file), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_dry_run_reports_but_does_not_reset(tmp_path):
    state_file = tmp_path / "breaker.json"
    _trip(state_file)
    result = _run(state_file)  # no --confirm
    assert result.returncode == 0
    assert "tripped:              True" in result.stdout
    # Still tripped afterwards.
    assert json.loads(state_file.read_text())["tripped"] is True


def test_confirm_resets(tmp_path):
    state_file = tmp_path / "breaker.json"
    _trip(state_file)
    result = _run(state_file, "--confirm")
    assert result.returncode == 0
    assert "reset" in result.stdout.lower()
    assert json.loads(state_file.read_text())["tripped"] is False


def test_untripped_is_noop(tmp_path):
    state_file = tmp_path / "breaker.json"
    CycleCircuitBreaker(state_file=state_file).record_success()
    result = _run(state_file, "--confirm")
    assert result.returncode == 0
    assert "not tripped" in result.stdout.lower()
