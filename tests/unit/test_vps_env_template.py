"""Validate the VPS .env template in scripts/vps_deploy.sh against Settings.

The template is what a fresh droplet deploy writes to .env. If any value in it
violates a Settings field constraint, the app fails at startup with a pydantic
ValidationError — on the droplet, after deploy, which is the worst place to find
out. (This happened: MAX_REBALANCES_PER_DAY=24 vs the field's le=20.)

This test extracts the heredoc, substitutes valid dummies for the intentional
`your_*_here` secret placeholders, and asserts Settings() constructs cleanly.
"""

import re
from pathlib import Path

import pytest

from src.utils.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SH = REPO_ROOT / "scripts" / "vps_deploy.sh"

# Valid stand-ins for the template's deliberate placeholders. Mirrors the
# hermetic values in tests/unit/conftest.py (validators reject `your_*`/`*_here`).
_SECRET_SUBSTITUTES = {
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "CDP_API_KEY": "test-cdp-api-key",
    "CDP_API_SECRET": "test-cdp-api-secret",
    "CDP_WALLET_SECRET": "dGVzdC13YWxsZXQtc2VjcmV0",  # base64
}


def _parse_template() -> dict:
    """Extract KEY=VALUE pairs from the heredoc written by vps_deploy.sh."""
    text = DEPLOY_SH.read_text()
    match = re.search(r"<< 'ENVEOF'\n(.*?)\nENVEOF", text, re.S)
    assert match, "could not locate the ENVEOF heredoc in vps_deploy.sh"

    env = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Strip inline comments and quotes, matching dotenv behavior.
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        env[key] = value
    return env


def test_template_has_expected_keys():
    env = _parse_template()
    # Load-bearing keys for the MPC run; a silent drop would disable custody
    # selection, alerting, or point the DB somewhere the backup script isn't.
    for key in (
        "USE_LOCAL_WALLET",
        "CDP_ACCOUNT_NAME",
        "DATABASE_URL",
        "ALERT_WEBHOOK",
        "MAX_REBALANCES_PER_DAY",
        "MAX_GAS_PER_DAY_USD",
    ):
        assert key in env, f"template is missing {key}"


def test_template_validates_against_settings(monkeypatch):
    """Every template value must satisfy its Settings field constraints."""
    env = _parse_template()
    env.update(_SECRET_SUBSTITUTES)
    # Local custody needs a seed; the template sets USE_LOCAL_WALLET=false, but
    # supply one anyway so this test only exercises value constraints.
    env.setdefault(
        "WALLET_SEED",
        "abandon abandon abandon abandon abandon abandon "
        "abandon abandon abandon abandon abandon about",
    )

    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    try:
        Settings()
    except Exception as e:  # noqa: BLE001 - surface the offending field clearly
        pytest.fail(f"VPS .env template fails Settings validation:\n{e}")


def test_rebalance_cap_within_field_bound():
    """Explicit guard on the constraint that actually bit us (le=20)."""
    env = _parse_template()
    bound = Settings.model_fields["max_rebalances_per_day"].metadata
    le_values = [getattr(m, "le", None) for m in bound]
    le = next((v for v in le_values if v is not None), None)
    assert le is not None, "expected an le= bound on max_rebalances_per_day"
    assert int(env["MAX_REBALANCES_PER_DAY"]) <= le
