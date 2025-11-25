"""Abstract base class for wallet providers.

Defines the interface that all wallet providers (CDP, Local, etc.) must implement.
This ensures WalletManager can work with any provider type without modification.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Optional
from web3.types import TxParams, Wei, HexBytes


class WalletProvider(ABC):
    """Abstract base class for wallet providers.

    All wallet providers must implement these methods to be compatible
    with WalletManager and the broader MAMMON system.
    """

    @abstractmethod
    def get_address(self) -> str:
        """Get the wallet address.

        Returns:
            Ethereum address as checksummed string (0x...)
        """
        pass

    @abstractmethod
    def get_balance(self, token: str = "eth") -> Decimal:
        """Get balance for a specific token.

        Args:
            token: Token symbol (default: "eth")

        Returns:
            Balance as Decimal
        """
        pass

    @abstractmethod
    def send_transaction(self, transaction: TxParams) -> HexBytes:
        """Sign and send a transaction.

        Args:
            transaction: Transaction parameters (to, value, data, gas, etc.)

        Returns:
            Transaction hash as HexBytes

        Raises:
            ValueError: If transaction validation fails
            ConnectionError: If unable to send transaction
        """
        pass

    @abstractmethod
    def sign_transaction(self, transaction: TxParams) -> bytes:
        """Sign a transaction without sending it.

        Args:
            transaction: Transaction parameters

        Returns:
            Signed transaction as raw bytes
        """
        pass

    @abstractmethod
    def get_nonce(self) -> int:
        """Get the next available nonce for this wallet.

        Returns:
            Next nonce value
        """
        pass

    @abstractmethod
    def reset_nonce(self) -> None:
        """Reset nonce tracking to sync with chain state.

        Call this if a transaction fails to prevent nonce gaps.
        """
        pass
