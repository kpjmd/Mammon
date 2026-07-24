"""The verifier's oracle must use the same staleness settings as the live loop.

verify_positions.py built its Chainlink oracle without max_staleness_seconds,
so it fell back to create_price_oracle's 3600s default. Chainlink's USDC/USD
feed on Base has a ~24h heartbeat, so every read was judged stale and the
oracle silently fell back to MockPriceOracle -- the verifier was comparing
recorded values against mock prices while the loop used real ones.
"""

import importlib
import os
from types import SimpleNamespace

import pytest


@pytest.fixture
def verify_module(monkeypatch):
    """Import the verifier without leaking its import-time env mutation.

    scripts/verify_positions.py sets USE_LOCAL_WALLET=false and
    DRY_RUN_MODE=true in os.environ *at import time* (deliberately, so the
    read-only script loads settings without a local seed). Importing it from a
    test leaks that into the rest of the session -- it broke
    test_config_custody's "local wallet remains the default". Snapshot both
    keys with monkeypatch first so they are restored at teardown.
    """
    for key in ("USE_LOCAL_WALLET", "DRY_RUN_MODE"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    return importlib.import_module("scripts.verify_positions")


def test_oracle_receives_staleness_settings(verify_module, monkeypatch):
    captured = {}

    def _fake_create(kind, **kwargs):
        captured["kind"] = kind
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(verify_module, "create_price_oracle", _fake_create)
    # Stop after the oracle is built; the scanner needs network wiring.
    monkeypatch.setattr(
        verify_module, "YieldScannerAgent", lambda *a, **k: object(), raising=False
    )

    settings = SimpleNamespace(
        chainlink_enabled=True,
        network="base-mainnet",
        chainlink_price_network="base-mainnet",
        chainlink_cache_ttl_seconds=300,
        chainlink_max_staleness_seconds=86400,
        chainlink_fallback_to_mock=True,
        morpho_max_markets=5,
        aerodrome_max_pools=10,
        supported_tokens=["USDC"],
    )

    try:
        verify_module._build_scanner_and_oracle(settings)
    except Exception:
        # Scanner construction may still fail; the oracle call already happened.
        pass

    assert captured["kind"] == "chainlink"
    assert captured["max_staleness_seconds"] == 86400
    assert captured["cache_ttl_seconds"] == 300
