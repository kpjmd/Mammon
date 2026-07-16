"""Unit tests for the contract whitelist.

Covers case-insensitive lookups, risk-level resolution, transaction-target
validation in strict/non-strict modes, block-list handling, add/remove,
custom-whitelist file loading (including malformed-JSON tolerance), and the
per-network singleton.
"""

import json


import src.security.contract_whitelist as cw_module
from src.security.contract_whitelist import (
    ContractWhitelist,
    ContractInfo,
    ContractType,
    RiskLevel,
    PERMIT2_ADDRESS,
    get_contract_whitelist,
)
from tests.unit.security.conftest import USDC, AAVE_POOL, UNKNOWN


class TestIsWhitelisted:
    def test_checksummed_address(self, whitelist):
        assert whitelist.is_whitelisted(USDC)

    def test_lowercase_address(self, whitelist):
        assert whitelist.is_whitelisted(USDC.lower())

    def test_uppercase_hex_address(self, whitelist):
        assert whitelist.is_whitelisted("0x" + USDC[2:].upper())

    def test_unknown_not_whitelisted(self, whitelist):
        assert not whitelist.is_whitelisted(UNKNOWN)


class TestRiskLevel:
    def test_known_contract_risk_level(self, whitelist):
        assert whitelist.get_risk_level(USDC) == RiskLevel.LOW

    def test_unknown_defaults_to_blocked(self, whitelist):
        assert whitelist.get_risk_level(UNKNOWN) == RiskLevel.BLOCKED

    def test_blocked_contract_is_blocked(self, whitelist, monkeypatch):
        monkeypatch.setattr(cw_module, "BLOCKED_CONTRACTS", {USDC.lower()})
        assert whitelist.get_risk_level(USDC) == RiskLevel.BLOCKED
        assert not whitelist.is_whitelisted(USDC)


class TestValidateTransactionTarget:
    def test_whitelisted_target_allowed(self, whitelist):
        allowed, reason, info = whitelist.validate_transaction_target(AAVE_POOL)
        assert allowed
        assert info is not None
        assert info.name == "Aave V3 Pool"

    def test_unknown_strict_blocked(self, whitelist):
        allowed, reason, info = whitelist.validate_transaction_target(UNKNOWN, strict_mode=True)
        assert not allowed
        assert info is None

    def test_unknown_non_strict_allowed(self, whitelist):
        allowed, reason, info = whitelist.validate_transaction_target(UNKNOWN, strict_mode=False)
        assert allowed
        assert "strict mode disabled" in reason.lower()
        assert info is None

    def test_blocked_risk_level_entry_denied(self, whitelist):
        whitelist.add_contract(
            ContractInfo(
                address=UNKNOWN,
                name="Deprecated Thing",
                protocol="test",
                contract_type=ContractType.OTHER,
                risk_level=RiskLevel.BLOCKED,
            )
        )
        allowed, reason, info = whitelist.validate_transaction_target(UNKNOWN)
        assert not allowed
        assert info is not None  # present but blocked


class TestAddRemove:
    def test_add_then_whitelisted_mixed_case(self, whitelist):
        addr = "0xAbCdEf0000000000000000000000000000000001"
        whitelist.add_contract(
            ContractInfo(
                address=addr,
                name="Custom",
                protocol="custom",
                contract_type=ContractType.OTHER,
            )
        )
        assert whitelist.is_whitelisted(addr.lower())
        assert whitelist.is_whitelisted(addr.upper().replace("0X", "0x"))

    def test_remove_round_trip(self, whitelist):
        assert whitelist.remove_contract(USDC)
        assert not whitelist.is_whitelisted(USDC)

    def test_remove_missing_returns_false(self, whitelist):
        assert not whitelist.remove_contract(UNKNOWN)


class TestHelpers:
    def test_is_permit2_case_insensitive(self, whitelist):
        assert whitelist.is_permit2(PERMIT2_ADDRESS.upper().replace("0X", "0x"))
        assert not whitelist.is_permit2(USDC)

    def test_get_all_by_protocol_case_insensitive(self, whitelist):
        aave = whitelist.get_all_by_protocol("AAVE")
        assert aave and all(c.protocol == "aave" for c in aave)

    def test_export_is_json_serializable(self, whitelist):
        exported = whitelist.export_whitelist()
        # Round-trips through JSON without error.
        assert json.loads(json.dumps(exported))
        assert USDC.lower() in exported


class TestCustomWhitelistFile:
    def test_loads_custom_entries(self, tmp_path, monkeypatch):
        custom = {
            UNKNOWN.lower(): {
                "name": "Custom Pool",
                "protocol": "custom",
                "type": "LENDING_POOL",  # ContractType member name (loader uses name lookup)
                "risk_level": "MEDIUM",
            }
        }
        path = tmp_path / "custom.json"
        path.write_text(json.dumps(custom))
        monkeypatch.setenv("CONTRACT_WHITELIST_PATH", str(path))

        wl = ContractWhitelist()
        assert wl.is_whitelisted(UNKNOWN)
        assert wl.get_risk_level(UNKNOWN) == RiskLevel.MEDIUM

    def test_malformed_json_tolerated(self, tmp_path, monkeypatch):
        path = tmp_path / "bad.json"
        path.write_text("{ this is not json")
        monkeypatch.setenv("CONTRACT_WHITELIST_PATH", str(path))

        wl = ContractWhitelist()  # must not raise
        # Defaults still intact.
        assert wl.is_whitelisted(USDC)


class TestSingleton:
    def test_singleton_cached_per_network(self):
        a = get_contract_whitelist("base-mainnet")
        b = get_contract_whitelist("base-mainnet")
        assert a is b

    def test_different_network_new_instance(self):
        a = get_contract_whitelist("base-mainnet")
        b = get_contract_whitelist("base-sepolia")
        assert a is not b
        assert b.network == "base-sepolia"
