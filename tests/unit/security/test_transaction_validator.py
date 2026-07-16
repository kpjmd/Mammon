"""Unit tests for the transaction security validator.

Covers EIP-7702 detection, Permit2 risk detection, dangerous-selector
detection, excessive-approval detection, whitelist integration, and result
aggregation. This layer was the direct remediation for the Dec-2 wallet drain
and previously had zero automated coverage.

Several tests deliberately assert the validator's *current* matching semantics
(substring vs offset-0, opcode-byte heuristics) so that future refactors are
forced to acknowledge these behaviors rather than change them silently.
"""

import pytest

from src.security.transaction_validator import (
    TransactionValidator,
    ThreatType,
    PERMIT2_SELECTORS,
    MAX_SAFE_APPROVAL,
    EIP7702_AUTH_PREFIX,
)
from src.security.contract_whitelist import (
    RiskLevel,
)
from tests.unit.security.conftest import (
    USDC,
    AAVE_POOL,
    PERMIT2,
    MORPHO_BLUE,
    UNKNOWN,
    selector,
    erc20_approve_calldata,
)


def _threat_types(result):
    return {t.threat_type for t in result.threats}


class TestBenignTransactions:
    """Legitimate transactions must pass cleanly."""

    def test_whitelisted_approve_is_valid(self, validator):
        data = erc20_approve_calldata(AAVE_POOL, 500 * 10**6)
        result = validator.validate_transaction(USDC, 0, data)
        assert result.is_valid
        assert result.threats == []
        assert result.rejection_reason is None

    def test_whitelisted_eth_transfer_no_data(self, validator):
        result = validator.validate_transaction(USDC, 10**15, b"")
        assert result.is_valid
        assert result.threats == []

    def test_risk_level_reflects_contract_when_clean(self, validator):
        # Morpho Blue is MEDIUM risk in the default whitelist.
        result = validator.validate_transaction(MORPHO_BLUE, 0, b"")
        assert result.is_valid
        assert result.risk_level == RiskLevel.MEDIUM


class TestEIP7702Detection:
    """EIP-7702 delegation detection."""

    def test_auth_prefix_at_offset_zero_is_critical(self, validator):
        data = EIP7702_AUTH_PREFIX + bytes(40)
        result = validator.validate_transaction(USDC, 0, data)
        assert not result.is_valid
        assert ThreatType.EIP7702_DELEGATION in _threat_types(result)
        assert result.risk_level == RiskLevel.BLOCKED

    def test_auth_prefix_embedded_is_still_detected(self, validator):
        # ef0100 is matched anywhere in calldata (substring semantics), so an
        # otherwise-benign payload that embeds it is still blocked. Asserted
        # intentionally: the detection is a substring search, not offset-0.
        data = erc20_approve_calldata(AAVE_POOL, 1) + EIP7702_AUTH_PREFIX
        result = validator.validate_transaction(USDC, 0, data)
        assert not result.is_valid
        assert ThreatType.EIP7702_DELEGATION in _threat_types(result)

    def test_empty_data_has_no_eip7702_threat(self, validator):
        result = validator.validate_transaction(USDC, 0, b"")
        assert ThreatType.EIP7702_DELEGATION not in _threat_types(result)

    def test_benign_calldata_with_0x04_byte_is_valid(self, validator):
        """Regression: a legitimate approve whose spender word contains a 0x04
        byte followed by >=32 bytes must NOT be flagged as EIP-7702.

        The tx-type byte (0x04) can never appear in calldata (the validator
        only ever sees calldata, never the transaction envelope), so the old
        ``\\x04[\\x00-\\xff]{32}`` pattern was pure false-positive surface that
        could brick real deposits.
        """
        # spender address begins with 0x04 -> its padded word is
        # 00..00 04 xx.. and 32+ bytes (rest of word + amount word) follow.
        spender = "0x04" + "11" * 19
        data = erc20_approve_calldata(spender, 100 * 10**6)
        assert b"\x04" in data  # precondition: the trigger byte is present
        result = validator.validate_transaction(USDC, 0, data)
        assert result.is_valid, result.threat_summary
        assert ThreatType.EIP7702_DELEGATION not in _threat_types(result)


