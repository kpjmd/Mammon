"""Cold wallet stub for Tier 3 Ledger hardware wallet.

This is a stub implementation for future Ledger integration.
Cold wallets are for manual operations only - no autonomous transactions.

Security Note:
Cold wallets should hold >90% of funds.
They require physical device interaction for all transactions.
"""

from decimal import Decimal
from typing import Dict, Any, Optional
from web3 import Web3
from web3.types import TxParams, HexBytes

from src.wallet.base_provider import WalletProvider
from src.wallet.tiered_config import WalletTier, TierConfig, DEFAULT_COLD_CONFIG
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ColdWalletNotImplementedError(NotImplementedError):
    """Raised when cold wallet operations are attempted.

    Cold wallet requires Ledger integration which is not yet implemented.
    """
    pass


class ColdWalletStub(WalletProvider):
    """Tier 3 Cold Wallet stub for Ledger hardware wallet.

    This wallet only supports read operations. All write operations
    raise NotImplementedError until Ledger integration is complete.

    The cold wallet is designed for:
    - Holding majority of funds (>90%)
    - Manual operations only
    - Highest security level
    - Physical device confirmation required

    Future implementation will use:
    - ledgerblue library for device communication
    - USB/Bluetooth connection to Ledger device
    - Manual transaction signing on device screen

    Attributes:
        address: Cold wallet address (public only)
        tier_config: Cold wallet tier configuration
        web3: Web3 instance for balance queries
    """

    def __init__(
        self,
        address: str,
        web3: Web3,
        config: Optional[Dict[str, Any]] = None,
        tier_config: Optional[TierConfig] = None,
    ):
        """Initialize cold wallet stub.

        Args:
            address: Cold wallet public address
            web3: Web3 instance for balance queries
            config: Configuration dict (optional)
            tier_config: Tier configuration (optional)
        """
        self.address = Web3.to_checksum_address(address)
        self.web3 = web3
        self.config = config or {}
        self.tier = WalletTier.COLD
        self.tier_config = tier_config or DEFAULT_COLD_CONFIG

        logger.info(
            f"ColdWalletStub initialized (read-only)",
            extra={
                "address": self.address,
                "tier": self.tier.value,
            }
        )

    def get_address(self) -> str:
        """Get the cold wallet address.

        Returns:
            Checksummed Ethereum address
        """
        return self.address

    def get_balance(self, token: str = "eth") -> Decimal:
        """Get token balance from the cold wallet.

        This is a read-only operation that doesn't require Ledger.

        Args:
            token: Token symbol (default: "eth")

        Returns:
            Balance as Decimal
        """
        if token.lower() != "eth":
            raise NotImplementedError(
                f"ERC-20 balance queries not yet implemented for cold wallet. "
                f"Only ETH is supported currently."
            )

        try:
            balance_wei = self.web3.eth.get_balance(self.address)
            balance_eth = Decimal(balance_wei) / Decimal(10**18)
            logger.debug(f"Cold wallet balance: {balance_eth} ETH")
            return balance_eth
        except Exception as e:
            logger.error(f"Failed to get cold wallet balance: {e}")
            return Decimal("0")

    def get_nonce(self) -> int:
        """Get the next available nonce.

        Returns:
            Next nonce for transaction
        """
        return self.web3.eth.get_transaction_count(self.address)

    def reset_nonce(self) -> None:
        """Reset nonce tracking.

        Cold wallet doesn't track nonces locally.
        """
        pass

    def sign_transaction(self, transaction: TxParams) -> bytes:
        """Sign a transaction with Ledger device.

        NOT IMPLEMENTED - Requires Ledger integration.

        Args:
            transaction: Transaction parameters

        Raises:
            ColdWalletNotImplementedError: Always
        """
        raise ColdWalletNotImplementedError(
            "Cold wallet transaction signing requires Ledger hardware wallet. "
            "This feature is not yet implemented.\n\n"
            "To sign transactions with your cold wallet:\n"
            "1. Use the Ledger device directly with MetaMask or Frame\n"
            "2. Export the unsigned transaction for manual signing\n"
            "3. Wait for Ledger integration in a future MAMMON release"
        )

    def send_transaction(self, transaction: TxParams) -> HexBytes:
        """Send a transaction signed by Ledger device.

        NOT IMPLEMENTED - Requires Ledger integration.

        Args:
            transaction: Transaction parameters

        Raises:
            ColdWalletNotImplementedError: Always
        """
        raise ColdWalletNotImplementedError(
            "Cold wallet transaction execution requires Ledger hardware wallet. "
            "This feature is not yet implemented.\n\n"
            "Cold wallet operations are manual-only. "
            "Use your Ledger device with a web interface to execute transactions."
        )

    def is_read_only(self) -> bool:
        """Check if this wallet is read-only.

        Returns:
            True (cold wallet is always read-only until Ledger integration)
        """
        return True

    def get_status(self) -> Dict[str, Any]:
        """Get cold wallet status.

        Returns:
            Status dict with balance and config
        """
        try:
            balance_eth = self.get_balance("eth")
        except Exception:
            balance_eth = Decimal("0")

        return {
            "tier": self.tier.value,
            "address": self.address,
            "balance_eth": str(balance_eth),
            "is_read_only": True,
            "ledger_connected": False,
            "status": "stub",
            "message": "Ledger integration pending",
        }

    def prepare_unsigned_transaction(
        self,
        transaction: TxParams
    ) -> Dict[str, Any]:
        """Prepare an unsigned transaction for manual Ledger signing.

        This allows users to manually sign with Ledger until
        full integration is implemented.

        Args:
            transaction: Transaction parameters

        Returns:
            Dict with transaction details for manual signing
        """
        # Add nonce and chain ID if not present
        if "nonce" not in transaction:
            transaction["nonce"] = self.get_nonce()
        if "chainId" not in transaction:
            transaction["chainId"] = self.web3.eth.chain_id

        return {
            "to": transaction.get("to"),
            "value": str(transaction.get("value", 0)),
            "data": transaction.get("data", "0x").hex() if isinstance(transaction.get("data"), bytes) else transaction.get("data", "0x"),
            "nonce": transaction["nonce"],
            "chainId": transaction["chainId"],
            "gas": transaction.get("gas"),
            "maxFeePerGas": transaction.get("maxFeePerGas"),
            "maxPriorityFeePerGas": transaction.get("maxPriorityFeePerGas"),
            "instructions": [
                "1. Copy these transaction details",
                "2. Open your Ledger device with MetaMask or Frame",
                "3. Manually create and sign this transaction",
                "4. Verify all details on your Ledger screen before confirming",
            ]
        }


def create_cold_wallet_stub(
    address: str,
    web3: Web3,
    config: Optional[Dict[str, Any]] = None,
) -> ColdWalletStub:
    """Factory function to create a cold wallet stub.

    Args:
        address: Cold wallet public address
        web3: Web3 instance
        config: Optional configuration

    Returns:
        ColdWalletStub instance
    """
    return ColdWalletStub(address, web3, config)
