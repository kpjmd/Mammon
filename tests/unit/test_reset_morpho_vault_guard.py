"""Tests for scripts/reset_morpho_vault_guard.py (operator reset of the latch)."""

import pytest

import scripts.reset_morpho_vault_guard as reset_script
from src.protocols.morpho_vault import get_vault_spec
from src.protocols.morpho_vault_guard import VaultGuardError, VaultGuardStore

VAULT = get_vault_spec("USDC").address


def test_dry_run_reports_and_keeps_latch(tmp_path, capsys):
    state = tmp_path / "guard.json"
    VaultGuardStore(state).latch(VAULT, "share price fell (test)")

    assert reset_script.main(["--state-file", str(state)]) == 0

    assert "share price fell (test)" in capsys.readouterr().out
    with pytest.raises(VaultGuardError):
        VaultGuardStore(state).assert_not_tripped(VAULT)


def test_confirm_clears_latch(tmp_path):
    state = tmp_path / "guard.json"
    VaultGuardStore(state).latch(VAULT, "operator exit")

    assert reset_script.main(["--state-file", str(state), "--vault", VAULT, "--confirm"]) == 0

    VaultGuardStore(state).assert_not_tripped(VAULT)


def test_confirm_recovers_corrupt_file(tmp_path, capsys):
    state = tmp_path / "guard.json"
    state.write_text("{oops")

    reset_script.main(["--state-file", str(state)])
    assert "UNREADABLE" in capsys.readouterr().out

    reset_script.main(["--state-file", str(state), "--confirm"])
    VaultGuardStore(state).assert_not_tripped(VAULT)
