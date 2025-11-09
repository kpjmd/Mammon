"""ERC20 token utilities for querying token data and balances.

Provides a clean interface for interacting with ERC20 tokens on any network.
"""

from typing import Optional
from decimal import Decimal
from web3 import Web3
from src.utils.web3_provider import get_web3
from src.utils.contracts import ERC20_ABI, ContractHelper
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ERC20Token:
    """Utility class for interacting with ERC20 tokens.

    Provides methods to query token metadata, balances, and allowances
    on any supported network.

    Attributes:
        network_id: Network identifier (e.g., "base-mainnet", "arbitrum-sepolia")
        token_address: Token contract address
        w3: Web3 instance for this network
        contract: Web3 contract instance
        symbol: Token symbol (cached after first query)
        decimals: Token decimals (cached after first query)
        name: Token name (cached after first query)
    """

    def __init__(self, network_id: str, token_address: str):
        """Initialize ERC20 token utility.

        Args:
            network_id: Network identifier
            token_address: Token contract address
        """
        self.network_id = network_id
        self.token_address = token_address

        # Get Web3 instance
        self.w3 = get_web3(network_id)

        # Get contract instance
        self.contract = ContractHelper.get_erc20_contract(self.w3, token_address)

        # Cache metadata (loaded on first access)
        self._symbol: Optional[str] = None
        self._decimals: Optional[int] = None
        self._name: Optional[str] = None

        logger.debug(f"Initialized ERC20Token for {token_address} on {network_id}")

    def get_symbol(self) -> str:
        """Get token symbol (e.g., "USDC", "WETH").

        Result is cached after first call.

        Returns:
            Token symbol
        """
        if self._symbol is None:
            try:
                self._symbol = self.contract.functions.symbol().call()
                logger.debug(f"Token symbol: {self._symbol}")
            except Exception as e:
                logger.warning(f"Failed to get symbol for {self.token_address}: {e}")
                self._symbol = "UNKNOWN"

        return self._symbol

    def get_decimals(self) -> int:
        """Get token decimals (e.g., 6 for USDC, 18 for WETH).

        Result is cached after first call.

        Returns:
            Number of decimals
        """
        if self._decimals is None:
            try:
                self._decimals = self.contract.functions.decimals().call()
                logger.debug(f"Token decimals: {self._decimals}")
            except Exception as e:
                logger.warning(f"Failed to get decimals for {self.token_address}: {e}")
                self._decimals = 18  # Default to 18

        return self._decimals

    def get_name(self) -> str:
        """Get full token name (e.g., "USD Coin", "Wrapped Ether").

        Result is cached after first call.

        Returns:
            Token name
        """
        if self._name is None:
            try:
                self._name = self.contract.functions.name().call()
                logger.debug(f"Token name: {self._name}")
            except Exception as e:
                logger.warning(f"Failed to get name for {self.token_address}: {e}")
                self._name = "Unknown Token"

        return self._name

    def get_total_supply(self) -> int:
        """Get total token supply (in wei/smallest unit).

        Returns:
            Total supply in smallest unit
        """
        try:
            total_supply = self.contract.functions.totalSupply().call()
            logger.debug(f"Total supply: {total_supply}")
            return total_supply
        except Exception as e:
            logger.error(f"Failed to get total supply for {self.token_address}: {e}")
            raise

    def get_balance(self, address: str) -> int:
        """Get token balance for an address (in wei/smallest unit).

        Args:
            address: Wallet address to query

        Returns:
            Balance in smallest unit (e.g., wei for 18 decimal tokens)
        """
        try:
            # Checksum the address
            checksummed = self.w3.to_checksum_address(address)
            balance = self.contract.functions.balanceOf(checksummed).call()
            logger.debug(f"Balance for {address}: {balance} (raw)")
            return balance
        except Exception as e:
            logger.error(f"Failed to get balance for {address}: {e}")
            raise

    def get_allowance(self, owner: str, spender: str) -> int:
        """Get token allowance (how much spender can spend on behalf of owner).

        Args:
            owner: Token owner address
            spender: Spender address (e.g., router contract)

        Returns:
            Allowance in smallest unit
        """
        try:
            owner_checksummed = self.w3.to_checksum_address(owner)
            spender_checksummed = self.w3.to_checksum_address(spender)

            allowance = self.contract.functions.allowance(
                owner_checksummed,
                spender_checksummed
            ).call()

            logger.debug(f"Allowance for {owner} -> {spender}: {allowance}")
            return allowance
        except Exception as e:
            logger.error(f"Failed to get allowance: {e}")
            raise

    def format_amount(self, raw_amount: int) -> Decimal:
        """Convert raw token amount to human-readable decimal.

        Automatically uses the token's decimals.

        Args:
            raw_amount: Amount in smallest unit (e.g., wei)

        Returns:
            Human-readable amount as Decimal

        Example:
            >>> token = ERC20Token("base-mainnet", usdc_address)
            >>> token.format_amount(1000000)  # USDC has 6 decimals
            Decimal('1.000000')
        """
        decimals = self.get_decimals()
        formatted = Decimal(raw_amount) / Decimal(10 ** decimals)
        return formatted

    def to_raw_amount(self, formatted_amount: Decimal) -> int:
        """Convert human-readable amount to raw token amount.

        Automatically uses the token's decimals.

        Args:
            formatted_amount: Human-readable amount

        Returns:
            Amount in smallest unit (e.g., wei)

        Example:
            >>> token = ERC20Token("base-mainnet", usdc_address)
            >>> token.to_raw_amount(Decimal("1.5"))  # USDC has 6 decimals
            1500000
        """
        decimals = self.get_decimals()
        raw = int(formatted_amount * Decimal(10 ** decimals))
        return raw

    def get_balance_formatted(self, address: str) -> Decimal:
        """Get token balance as human-readable Decimal.

        Convenience method that combines get_balance() and format_amount().

        Args:
            address: Wallet address to query

        Returns:
            Balance as human-readable Decimal
        """
        raw_balance = self.get_balance(address)
        return self.format_amount(raw_balance)

    def __repr__(self) -> str:
        """String representation of ERC20Token."""
        symbol = self.get_symbol() if self._symbol else "?"
        return f"ERC20Token({symbol} on {self.network_id})"

    def get_info(self) -> dict:
        """Get all token metadata as a dictionary.

        Returns:
            Dict with name, symbol, decimals, address, network
        """
        return {
            "name": self.get_name(),
            "symbol": self.get_symbol(),
            "decimals": self.get_decimals(),
            "address": self.token_address,
            "network": self.network_id,
        }


# Convenience functions for common operations

def get_token_balance(
    network_id: str,
    token_address: str,
    wallet_address: str,
    formatted: bool = True
) -> Decimal | int:
    """Get token balance for a wallet address.

    Convenience function that creates a token instance and queries balance.

    Args:
        network_id: Network identifier
        token_address: Token contract address
        wallet_address: Wallet address to query
        formatted: If True, return human-readable Decimal; if False, return raw int

    Returns:
        Balance (formatted Decimal or raw int depending on formatted parameter)
    """
    token = ERC20Token(network_id, token_address)

    if formatted:
        return token.get_balance_formatted(wallet_address)
    else:
        return token.get_balance(wallet_address)


def get_token_info(network_id: str, token_address: str) -> dict:
    """Get token metadata (name, symbol, decimals).

    Convenience function that creates a token instance and gets metadata.

    Args:
        network_id: Network identifier
        token_address: Token contract address

    Returns:
        Dict with token metadata
    """
    token = ERC20Token(network_id, token_address)
    return token.get_info()
