"""Contract whitelist for MAMMON security.

Enforces that transactions can only interact with known, verified contracts.
This prevents attacks where malicious contracts are substituted for legitimate ones.

Security Note:
- Only interact with whitelisted contracts
- New contracts must be manually added after verification
- Block transactions to unknown addresses by default
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set
import json
import os

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContractType(Enum):
    """Types of contracts in the whitelist."""

    TOKEN = "token"            # ERC20 tokens
    LENDING_POOL = "lending"   # Aave, Moonwell, Morpho pools
    DEX_ROUTER = "dex_router"  # Uniswap, Aerodrome routers
    DEX_FACTORY = "factory"    # Pool factory contracts
    ORACLE = "oracle"          # Price oracles (Chainlink, etc.)
    WRAPPER = "wrapper"        # WETH and similar wrappers
    PERMIT2 = "permit2"        # Uniswap Permit2 (monitored)
    GOVERNANCE = "governance"  # Protocol governance
    OTHER = "other"


class RiskLevel(Enum):
    """Risk level of contracts."""

    LOW = "low"           # Well-established, heavily audited
    MEDIUM = "medium"     # Established but newer or less audited
    HIGH = "high"         # New contracts or complex interactions
    BLOCKED = "blocked"   # Known malicious or deprecated


@dataclass
class ContractInfo:
    """Information about a whitelisted contract.

    Attributes:
        address: Contract address (checksummed)
        name: Human-readable name
        protocol: Protocol name (aave, moonwell, etc.)
        contract_type: Type of contract
        risk_level: Risk assessment
        network: Network the contract is on
        verified_date: When this contract was verified
        notes: Additional notes about the contract
    """

    address: str
    name: str
    protocol: str
    contract_type: ContractType
    risk_level: RiskLevel = RiskLevel.LOW
    network: str = "base-mainnet"
    verified_date: Optional[datetime] = None
    notes: str = ""

    def __post_init__(self):
        """Normalize address to lowercase for comparison."""
        self.address = self.address.lower()
        if self.verified_date is None:
            self.verified_date = datetime.utcnow()


# Known Permit2 address - monitored but allowed with warnings
PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3".lower()

# Known malicious or deprecated contracts (block list)
BLOCKED_CONTRACTS: Set[str] = {
    # Add known malicious addresses here as they're discovered
}


def _build_default_whitelist() -> Dict[str, ContractInfo]:
    """Build the default contract whitelist from protocol addresses.

    Returns:
        Dict mapping lowercase addresses to ContractInfo
    """
    whitelist: Dict[str, ContractInfo] = {}

    # ============================================================
    # TOKENS (ERC20)
    # ============================================================
    tokens = [
        ContractInfo(
            address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            name="USDC",
            protocol="circle",
            contract_type=ContractType.TOKEN,
            risk_level=RiskLevel.LOW,
            notes="Native USDC on Base",
        ),
        ContractInfo(
            address="0x4200000000000000000000000000000000000006",
            name="WETH",
            protocol="base",
            contract_type=ContractType.WRAPPER,
            risk_level=RiskLevel.LOW,
            notes="Wrapped ETH on Base",
        ),
        ContractInfo(
            address="0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
            name="DAI",
            protocol="makerdao",
            contract_type=ContractType.TOKEN,
            risk_level=RiskLevel.LOW,
            notes="DAI Stablecoin on Base",
        ),
        ContractInfo(
            address="0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
            name="USDbC",
            protocol="circle",
            contract_type=ContractType.TOKEN,
            risk_level=RiskLevel.MEDIUM,
            notes="Bridged USDC (legacy)",
        ),
        ContractInfo(
            address="0x940181a94A35A4569E4529A3CDfB74e38FD98631",
            name="AERO",
            protocol="aerodrome",
            contract_type=ContractType.TOKEN,
            risk_level=RiskLevel.MEDIUM,
            notes="Aerodrome governance token",
        ),
    ]

    # ============================================================
    # AAVE V3
    # ============================================================
    aave_contracts = [
        ContractInfo(
            address="0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
            name="Aave V3 Pool",
            protocol="aave",
            contract_type=ContractType.LENDING_POOL,
            risk_level=RiskLevel.LOW,
            notes="Main Aave V3 lending pool on Base",
        ),
        ContractInfo(
            address="0x2d8A3C5677189723C4cB8873CfC9C8976FDF38Ac",
            name="Aave V3 Pool Data Provider",
            protocol="aave",
            contract_type=ContractType.OTHER,
            risk_level=RiskLevel.LOW,
            notes="Aave V3 data provider for reserve info",
        ),
        ContractInfo(
            address="0x2Cc0Fc26eD4563A5ce5e8bdcfe1A2878676Ae156",
            name="Aave V3 Oracle",
            protocol="aave",
            contract_type=ContractType.ORACLE,
            risk_level=RiskLevel.LOW,
            notes="Aave V3 price oracle",
        ),
        ContractInfo(
            address="0x174446a6741300cD2E7C1b1A636Fee99c8F83502",
            name="Aave V3 UI Pool Data Provider",
            protocol="aave",
            contract_type=ContractType.OTHER,
            risk_level=RiskLevel.LOW,
            notes="Aave V3 UI data provider",
        ),
    ]

    # ============================================================
    # MOONWELL
    # ============================================================
    moonwell_contracts = [
        ContractInfo(
            address="0xfBb21d0380beE3312B33c4353c8936a0F13EF26C",
            name="Moonwell Comptroller",
            protocol="moonwell",
            contract_type=ContractType.LENDING_POOL,
            risk_level=RiskLevel.LOW,
            notes="Moonwell main comptroller on Base",
        ),
        ContractInfo(
            address="0xEdc817A28E8B93B03976FBd4a3dDBc9f7D176c22",
            name="Moonwell mUSDC",
            protocol="moonwell",
            contract_type=ContractType.LENDING_POOL,
            risk_level=RiskLevel.LOW,
            notes="Moonwell USDC market",
        ),
        ContractInfo(
            address="0x628ff693426583D9a7FB391E54366292F509D457",
            name="Moonwell mWETH",
            protocol="moonwell",
            contract_type=ContractType.LENDING_POOL,
            risk_level=RiskLevel.LOW,
            notes="Moonwell WETH market",
        ),
    ]

    # ============================================================
    # MORPHO
    # ============================================================
    morpho_contracts = [
        ContractInfo(
            address="0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
            name="Morpho Blue",
            protocol="morpho",
            contract_type=ContractType.LENDING_POOL,
            risk_level=RiskLevel.MEDIUM,
            notes="Morpho Blue core protocol",
        ),
        ContractInfo(
            address="0xBAa5CC21fd487B8Fcc2F632f3F4E8D37262a0842",
            name="MORPHO Token",
            protocol="morpho",
            contract_type=ContractType.TOKEN,
            risk_level=RiskLevel.MEDIUM,
            notes="Morpho governance token",
        ),
        ContractInfo(
            address="0x2DC205F24BCb6B311E5cdf0745B0741648Aebd3d",
            name="Morpho Chainlink Oracle V2",
            protocol="morpho",
            contract_type=ContractType.ORACLE,
            risk_level=RiskLevel.LOW,
            notes="Morpho price oracle",
        ),
    ]

    # ============================================================
    # AERODROME
    # ============================================================
    aerodrome_contracts = [
        ContractInfo(
            address="0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
            name="Aerodrome Router",
            protocol="aerodrome",
            contract_type=ContractType.DEX_ROUTER,
            risk_level=RiskLevel.LOW,
            notes="Aerodrome main router",
        ),
        ContractInfo(
            address="0x420DD381b31aEf6683db6B902084cB0FFECe40Da",
            name="Aerodrome Factory",
            protocol="aerodrome",
            contract_type=ContractType.DEX_FACTORY,
            risk_level=RiskLevel.LOW,
            notes="Aerodrome pool factory",
        ),
    ]

    # ============================================================
    # UNISWAP V3
    # ============================================================
    uniswap_contracts = [
        ContractInfo(
            address="0x6fF5693b99212Da76ad316178A184AB56D299b43",
            name="Uniswap Universal Router",
            protocol="uniswap",
            contract_type=ContractType.DEX_ROUTER,
            risk_level=RiskLevel.LOW,
            notes="Uniswap V3 Universal Router on Base",
        ),
        ContractInfo(
            address="0x2626664c2603336E57B271c5C0b26F421741e481",
            name="Uniswap SwapRouter02",
            protocol="uniswap",
            contract_type=ContractType.DEX_ROUTER,
            risk_level=RiskLevel.LOW,
            notes="Uniswap V3 SwapRouter02 on Base",
        ),
        ContractInfo(
            address="0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
            name="Uniswap V3 Factory",
            protocol="uniswap",
            contract_type=ContractType.DEX_FACTORY,
            risk_level=RiskLevel.LOW,
            notes="Uniswap V3 pool factory",
        ),
        ContractInfo(
            address="0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
            name="Uniswap Quoter V2",
            protocol="uniswap",
            contract_type=ContractType.OTHER,
            risk_level=RiskLevel.LOW,
            notes="Uniswap V3 quote helper",
        ),
    ]

    # ============================================================
    # PERMIT2 (Monitored - allowed with warnings)
    # ============================================================
    permit2_contracts = [
        ContractInfo(
            address=PERMIT2_ADDRESS,
            name="Permit2",
            protocol="uniswap",
            contract_type=ContractType.PERMIT2,
            risk_level=RiskLevel.MEDIUM,
            notes="MONITORED: Can grant token approvals. Verify all signatures.",
        ),
    ]

    # Combine all contracts
    all_contracts = (
        tokens
        + aave_contracts
        + moonwell_contracts
        + morpho_contracts
        + aerodrome_contracts
        + uniswap_contracts
        + permit2_contracts
    )

    for contract in all_contracts:
        whitelist[contract.address] = contract

    return whitelist


class ContractWhitelist:
    """Manager for contract whitelist enforcement.

    Provides methods to check if addresses are whitelisted and
    retrieve contract information.
    """

    def __init__(self, network: str = "base-mainnet"):
        """Initialize whitelist for a specific network.

        Args:
            network: Network identifier (e.g., "base-mainnet")
        """
        self.network = network
        self._whitelist: Dict[str, ContractInfo] = _build_default_whitelist()
        self._custom_whitelist_path = os.getenv("CONTRACT_WHITELIST_PATH")

        if self._custom_whitelist_path and os.path.exists(self._custom_whitelist_path):
            self._load_custom_whitelist()

        logger.info(
            f"ContractWhitelist initialized",
            extra={
                "network": network,
                "whitelisted_count": len(self._whitelist),
                "blocked_count": len(BLOCKED_CONTRACTS),
            }
        )

    def _load_custom_whitelist(self) -> None:
        """Load additional contracts from custom whitelist file."""
        try:
            with open(self._custom_whitelist_path, "r") as f:
                custom_contracts = json.load(f)

            for addr, info in custom_contracts.items():
                contract_info = ContractInfo(
                    address=addr,
                    name=info.get("name", "Unknown"),
                    protocol=info.get("protocol", "custom"),
                    contract_type=ContractType[info.get("type", "OTHER").upper()],
                    risk_level=RiskLevel[info.get("risk_level", "MEDIUM").upper()],
                    network=info.get("network", self.network),
                    notes=info.get("notes", "Custom whitelist entry"),
                )
                self._whitelist[contract_info.address] = contract_info

            logger.info(f"Loaded {len(custom_contracts)} custom whitelist entries")

        except Exception as e:
            logger.error(f"Failed to load custom whitelist: {e}")

    def is_whitelisted(self, address: str) -> bool:
        """Check if an address is whitelisted.

        Args:
            address: Contract address to check

        Returns:
            True if whitelisted, False otherwise
        """
        normalized = address.lower()
        return normalized in self._whitelist and normalized not in BLOCKED_CONTRACTS

    def is_blocked(self, address: str) -> bool:
        """Check if an address is explicitly blocked.

        Args:
            address: Contract address to check

        Returns:
            True if blocked, False otherwise
        """
        return address.lower() in BLOCKED_CONTRACTS

    def get_contract_info(self, address: str) -> Optional[ContractInfo]:
        """Get information about a whitelisted contract.

        Args:
            address: Contract address

        Returns:
            ContractInfo if whitelisted, None otherwise
        """
        return self._whitelist.get(address.lower())

    def get_risk_level(self, address: str) -> RiskLevel:
        """Get the risk level of a contract.

        Args:
            address: Contract address

        Returns:
            RiskLevel (BLOCKED if not whitelisted)
        """
        normalized = address.lower()

        if normalized in BLOCKED_CONTRACTS:
            return RiskLevel.BLOCKED

        contract_info = self._whitelist.get(normalized)
        if contract_info:
            return contract_info.risk_level

        return RiskLevel.BLOCKED  # Unknown = blocked

    def is_permit2(self, address: str) -> bool:
        """Check if address is the Permit2 contract.

        Args:
            address: Contract address

        Returns:
            True if Permit2
        """
        return address.lower() == PERMIT2_ADDRESS

    def add_contract(self, contract_info: ContractInfo) -> None:
        """Add a contract to the whitelist.

        Args:
            contract_info: Contract information to add
        """
        self._whitelist[contract_info.address] = contract_info
        logger.info(
            f"Added contract to whitelist",
            extra={
                "address": contract_info.address,
                "name": contract_info.name,
                "protocol": contract_info.protocol,
            }
        )

    def remove_contract(self, address: str) -> bool:
        """Remove a contract from the whitelist.

        Args:
            address: Contract address to remove

        Returns:
            True if removed, False if not found
        """
        normalized = address.lower()
        if normalized in self._whitelist:
            del self._whitelist[normalized]
            logger.warning(f"Removed contract from whitelist: {address}")
            return True
        return False

    def get_all_by_protocol(self, protocol: str) -> List[ContractInfo]:
        """Get all contracts for a specific protocol.

        Args:
            protocol: Protocol name (e.g., "aave", "moonwell")

        Returns:
            List of ContractInfo for the protocol
        """
        return [
            info for info in self._whitelist.values()
            if info.protocol.lower() == protocol.lower()
        ]

    def get_all_by_type(self, contract_type: ContractType) -> List[ContractInfo]:
        """Get all contracts of a specific type.

        Args:
            contract_type: Type of contract

        Returns:
            List of ContractInfo of that type
        """
        return [
            info for info in self._whitelist.values()
            if info.contract_type == contract_type
        ]

    def validate_transaction_target(
        self,
        to_address: str,
        strict_mode: bool = True
    ) -> tuple[bool, str, Optional[ContractInfo]]:
        """Validate a transaction target address.

        Args:
            to_address: Transaction destination address
            strict_mode: If True, block unknown addresses

        Returns:
            Tuple of (allowed: bool, reason: str, contract_info: Optional)
        """
        normalized = to_address.lower()

        # Check block list first
        if self.is_blocked(normalized):
            return False, "Address is on block list", None

        # Check whitelist
        contract_info = self.get_contract_info(normalized)

        if contract_info:
            # Whitelisted - check risk level
            if contract_info.risk_level == RiskLevel.BLOCKED:
                return False, f"Contract {contract_info.name} is deprecated/blocked", contract_info

            # Permit2 warning
            if contract_info.contract_type == ContractType.PERMIT2:
                logger.warning(
                    f"Transaction to Permit2 contract - verify signatures carefully",
                    extra={"address": to_address}
                )

            return True, f"Whitelisted: {contract_info.name} ({contract_info.protocol})", contract_info

        # Not whitelisted
        if strict_mode:
            return False, f"Address {to_address} not in whitelist", None
        else:
            logger.warning(f"Transaction to unknown address: {to_address}")
            return True, "Unknown address (strict mode disabled)", None

    def export_whitelist(self) -> Dict[str, dict]:
        """Export whitelist as JSON-serializable dict.

        Returns:
            Dict of address -> contract info dict
        """
        return {
            addr: {
                "name": info.name,
                "protocol": info.protocol,
                "type": info.contract_type.value,
                "risk_level": info.risk_level.value,
                "network": info.network,
                "notes": info.notes,
            }
            for addr, info in self._whitelist.items()
        }


# Global whitelist instance
_whitelist: Optional[ContractWhitelist] = None


def get_contract_whitelist(network: str = "base-mainnet") -> ContractWhitelist:
    """Get the global contract whitelist instance.

    Args:
        network: Network identifier

    Returns:
        ContractWhitelist instance
    """
    global _whitelist
    if _whitelist is None or _whitelist.network != network:
        _whitelist = ContractWhitelist(network)
    return _whitelist