class TestPermit2Detection:
    """Permit2 hidden-approval detection."""

    @pytest.mark.parametrize("func_name", list(PERMIT2_SELECTORS.keys()))
    def test_permit2_selector_at_offset_zero_flagged(self, validator, func_name):
        sel = selector(PERMIT2_SELECTORS[func_name][2:])
        data = sel + bytes(64)
        result = validator.validate_transaction(USDC, 0, data)
        assert ThreatType.PERMIT2_SUSPICIOUS in _threat_types(result)

    def test_permit2_approve_is_critical_in_strict_mode(self, validator):
        data = selector(PERMIT2_SELECTORS["approve"][2:]) + bytes(64)
        result = validator.validate_transaction(USDC, 0, data)
        assert not result.is_valid  # approve/permit are CRITICAL in strict mode

    def test_permit2_approve_is_warning_in_non_strict_mode(self, whitelist):
        v = TransactionValidator(whitelist=whitelist, strict_mode=False)
        data = selector(PERMIT2_SELECTORS["approve"][2:]) + bytes(64)
        result = v.validate_transaction(USDC, 0, data)
        # WARNING severity -> allowed, but still surfaced.
        assert result.is_valid
        assert ThreatType.PERMIT2_SUSPICIOUS in _threat_types(result)

    def test_permit2_lockdown_is_warning_only(self, validator):
        data = selector(PERMIT2_SELECTORS["lockdown"][2:]) + bytes(64)
        result = validator.validate_transaction(USDC, 0, data)
        # Non-approve/permit selectors are WARNING -> transaction still valid.
        assert result.is_valid
        assert result.risk_level == RiskLevel.HIGH

    def test_permit2_selector_at_nonzero_offset_not_detected(self, validator):
        # Selector checks only look at offset 0; a Permit2 selector buried at
        # offset 4 is not matched. Asserted to document offset-0-only behavior.
        data = bytes(4) + selector(PERMIT2_SELECTORS["approve"][2:]) + bytes(64)
        result = validator.validate_transaction(USDC, 0, data)
        assert ThreatType.PERMIT2_SUSPICIOUS not in _threat_types(result)

    def test_direct_call_to_permit2_warns(self, validator):
        result = validator.validate_transaction(PERMIT2, 0, b"")
        assert ThreatType.PERMIT2_SUSPICIOUS in _threat_types(result)
        assert result.is_valid  # direct interaction is a warning, not a block

    def test_permit2_address_embedded_in_calldata_warns(self, validator):
        permit2_bytes = bytes.fromhex(PERMIT2[2:])
        data = erc20_approve_calldata(AAVE_POOL, 1)[:36] + bytes(12) + permit2_bytes
        result = validator.validate_transaction(USDC, 0, data)
        assert ThreatType.PERMIT2_SUSPICIOUS in _threat_types(result)


class TestDangerousSelectors:
    """Dangerous function-selector detection."""

    def test_shared_selector_yields_two_threats(self, validator):
        # setCode and upgradeTo share selector 0x3659cfe6, so a single call
        # produces two dangerous-function threats. Asserted intentionally.
        data = selector("3659cfe6") + bytes(32)
        result = validator.validate_transaction(AAVE_POOL, 0, data)
        funcs = [t.details.get("function") for t in result.threats]
        assert "setCode" in funcs and "upgradeTo" in funcs
        assert not result.is_valid

    def test_upgrade_to_and_call_selector_is_critical(self, validator):
        data = selector("4f1ef286") + bytes(32)
        result = validator.validate_transaction(AAVE_POOL, 0, data)
        assert not result.is_valid
        assert any(t.details.get("function") == "upgradeToAndCall" for t in result.threats)

    def test_first_byte_0xff_heuristic_blocks(self, validator):
        # DANGEROUS_SELECTORS maps selfdestruct->0xff (an opcode byte), matched
        # against the first calldata byte. This is a deliberately broad
        # heuristic; asserted with its false-positive tradeoff acknowledged.
        data = bytes([0xFF]) + bytes(40)
        result = validator.validate_transaction(AAVE_POOL, 0, data)
        assert not result.is_valid
        assert ThreatType.SELF_DESTRUCT in _threat_types(result)

    def test_first_byte_0xf4_heuristic_blocks(self, validator):
        data = bytes([0xF4]) + bytes(40)
        result = validator.validate_transaction(AAVE_POOL, 0, data)
        assert not result.is_valid
        assert ThreatType.DELEGATECALL in _threat_types(result)

    def test_dangerous_selector_at_offset_four_not_detected(self, validator):
        data = bytes(4) + selector("3659cfe6") + bytes(32)
        result = validator.validate_transaction(AAVE_POOL, 0, data)
        assert not any(
            t.details.get("function") in ("setCode", "upgradeTo") for t in result.threats
        )

    def test_data_shorter_than_selector_has_no_threat(self, validator):
        result = validator.validate_transaction(AAVE_POOL, 0, b"\x01\x02")
        assert ThreatType.SUSPICIOUS_DATA not in _threat_types(result)


