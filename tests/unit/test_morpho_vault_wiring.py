"""Wiring tests for the Morpho vault venue.

Guards the properties that keep the vault opt-in and fail closed:
- SUPPORTED_PROTOCOLS defaults to Aave V3 + Moonwell, accepts only protocols
  with a working executor path, and reaches the strategy (and so the
  idle-deploy allowlist) through the runner's config.
- The vault is on the contract whitelist (else WalletManager blocks its txs).
- The scanner registers the vault (not raw Morpho Blue markets) as "Morpho".
- verify_positions always checks Morpho balances.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.security.contract_whitelist import ContractType, ContractWhitelist
from src.strategies.simple_yield import SimpleYieldStrategy
from src.utils.config import Settings
from tests.unit.morpho_vault_fakes import VAULT, FakeWeb3


# ===== SETTINGS =====


def test_supported_protocols_default_excludes_morpho():
    settings = Settings()
    assert settings.supported_protocols == "Aave V3,Moonwell"
    assert settings.supported_protocols_list == ["Aave V3", "Moonwell"]


def test_supported_protocols_opt_in_and_normalized(monkeypatch):
    monkeypatch.setenv("SUPPORTED_PROTOCOLS", " Aave V3 , Moonwell,Morpho ")
    assert Settings().supported_protocols_list == ["Aave V3", "Moonwell", "Morpho"]


@pytest.mark.parametrize("value", ["Aave V3,Aerodrome", "Morpho Blue", "", " , "])
def test_supported_protocols_rejects_non_executable(monkeypatch, value):
    monkeypatch.setenv("SUPPORTED_PROTOCOLS", value)
    with pytest.raises(ValidationError, match="supported_protocols"):
        Settings()


def test_vault_guard_bound_defaults_and_limits(monkeypatch):
    settings = Settings()
    assert settings.morpho_vault_min_timelock_seconds == 604800
    assert settings.morpho_vault_max_fee == Decimal("0.05")
    monkeypatch.setenv("MORPHO_VAULT_MIN_TIMELOCK_SECONDS", "3600")
    with pytest.raises(ValidationError):
        Settings()


# ===== RUNNER → STRATEGY =====


def _runner():
    from scripts.run_autonomous_optimizer import AutonomousRunner

    return AutonomousRunner(
        duration_hours=1.0,
        scan_interval_hours=2.0,
        max_rebalances_per_day=20,
        max_gas_per_day_usd=Decimal("2"),
        dry_run=True,
    )


def test_runner_default_strategy_allowlist_unchanged():
    config = _runner()._build_config()
    assert config["supported_protocols"] == ["Aave V3", "Moonwell"]
    assert SimpleYieldStrategy(config).supported_protocols == ["Aave V3", "Moonwell"]


def test_runner_passes_morpho_opt_in_to_strategy(monkeypatch):
    monkeypatch.setenv("SUPPORTED_PROTOCOLS", "Aave V3,Moonwell,Morpho")
    config = _runner()._build_config()
    assert SimpleYieldStrategy(config).supported_protocols == ["Aave V3", "Moonwell", "Morpho"]
    assert config["morpho_vault_min_timelock_seconds"] == 604800
    assert config["morpho_vault_max_fee"] == Decimal("0.05")


# ===== WHITELIST =====


def test_vault_is_whitelisted_lending_pool():
    wl = ContractWhitelist()
    assert wl.is_whitelisted(VAULT)
    info = wl.get_contract_info(VAULT)
    assert info.protocol == "morpho"
    assert info.contract_type == ContractType.LENDING_POOL


# ===== SCANNER / VERIFIER =====


def test_scanner_registers_vault_as_morpho():
    from src.agents.yield_scanner import YieldScannerAgent
    from src.protocols.morpho_vault import MorphoVaultProtocol

    with patch("src.protocols.morpho_vault.get_web3", return_value=FakeWeb3()):
        scanner = YieldScannerAgent({"chainlink_enabled": False, "network": "base-mainnet"})

    morpho = [p for p in scanner.protocols if p.name == "Morpho"]
    assert len(morpho) == 1
    assert isinstance(morpho[0], MorphoVaultProtocol)


def test_verifier_checks_morpho_balances():
    import os

    # verify_positions mutates these at import time; keep them hermetic.
    saved = {k: os.environ.get(k) for k in ("USE_LOCAL_WALLET", "DRY_RUN_MODE")}
    try:
        import scripts.verify_positions as vp

        assert "Morpho" in vp.SUPPORTED_PROTOCOLS
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
