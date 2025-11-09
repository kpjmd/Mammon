"""Price oracle interfaces for token price data.

This module provides abstract price oracle interfaces and implementations
for retrieving real-time token prices in various currencies.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime, timedelta


class PriceOracle(ABC):
    """Abstract base class for price data providers.

    Price oracles provide real-time and historical price data for tokens,
    enabling accurate USD conversions for spending limits and reporting.
    """

    @abstractmethod
    async def get_price(self, token: str, quote: str = "USD") -> Decimal:
        """Get current price for a token.

        Args:
            token: Token symbol (e.g., "ETH", "USDC")
            quote: Quote currency (default: "USD")

        Returns:
            Current price as Decimal

        Raises:
            ValueError: If token/quote pair is not supported
            ConnectionError: If unable to fetch price data
        """
        pass

    @abstractmethod
    async def get_prices(
        self,
        tokens: List[str],
        quote: str = "USD"
    ) -> Dict[str, Decimal]:
        """Get current prices for multiple tokens.

        Args:
            tokens: List of token symbols
            quote: Quote currency (default: "USD")

        Returns:
            Dict mapping token symbols to prices

        Raises:
            ValueError: If any token/quote pair is not supported
            ConnectionError: If unable to fetch price data
        """
        pass

    @abstractmethod
    def is_price_stale(self, token: str, max_age_seconds: int = 300) -> bool:
        """Check if cached price data is stale.

        Args:
            token: Token symbol
            max_age_seconds: Maximum acceptable age in seconds (default: 5 min)

        Returns:
            True if price data is older than max_age_seconds
        """
        pass


class MockPriceOracle(PriceOracle):
    """Mock price oracle for testing and development.

    Provides hardcoded prices for common tokens. This preserves the
    Phase 1 behavior of using $3000/ETH for calculations.

    DO NOT use in production - this is for testing only!
    """

    def __init__(self) -> None:
        """Initialize mock price oracle with hardcoded prices."""
        self.prices: Dict[str, Decimal] = {
            "ETH": Decimal("3000.00"),
            "WETH": Decimal("3000.00"),  # Wrapped ETH same as ETH
            "USDC": Decimal("1.00"),
            "USDT": Decimal("1.00"),
            "DAI": Decimal("1.00"),
            "AERO": Decimal("0.50"),  # Mock Aerodrome token price
        }
        self.last_update: Dict[str, datetime] = {}

    async def get_price(self, token: str, quote: str = "USD") -> Decimal:
        """Get mock price for a token.

        Args:
            token: Token symbol (e.g., "ETH", "USDC")
            quote: Quote currency (only "USD" supported in mock)

        Returns:
            Mock price as Decimal

        Raises:
            ValueError: If token is not in mock price list
        """
        if quote != "USD":
            raise ValueError(f"Mock oracle only supports USD quotes, got: {quote}")

        token_upper = token.upper()
        if token_upper not in self.prices:
            # Default to $1 for unknown tokens (stablecoins assumption)
            return Decimal("1.00")

        # Update last_update timestamp
        self.last_update[token_upper] = datetime.now()

        return self.prices[token_upper]

    async def get_prices(
        self,
        tokens: List[str],
        quote: str = "USD"
    ) -> Dict[str, Decimal]:
        """Get mock prices for multiple tokens.

        Args:
            tokens: List of token symbols
            quote: Quote currency (only "USD" supported in mock)

        Returns:
            Dict mapping token symbols to mock prices
        """
        prices = {}
        for token in tokens:
            prices[token] = await self.get_price(token, quote)
        return prices

    def is_price_stale(self, token: str, max_age_seconds: int = 300) -> bool:
        """Check if mock price is stale.

        Mock oracle always returns False (prices never stale) for simplicity.

        Args:
            token: Token symbol
            max_age_seconds: Maximum acceptable age (ignored in mock)

        Returns:
            Always False for mock oracle
        """
        return False

    def set_price(self, token: str, price: Decimal) -> None:
        """Set a mock price for testing.

        This is useful for testing scenarios with different price points.

        Args:
            token: Token symbol
            price: Price to set
        """
        self.prices[token.upper()] = price
        self.last_update[token.upper()] = datetime.now()


class ChainlinkPriceOracle(PriceOracle):
    """Chainlink price oracle for production use.

    Fetches real-time prices from Chainlink price feeds on-chain.

    IMPORTANT: This is a stub for Phase 2A implementation.
    DO NOT use until fully implemented and tested!
    """

    def __init__(self, network: str, rpc_url: str) -> None:
        """Initialize Chainlink price oracle.

        Args:
            network: Network identifier (e.g., "base-mainnet")
            rpc_url: RPC URL for blockchain queries
        """
        self.network = network
        self.rpc_url = rpc_url
        self.price_feeds: Dict[str, str] = {}  # Token -> feed address mapping
        self.cache: Dict[str, tuple[Decimal, datetime]] = {}  # Price cache

    async def get_price(self, token: str, quote: str = "USD") -> Decimal:
        """Get price from Chainlink feed.

        Args:
            token: Token symbol
            quote: Quote currency (default: "USD")

        Returns:
            Current price from Chainlink

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "ChainlinkPriceOracle not yet implemented. "
            "This is planned for Phase 2A. "
            "Use MockPriceOracle for Phase 1C testing."
        )

    async def get_prices(
        self,
        tokens: List[str],
        quote: str = "USD"
    ) -> Dict[str, Decimal]:
        """Get prices for multiple tokens from Chainlink.

        Args:
            tokens: List of token symbols
            quote: Quote currency

        Returns:
            Dict of prices

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "ChainlinkPriceOracle not yet implemented. "
            "Use MockPriceOracle for Phase 1C testing."
        )

    def is_price_stale(self, token: str, max_age_seconds: int = 300) -> bool:
        """Check if Chainlink price is stale.

        Args:
            token: Token symbol
            max_age_seconds: Maximum acceptable age

        Returns:
            True if price is stale

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "ChainlinkPriceOracle not yet implemented. "
            "Use MockPriceOracle for Phase 1C testing."
        )


def create_price_oracle(oracle_type: str = "mock", **kwargs) -> PriceOracle:
    """Factory function to create a price oracle instance.

    Args:
        oracle_type: Type of oracle ("mock" or "chainlink")
        **kwargs: Additional arguments for oracle initialization

    Returns:
        PriceOracle instance

    Raises:
        ValueError: If oracle_type is not supported

    Examples:
        >>> oracle = create_price_oracle("mock")
        >>> price = await oracle.get_price("ETH")
        >>> print(f"ETH price: ${price}")
    """
    if oracle_type == "mock":
        return MockPriceOracle()
    elif oracle_type == "chainlink":
        network = kwargs.get("network")
        rpc_url = kwargs.get("rpc_url")
        if not network or not rpc_url:
            raise ValueError("ChainlinkPriceOracle requires 'network' and 'rpc_url'")
        return ChainlinkPriceOracle(network, rpc_url)
    else:
        raise ValueError(
            f"Unsupported oracle type: {oracle_type}. "
            f"Supported types: 'mock', 'chainlink'"
        )
