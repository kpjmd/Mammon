"""Transaction security validator for MAMMON.

Provides pre-transaction security validation including:
- EIP-7702 delegation attack detection
- Permit2 hidden authorization detection
- Contract whitelist enforcement
- Suspicious pattern detection

Security Note:
This is a critical security component. All transactions MUST pass
validation before execution. Block any suspicious activity.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from decimal import Decimal
from eth_utils import to_checksum_address
import re

from src.security.contract_whitelist import (
    ContractWhitelist,
    ContractInfo,
    RiskLevel,
    PERMIT2_ADDRESS,
    get_contract_whitelist,
)
from src.wallet.tiered_config import WalletTier, TierConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ThreatType(Enum):
    """Types of security threats detected."""

    EIP7702_DELEGATION = "eip7702_delegation"
    PERMIT2_UNLIMITED = "permit2_unlimited"
    PERMIT2_SUSPICIOUS = "permit2_suspicious"
    UNKNOWN_CONTRACT = "unknown_contract"
    BLOCKED_CONTRACT = "blocked_contract"
    HIGH_VALUE_TO_EOA = "high_value_to_eoa"
    SUSPICIOUS_DATA = "suspicious_data"
    SELF_DESTRUCT = "self_destruct"
    DELEGATECALL = "delegatecall"
    CREATE2_DEPLOYMENT = "create2_deployment"
    EXCESSIVE_APPROVAL = "excessive_approval"


class ValidationSeverity(Enum):
    """Severity of validation findings."""

    INFO = "info"           # Informational, no action needed
    WARNING = "warning"     # Proceed with caution
    CRITICAL = "critical"   # Block transaction


@dataclass
class ThreatDetection:
    """A detected security threat.

    Attributes:
        threat_type: Type of threat detected
        severity: Severity level
        description: Human-readable description
        details: Additional details about the threat
        recommended_action: What to do about it
    """

    threat_type: ThreatType
    severity: ValidationSeverity
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    recommended_action: str = "Block transaction"


@dataclass
class ValidationResult:
    """Result of transaction validation.

    Attributes:
        is_valid: Whether the transaction should be allowed
        risk_level: Overall risk level
        threats: List of detected threats
        warnings: List of warning messages
        contract_info: Info about the target contract (if whitelisted)
        rejection_reason: Reason for rejection (if blocked)
    """

    is_valid: bool
    risk_level: RiskLevel
    threats: List[ThreatDetection] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    contract_info: Optional[ContractInfo] = None
    rejection_reason: Optional[str] = None

    @property
    def has_critical_threats(self) -> bool:
        """Check if any critical threats were detected."""
        return any(t.severity == ValidationSeverity.CRITICAL for t in self.threats)

    @property
    def threat_summary(self) -> str:
        """Get a summary of detected threats."""
        if not self.threats:
            return "No threats detected"
        return "; ".join(t.description for t in self.threats)


# EIP-7702 Constants
# EIP-7702 authorization list designator
EIP7702_TX_TYPE = 0x04  # Type 4 transaction
EIP7702_AUTH_PREFIX = bytes.fromhex("ef0100")  # Authorization designator

# Permit2 Constants
PERMIT2_CONTRACT = PERMIT2_ADDRESS

# Permit2 function selectors
PERMIT2_SELECTORS = {
    "permit": "0x2b67b570",                    # permit(address,...)
    "permitTransferFrom": "0x30f28b7a",        # permitTransferFrom(...)
    "permitTransferFromBatch": "0xedd9444b",   # permitTransferFromBatch(...)
    "permitWitnessTransferFrom": "0x137c29fe", # permitWitnessTransferFrom(...)
    "approve": "0x87517c45",                   # approve(address,address,uint160,uint48)
    "lockdown": "0xcc53287f",                  # lockdown(...)
}

# Dangerous function selectors (general)
DANGEROUS_SELECTORS = {
    "selfdestruct": "0xff",                   # SELFDESTRUCT opcode
    "delegatecall": "0xf4",                   # DELEGATECALL opcode
    "setCode": "0x3659cfe6",                  # setCode pattern
    "upgradeTo": "0x3659cfe6",                # Proxy upgrade
    "upgradeToAndCall": "0x4f1ef286",         # Proxy upgrade with call
}

# Maximum safe approval amount (1 trillion tokens with 18 decimals)
MAX_SAFE_APPROVAL = 10**30

# Patterns that might indicate hidden delegation
SUSPICIOUS_PATTERNS = [
    re.compile(rb'\xef\x01\x00'),  # EIP-7702 authorization prefix
    re.compile(rb'\x04[\x00-\xff]{32}'),  # Type 4 transaction pattern
]


class TransactionValidator:
    """Validates transactions for security threats.

    Checks transactions against multiple security rules before
    allowing execution. All transactions must pass validation.
    """

    def __init__(
        self,
        whitelist: Optional[ContractWhitelist] = None,
        strict_mode: bool = True,
        eip7702_detection: bool = True,
        permit2_detection: bool = True,
    ):
        """Initialize the transaction validator.

        Args:
            whitelist: Contract whitelist to use
            strict_mode: If True, block unknown contracts
            eip7702_detection: Enable EIP-7702 detection
            permit2_detection: Enable Permit2 detection
        """
        self.whitelist = whitelist or get_contract_whitelist()
        self.strict_mode = strict_mode
        self.eip7702_detection = eip7702_detection
        self.permit2_detection = permit2_detection

        logger.info(
            "TransactionValidator initialized",
            extra={
                "strict_mode": strict_mode,
                "eip7702_detection": eip7702_detection,
                "permit2_detection": permit2_detection,
            }
        )

    def validate_transaction(
        self,
        to_address: str,
        value: int,
        data: bytes,
        from_address: Optional[str] = None,
        tier_config: Optional[TierConfig] = None,
    ) -> ValidationResult:
        """Validate a transaction for security threats.

        Args:
            to_address: Transaction destination
            value: ETH value in wei
            data: Transaction calldata
            from_address: Sender address (optional)
            tier_config: Wallet tier config for risk level filtering

        Returns:
            ValidationResult with validation outcome
        """
        threats: List[ThreatDetection] = []
        warnings: List[str] = []
        contract_info: Optional[ContractInfo] = None

        # 1. Check contract whitelist
        is_whitelisted, reason, contract_info = self.whitelist.validate_transaction_target(
            to_address, self.strict_mode
        )

        if not is_whitelisted:
            if self.whitelist.is_blocked(to_address):
                threats.append(ThreatDetection(
                    threat_type=ThreatType.BLOCKED_CONTRACT,
                    severity=ValidationSeverity.CRITICAL,
                    description=f"Target address is blocked: {reason}",
                    details={"address": to_address},
                ))
            else:
                threats.append(ThreatDetection(
                    threat_type=ThreatType.UNKNOWN_CONTRACT,
                    severity=ValidationSeverity.CRITICAL,
                    description=f"Target address not whitelisted: {to_address}",
                    details={"address": to_address},
                ))

        # 2. Check tier-specific risk levels
        if tier_config and contract_info:
            contract_risk = contract_info.risk_level
            if contract_risk not in tier_config.allowed_risk_levels:
                threats.append(ThreatDetection(
                    threat_type=ThreatType.UNKNOWN_CONTRACT,
                    severity=ValidationSeverity.CRITICAL,
                    description=f"Contract risk level {contract_risk.value} not allowed for {tier_config.tier.value} wallet",
                    details={
                        "contract_risk": contract_risk.value,
                        "allowed_risks": [r.value for r in tier_config.allowed_risk_levels],
                    },
                ))

        # 3. EIP-7702 Detection
        if self.eip7702_detection:
            eip7702_threat = self._detect_eip7702(data, to_address)
            if eip7702_threat:
                threats.append(eip7702_threat)

        # 4. Permit2 Detection
        if self.permit2_detection:
            permit2_threats = self._detect_permit2_risks(to_address, data)
            threats.extend(permit2_threats)

        # 5. Suspicious data patterns
        data_threats = self._detect_suspicious_patterns(data)
        threats.extend(data_threats)

        # 6. Dangerous function calls
        function_threats = self._detect_dangerous_functions(data)
        threats.extend(function_threats)

        # 7. Excessive approval detection
        approval_threat = self._detect_excessive_approval(data)
        if approval_threat:
            threats.append(approval_threat)

        # Determine overall validity and risk level
        has_critical = any(t.severity == ValidationSeverity.CRITICAL for t in threats)
        has_warning = any(t.severity == ValidationSeverity.WARNING for t in threats)

        if has_critical:
            risk_level = RiskLevel.BLOCKED
            is_valid = False
            rejection_reason = "; ".join(
                t.description for t in threats if t.severity == ValidationSeverity.CRITICAL
            )
        elif has_warning:
            risk_level = RiskLevel.HIGH
            is_valid = True  # Allow with warnings
            rejection_reason = None
            warnings.extend(t.description for t in threats if t.severity == ValidationSeverity.WARNING)
        else:
            risk_level = contract_info.risk_level if contract_info else RiskLevel.LOW
            is_valid = True
            rejection_reason = None

        result = ValidationResult(
            is_valid=is_valid,
            risk_level=risk_level,
            threats=threats,
            warnings=warnings,
            contract_info=contract_info,
            rejection_reason=rejection_reason,
        )

        # Log validation result
        if not is_valid:
            logger.warning(
                f"Transaction BLOCKED: {result.threat_summary}",
                extra={
                    "to_address": to_address,
                    "threats": [t.threat_type.value for t in threats],
                }
            )
        elif threats:
            logger.info(
                f"Transaction allowed with warnings: {result.threat_summary}",
                extra={
                    "to_address": to_address,
                    "warnings": warnings,
                }
            )

        return result

    def _detect_eip7702(
        self,
        data: bytes,
        to_address: str
    ) -> Optional[ThreatDetection]:
        """Detect EIP-7702 delegation attacks.

        EIP-7702 allows EOAs to temporarily set code via authorization.
        This can be abused to steal funds by delegating control to malicious code.

        Args:
            data: Transaction calldata
            to_address: Transaction destination

        Returns:
            ThreatDetection if EIP-7702 delegation detected
        """
        # Check for EIP-7702 authorization designator in data
        if data and EIP7702_AUTH_PREFIX in data:
            return ThreatDetection(
                threat_type=ThreatType.EIP7702_DELEGATION,
                severity=ValidationSeverity.CRITICAL,
                description="EIP-7702 delegation authorization detected in transaction data",
                details={
                    "pattern": "0xef0100",
                    "attack_type": "EOA code delegation",
                },
                recommended_action="BLOCK - This could delegate control of your wallet to malicious code",
            )

        # Check for suspicious patterns that might hide delegation
        for pattern in SUSPICIOUS_PATTERNS:
            if data and pattern.search(data):
                return ThreatDetection(
                    threat_type=ThreatType.EIP7702_DELEGATION,
                    severity=ValidationSeverity.CRITICAL,
                    description="Suspicious pattern matching EIP-7702 delegation detected",
                    details={
                        "pattern_match": True,
                        "attack_type": "Potential hidden delegation",
                    },
                    recommended_action="BLOCK - Potential hidden EIP-7702 delegation",
                )

        return None

    def _detect_permit2_risks(
        self,
        to_address: str,
        data: bytes
    ) -> List[ThreatDetection]:
        """Detect risky Permit2 operations.

        Permit2 can grant token approvals without explicit approve() calls.
        This can be abused to grant unlimited approvals to attackers.

        Args:
            to_address: Transaction destination
            data: Transaction calldata

        Returns:
            List of ThreatDetection for Permit2 risks
        """
        threats: List[ThreatDetection] = []

        # Check if destination is Permit2
        if to_address.lower() == PERMIT2_CONTRACT:
            # Add warning for any Permit2 interaction
            threats.append(ThreatDetection(
                threat_type=ThreatType.PERMIT2_SUSPICIOUS,
                severity=ValidationSeverity.WARNING,
                description="Direct interaction with Permit2 contract",
                details={"contract": "Permit2"},
                recommended_action="Verify this is an intentional Permit2 operation",
            ))

        # Check for Permit2 function selectors in calldata
        if data and len(data) >= 4:
            selector = data[:4].hex()

            for func_name, func_selector in PERMIT2_SELECTORS.items():
                if f"0x{selector}" == func_selector:
                    severity = ValidationSeverity.WARNING
                    if func_name in ["approve", "permit"]:
                        # These are particularly risky
                        severity = ValidationSeverity.CRITICAL if self.strict_mode else ValidationSeverity.WARNING

                    threats.append(ThreatDetection(
                        threat_type=ThreatType.PERMIT2_SUSPICIOUS,
                        severity=severity,
                        description=f"Permit2 {func_name}() call detected",
                        details={
                            "function": func_name,
                            "selector": func_selector,
                        },
                        recommended_action=f"Verify Permit2 {func_name} parameters carefully",
                    ))

        # Check for Permit2 address in calldata (hidden approvals)
        if data and bytes.fromhex(PERMIT2_CONTRACT[2:]) in data:
            # Permit2 address found in calldata - could be granting approval
            if to_address.lower() != PERMIT2_CONTRACT:
                threats.append(ThreatDetection(
                    threat_type=ThreatType.PERMIT2_SUSPICIOUS,
                    severity=ValidationSeverity.WARNING,
                    description="Permit2 address found in transaction data (potential hidden approval)",
                    details={
                        "permit2_in_data": True,
                        "target_contract": to_address,
                    },
                    recommended_action="Review transaction for hidden Permit2 approvals",
                ))

        return threats

    def _detect_suspicious_patterns(self, data: bytes) -> List[ThreatDetection]:
        """Detect suspicious patterns in transaction data.

        Args:
            data: Transaction calldata

        Returns:
            List of ThreatDetection for suspicious patterns
        """
        threats: List[ThreatDetection] = []

        if not data:
            return threats

        # Check for common attack patterns

        # Large data with embedded addresses (potential hidden operations)
        if len(data) > 1000:
            # Count address-like patterns (20 bytes)
            address_count = len(re.findall(rb'[\x00-\xff]{20}', data))
            if address_count > 10:
                threats.append(ThreatDetection(
                    threat_type=ThreatType.SUSPICIOUS_DATA,
                    severity=ValidationSeverity.WARNING,
                    description=f"Large transaction data with many embedded addresses ({address_count})",
                    details={"data_length": len(data), "address_count": address_count},
                    recommended_action="Review transaction carefully - may contain hidden operations",
                ))

        return threats

    def _detect_dangerous_functions(self, data: bytes) -> List[ThreatDetection]:
        """Detect dangerous function calls.

        Args:
            data: Transaction calldata

        Returns:
            List of ThreatDetection for dangerous functions
        """
        threats: List[ThreatDetection] = []

        if not data or len(data) < 4:
            return threats

        selector = f"0x{data[:4].hex()}"

        for func_name, func_selector in DANGEROUS_SELECTORS.items():
            if selector == func_selector or (len(func_selector) == 4 and data[0:1].hex() == func_selector[2:]):
                threats.append(ThreatDetection(
                    threat_type=ThreatType.DELEGATECALL if "delegate" in func_name.lower()
                        else ThreatType.SELF_DESTRUCT if "destruct" in func_name.lower()
                        else ThreatType.SUSPICIOUS_DATA,
                    severity=ValidationSeverity.CRITICAL,
                    description=f"Dangerous function call detected: {func_name}",
                    details={"function": func_name, "selector": selector},
                    recommended_action=f"BLOCK - {func_name} can be used maliciously",
                ))

        return threats

    def _detect_excessive_approval(self, data: bytes) -> Optional[ThreatDetection]:
        """Detect excessive token approvals (unlimited approvals).

        Args:
            data: Transaction calldata

        Returns:
            ThreatDetection if excessive approval detected
        """
        if not data or len(data) < 68:  # approve(address,uint256) is 4 + 32 + 32 bytes
            return None

        # Check for standard approve selector
        selector = data[:4].hex()
        approve_selector = "095ea7b3"  # approve(address,uint256)

        if selector == approve_selector:
            # Extract approval amount (last 32 bytes of a 68-byte approve call)
            try:
                amount = int.from_bytes(data[36:68], "big")

                # Check for unlimited approval (type(uint256).max)
                uint256_max = 2**256 - 1
                if amount == uint256_max or amount > MAX_SAFE_APPROVAL:
                    return ThreatDetection(
                        threat_type=ThreatType.EXCESSIVE_APPROVAL,
                        severity=ValidationSeverity.WARNING,
                        description="Unlimited or excessive token approval detected",
                        details={
                            "approval_amount": str(amount),
                            "is_unlimited": amount == uint256_max,
                        },
                        recommended_action="Consider using a limited approval amount instead",
                    )
            except Exception:
                pass  # Couldn't parse approval amount

        return None

    def validate_batch(
        self,
        transactions: List[Dict[str, Any]],
        tier_config: Optional[TierConfig] = None,
    ) -> List[ValidationResult]:
        """Validate a batch of transactions.

        Args:
            transactions: List of transaction dicts with 'to', 'value', 'data'
            tier_config: Wallet tier configuration

        Returns:
            List of ValidationResult for each transaction
        """
        results = []
        for tx in transactions:
            result = self.validate_transaction(
                to_address=tx.get("to", ""),
                value=tx.get("value", 0),
                data=tx.get("data", b""),
                from_address=tx.get("from"),
                tier_config=tier_config,
            )
            results.append(result)
        return results

    def is_safe(
        self,
        to_address: str,
        value: int = 0,
        data: bytes = b"",
    ) -> bool:
        """Quick check if a transaction is safe.

        Args:
            to_address: Transaction destination
            value: ETH value
            data: Transaction data

        Returns:
            True if transaction passes validation
        """
        result = self.validate_transaction(to_address, value, data)
        return result.is_valid


def get_transaction_validator(
    strict_mode: bool = True,
    eip7702_detection: bool = True,
    permit2_detection: bool = True,
) -> TransactionValidator:
    """Get a configured transaction validator.

    Args:
        strict_mode: Block unknown contracts
        eip7702_detection: Enable EIP-7702 detection
        permit2_detection: Enable Permit2 detection

    Returns:
        Configured TransactionValidator
    """
    return TransactionValidator(
        strict_mode=strict_mode,
        eip7702_detection=eip7702_detection,
        permit2_detection=permit2_detection,
    )
