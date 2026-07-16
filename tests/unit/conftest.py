"""Shared fixtures for the unit-test suite.

Unit tests must be *hermetic*: their results should not depend on the
developer's local ``.env`` file or on secrets present in the shell. Many code
paths transitively construct :class:`src.utils.config.Settings` (via
``get_settings()``), which declares ``wallet_seed``, ``cdp_wallet_secret`` and
other fields as required. Without them pydantic raises
``ValidationError: ... Field required`` and the test errors out for reasons
unrelated to the behavior under test.

The autouse fixture below gives every unit test a complete, valid, deterministic
environment and neutralizes ``.env`` loading, so the suite behaves identically
regardless of what the developer has configured locally.
"""

import pytest

import src.utils.config as config_module
from src.utils.config import Settings

# A valid 12-word BIP39 mnemonic (passes the word-count validator in
# ``Settings.validate_wallet_seed``). Deterministic, well-known test vector —
# never used with real funds.
_TEST_WALLET_SEED = (
    "abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon abandon abandon about"
)

# Complete set of required + safety-relevant settings for a deterministic run.
# Values are intentionally non-placeholder (the validators reject ``your_*`` /
# ``*_here``) and safe (dry-run on, development environment).
_TEST_ENV = {
    "CDP_API_KEY": "test-cdp-api-key",
    "CDP_API_SECRET": "test-cdp-api-secret",
    "CDP_WALLET_SECRET": "dGVzdC13YWxsZXQtc2VjcmV0",  # base64("test-wallet-secret")
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "WALLET_SEED": _TEST_WALLET_SEED,
    "DRY_RUN_MODE": "true",
    "ENVIRONMENT": "development",
}


@pytest.fixture(autouse=True)
def mammon_test_env(request, monkeypatch):
    """Provide a hermetic, deterministic settings environment for every test.

    - Neutralizes ``.env`` loading so tests never read the developer's local
      secrets (fields not set here fall back to their in-code defaults).
    - Sets a complete set of required env vars so ``Settings()`` constructs
      cleanly wherever code calls ``get_settings()``.
    - Resets the cached settings singleton before and after each test so a
      ``Settings`` instance built by one test cannot leak into another.

    Carve-out: ``test_wallet_seed_validation_required`` in ``test_config.py``
    asserts that ``Settings()`` *fails* when ``wallet_seed`` is absent, so this
    fixture must leave ``WALLET_SEED`` unset for that one test.
    """
    # Make Settings ignore the developer's .env file for hermeticity.
    monkeypatch.setitem(Settings.model_config, "env_file", None)

    wants_missing_seed = (
        "test_wallet_seed_validation_required" in request.node.nodeid
    )

    for key, value in _TEST_ENV.items():
        if key == "WALLET_SEED" and wants_missing_seed:
            monkeypatch.delenv("WALLET_SEED", raising=False)
            continue
        monkeypatch.setenv(key, value)

    # Ensure no cached Settings leaks in from a prior test or import.
    monkeypatch.setattr(config_module, "_settings", None, raising=False)
    yield
    config_module._settings = None