class TestExcessiveApproval:
    """Unlimited / excessive ERC20 approval detection."""

    def test_unlimited_approval_warns_but_allowed(self, validator):
        data = erc20_approve_calldata(AAVE_POOL, 2**256 - 1)
        result = validator.validate_transaction(USDC, 0, data)
        assert result.is_valid
        assert ThreatType.EXCESSIVE_APPROVAL in _threat_types(result)

    def test_above_max_safe_approval_warns(self, validator):
        data = erc20_approve_calldata(AAVE_POOL, MAX_SAFE_APPROVAL + 1)
        result = validator.validate_transaction(USDC, 0, data)
        assert ThreatType.EXCESSIVE_APPROVAL in _threat_types(result)

    def test_reasonable_approval_is_clean(self, validator):
        data = erc20_approve_calldata(AAVE_POOL, 1000 * 10**6)
        result = validator.validate_transaction(USDC, 0, data)
        assert ThreatType.EXCESSIVE_APPROVAL not in _threat_types(result)

    def test_truncated_approve_calldata_ignored(self, validator):
        data = selector("095ea7b3") + bytes(10)  # < 68 bytes
        result = validator.validate_transaction(USDC, 0, data)
        assert ThreatType.EXCESSIVE_APPROVAL not in _threat_types(result)


class TestWhitelistIntegration:
    """Whitelist enforcement inside validation."""

    def test_unknown_contract_blocked_in_strict_mode(self, validator):
        result = validator.validate_transaction(UNKNOWN, 0, b"")
        assert not result.is_valid
        assert ThreatType.UNKNOWN_CONTRACT in _threat_types(result)
        assert result.risk_level == RiskLevel.BLOCKED
        assert result.rejection_reason

    def test_unknown_contract_allowed_in_non_strict_mode(self, whitelist):
        v = TransactionValidator(whitelist=whitelist, strict_mode=False)
        result = v.validate_transaction(UNKNOWN, 0, b"")
        assert result.is_valid

    def test_blocked_contract_flagged(self, validator, monkeypatch):
        monkeypatch.setattr(
            "src.security.contract_whitelist.BLOCKED_CONTRACTS",
            {UNKNOWN.lower()},
        )
        result = validator.validate_transaction(UNKNOWN, 0, b"")
        assert not result.is_valid
        assert ThreatType.BLOCKED_CONTRACT in _threat_types(result)


class TestResultAggregation:
    """Aggregation of threats into a ValidationResult."""

    def test_critical_and_warning_together_blocks(self, validator):
        # Unknown contract (critical) + unlimited approval (warning).
        data = erc20_approve_calldata(AAVE_POOL, 2**256 - 1)
        result = validator.validate_transaction(UNKNOWN, 0, data)
        assert not result.is_valid
        assert result.has_critical_threats
        # rejection_reason should reference only critical threats.
        assert "not whitelisted" in result.rejection_reason.lower()

    def test_threat_summary_lists_descriptions(self, validator):
        result = validator.validate_transaction(UNKNOWN, 0, b"")
        assert "whitelist" in result.threat_summary.lower()

    def test_validate_batch_returns_per_tx_results(self, validator):
        txs = [
            {"to": USDC, "value": 0, "data": erc20_approve_calldata(AAVE_POOL, 1)},
            {"to": UNKNOWN, "value": 0, "data": b""},
        ]
        results = validator.validate_batch(txs)
        assert len(results) == 2
        assert results[0].is_valid
        assert not results[1].is_valid

    def test_is_safe_convenience(self, validator):
        assert validator.is_safe(USDC, 0, erc20_approve_calldata(AAVE_POOL, 1))
        assert not validator.is_safe(UNKNOWN, 0, b"")
