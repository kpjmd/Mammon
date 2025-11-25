"""Price oracle interfaces for token price data.

This module provides abstract price oracle interfaces and implementations
for retrieving real-time token prices in various currencies.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime, timedelta
import asyncio
import time
from web3 import Web3
from web3.exceptions import ContractLogicError

from src.utils.logger import get_logger
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings
from src.utils.chainlink_feeds import (
    get_feed_address,
    get_canonical_symbol,
    is_feed_available,
    AGGREGATOR_V3_ABI,
)

logger = get_logger(__name__)


class StalePriceError(Exception):
    """Raised when a price feed is too stale and strict mode is enabled."""
    pass


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
    Supports multi-network architecture where price data comes from one
    network (e.g., Base Mainnet) but is used in another context
    (e.g., Arbitrum Sepolia transactions).

    Features:
    - Cross-network price queries (read from reliable mainnet feeds)
    - Intelligent caching with configurable TTL
    - Automatic fallback for missing feeds
    - Staleness detection
    - Retry logic with exponential backoff
    """

    def __init__(
        self,
        network: str,
        rpc_url: Optional[str] = None,
        price_network: Optional[str] = None,
        cache_ttl_seconds: int = 300,
        max_staleness_seconds: int = 3600,
        fallback_oracle: Optional[PriceOracle] = None,
        strict_staleness: bool = False,
    ) -> None:
        """Initialize Chainlink price oracle.

        Args:
            network: Execution network identifier (e.g., "arbitrum-sepolia")
            rpc_url: Optional custom RPC URL for price network
            price_network: Network to query for prices (default: same as network)
                          Use "base-mainnet" for reliable price data
            cache_ttl_seconds: Cache time-to-live in seconds (default: 300)
            max_staleness_seconds: Maximum acceptable price age (default: 3600)
            fallback_oracle: Optional fallback oracle if Chainlink unavailable
            strict_staleness: If True, raise StalePriceError instead of warning
                             when price is stale (recommended for production swaps)
        """
        self.execution_network = network
        self.price_network = price_network or network
        self.custom_rpc_url = rpc_url
        self.cache_ttl = cache_ttl_seconds
        self.max_staleness = max_staleness_seconds
        self.fallback_oracle = fallback_oracle
        self.strict_staleness = strict_staleness

        # Price cache: {token_symbol: (price, fetch_timestamp, on_chain_timestamp)}
        self.cache: Dict[str, tuple[Decimal, float, int]] = {}

        # Cache for tokens without Chainlink feeds (to avoid repeated failed lookups)
        # Set of token symbols that have no feed
        self.missing_feeds_cache: set = set()

        # Initialize Web3 connection to price network with premium RPC support
        settings = get_settings()
        self.w3 = get_web3(self.price_network, self.custom_rpc_url, config=settings)

        logger.info(
            f"Initialized ChainlinkPriceOracle: "
            f"execution_network={network}, price_network={self.price_network}, "
            f"cache_ttl={cache_ttl_seconds}s, max_staleness={max_staleness_seconds}s, "
            f"strict_staleness={strict_staleness}"
        )

    async def get_price(self, token: str, quote: str = "USD") -> Decimal:
        """Get current price for a token from Chainlink.

        Implements caching, staleness checks, and fallback logic.

        Args:
            token: Token symbol (e.g., "ETH", "WETH", "USDC")
            quote: Quote currency (default: "USD")

        Returns:
            Current price as Decimal

        Raises:
            ValueError: If token/quote pair not supported and no fallback
            ConnectionError: If unable to fetch price and no cached/fallback data
        """
        token_upper = token.upper()
        quote_upper = quote.upper()

        # Check cache first
        if not self.is_price_stale(token_upper, self.cache_ttl):
            price, _, _ = self.cache[token_upper]
            logger.debug(f"Cache hit for {token_upper}/{quote_upper}: ${price}")
            return price

        # Get canonical token symbol (e.g., WETH -> ETH)
        canonical_symbol = get_canonical_symbol(token_upper)

        # Check missing feeds cache to avoid repeated failed lookups
        if canonical_symbol in self.missing_feeds_cache:
            # Skip the warning log since we already know it's missing
            if self.fallback_oracle:
                return await self.fallback_oracle.get_price(token, quote)
            raise ValueError(
                f"No Chainlink price feed for {token}/{quote} on {self.price_network} "
                f"(cached as missing)"
            )

        # Check if feed exists
        feed_address = get_feed_address(self.price_network, canonical_symbol, quote_upper)

        if not feed_address:
            # Log warning only once when feed is first discovered to be missing
            logger.warning(
                f"No Chainlink feed for {canonical_symbol}/{quote_upper} "
                f"on {self.price_network}"
            )

            # Add to missing feeds cache to avoid future lookups
            self.missing_feeds_cache.add(canonical_symbol)

            # Try fallback oracle
            if self.fallback_oracle:
                logger.info(f"Using fallback oracle for {token_upper}")
                return await self.fallback_oracle.get_price(token, quote)

            raise ValueError(
                f"No Chainlink price feed for {token}/{quote} on {self.price_network} "
                f"and no fallback oracle configured"
            )

        # Query Chainlink feed with retry logic
        try:
            price, on_chain_timestamp = await self._query_feed_with_retry(
                feed_address, canonical_symbol, quote_upper
            )

            # Check on-chain staleness
            age_seconds = int(time.time()) - on_chain_timestamp
            if age_seconds > self.max_staleness:
                logger.warning(
                    f"Chainlink price for {canonical_symbol} is stale: "
                    f"{age_seconds}s old (max: {self.max_staleness}s)"
                )

                # Try fallback if price too stale
                if self.fallback_oracle:
                    logger.info(f"Using fallback oracle due to stale price")
                    return await self.fallback_oracle.get_price(token, quote)

                # In strict mode, raise exception instead of using stale price
                if self.strict_staleness:
                    raise StalePriceError(
                        f"Price for {canonical_symbol} is stale ({age_seconds}s old, "
                        f"max: {self.max_staleness}s) and strict_staleness=True"
                    )

                # Use stale price with warning (permissive mode)
                logger.warning(f"Using stale Chainlink price for {canonical_symbol}")

            # Update cache
            self.cache[token_upper] = (price, time.time(), on_chain_timestamp)

            logger.info(
                f"Fetched {token_upper}/{quote_upper} from Chainlink: ${price} "
                f"(age: {age_seconds}s)"
            )
            return price

        except Exception as e:
            logger.error(f"Failed to query Chainlink for {canonical_symbol}: {e}")

            # Try fallback oracle
            if self.fallback_oracle:
                logger.info(f"Using fallback oracle due to error: {e}")
                return await self.fallback_oracle.get_price(token, quote)

            # Check if we have stale cached data we can use
            if token_upper in self.cache:
                price, fetch_time, _ = self.cache[token_upper]
                cache_age = time.time() - fetch_time
                logger.warning(
                    f"Using stale cached price for {token_upper} "
                    f"({cache_age:.0f}s old)"
                )
                return price

            raise ConnectionError(
                f"Failed to fetch price for {token}/{quote} from Chainlink: {e}"
            )

    async def get_prices(
        self,
        tokens: List[str],
        quote: str = "USD"
    ) -> Dict[str, Decimal]:
        """Get current prices for multiple tokens from Chainlink.

        Uses concurrent queries for performance.

        Args:
            tokens: List of token symbols
            quote: Quote currency (default: "USD")

        Returns:
            Dict mapping token symbols to prices

        Note:
            If any individual token query fails, it will be omitted from results
            or use fallback oracle if configured. This ensures partial success
            rather than total failure.
        """
        if not tokens:
            return {}

        # Query all tokens concurrently
        tasks = [self.get_price(token, quote) for token in tokens]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build results dict, handling exceptions
        prices = {}
        for token, result in zip(tokens, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to get price for {token}: {result}")
                # Skip this token rather than failing entire batch
                continue
            prices[token] = result

        return prices

    def is_price_stale(self, token: str, max_age_seconds: int = 300) -> bool:
        """Check if cached price data is stale.

        Args:
            token: Token symbol
            max_age_seconds: Maximum acceptable age in seconds (default: 5 min)

        Returns:
            True if no cached data or data older than max_age_seconds
        """
        token_upper = token.upper()

        if token_upper not in self.cache:
            return True

        _, fetch_timestamp, _ = self.cache[token_upper]
        age = time.time() - fetch_timestamp
        return age > max_age_seconds

    async def _query_feed_with_retry(
        self,
        feed_address: str,
        token_symbol: str,
        quote: str,
        max_retries: int = 3,
    ) -> tuple[Decimal, int]:
        """Query Chainlink price feed with retry logic.

        Args:
            feed_address: Chainlink feed contract address
            token_symbol: Token symbol for logging
            quote: Quote currency for logging
            max_retries: Maximum number of retry attempts

        Returns:
            Tuple of (price, updated_at_timestamp)

        Raises:
            ConnectionError: If all retry attempts fail
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                # Create contract instance
                feed_contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(feed_address),
                    abi=AGGREGATOR_V3_ABI,
                )

                # Query latest round data
                round_data = feed_contract.functions.latestRoundData().call()
                round_id, answer, started_at, updated_at, answered_in_round = round_data

                # Validate round data
                if answer <= 0:
                    raise ValueError(f"Invalid price from Chainlink: {answer}")

                if updated_at == 0:
                    raise ValueError("Invalid timestamp from Chainlink")

                # Get feed decimals
                decimals = feed_contract.functions.decimals().call()

                # Convert to Decimal (Chainlink typically uses 8 decimals)
                price = Decimal(answer) / Decimal(10 ** decimals)

                logger.debug(
                    f"Chainlink {token_symbol}/{quote}: price={price}, "
                    f"decimals={decimals}, roundId={round_id}, "
                    f"updatedAt={updated_at}"
                )

                return price, updated_at

            except (ContractLogicError, ValueError, ConnectionError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for {token_symbol}/{quote}: "
                        f"{e}. Waiting {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"All {max_retries} retry attempts failed for "
                        f"{token_symbol}/{quote}"
                    )

        raise ConnectionError(
            f"Failed to query Chainlink feed after {max_retries} attempts: "
            f"{last_error}"
        )

    def clear_cache(self, token: Optional[str] = None) -> None:
        """Clear price cache.

        Args:
            token: Optional specific token to clear, or None to clear all
        """
        if token:
            token_upper = token.upper()
            if token_upper in self.cache:
                del self.cache[token_upper]
                logger.debug(f"Cleared cache for {token_upper}")
        else:
            self.cache.clear()
            logger.debug("Cleared all price cache")

    def get_cache_stats(self) -> Dict:
        """Get cache statistics for monitoring.

        Returns:
            Dict with cache statistics
        """
        if not self.cache:
            return {"size": 0, "tokens": []}

        now = time.time()
        stats = {
            "size": len(self.cache),
            "tokens": [],
        }

        for token, (price, fetch_time, on_chain_time) in self.cache.items():
            cache_age = now - fetch_time
            on_chain_age = int(now) - on_chain_time
            stats["tokens"].append({
                "symbol": token,
                "price": str(price),
                "cache_age_seconds": int(cache_age),
                "on_chain_age_seconds": on_chain_age,
                "is_stale": cache_age > self.cache_ttl,
            })

        return stats


def create_price_oracle(oracle_type: str = "mock", **kwargs) -> PriceOracle:
    """Factory function to create a price oracle instance.

    Args:
        oracle_type: Type of oracle ("mock" or "chainlink")
        **kwargs: Additional arguments for oracle initialization
            For "chainlink":
                - network: Execution network (required)
                - rpc_url: Custom RPC URL (optional)
                - price_network: Network for price queries (optional, defaults to network)
                - cache_ttl_seconds: Cache TTL (optional, default: 300)
                - max_staleness_seconds: Max price age (optional, default: 3600)
                - fallback_to_mock: Use mock fallback (optional, default: False)
                - strict_staleness: Raise exception on stale prices (optional, default: False)

    Returns:
        PriceOracle instance

    Raises:
        ValueError: If oracle_type is not supported or required args missing

    Examples:
        >>> # Mock oracle for testing
        >>> oracle = create_price_oracle("mock")
        >>> price = await oracle.get_price("ETH")

        >>> # Chainlink oracle with Base mainnet prices for Arbitrum execution
        >>> oracle = create_price_oracle(
        ...     "chainlink",
        ...     network="arbitrum-sepolia",
        ...     price_network="base-mainnet",
        ...     fallback_to_mock=True
        ... )
    """
    if oracle_type == "mock":
        return MockPriceOracle()

    elif oracle_type == "chainlink":
        network = kwargs.get("network")
        if not network:
            raise ValueError("ChainlinkPriceOracle requires 'network' parameter")

        # Optional parameters
        rpc_url = kwargs.get("rpc_url")
        price_network = kwargs.get("price_network")
        cache_ttl = kwargs.get("cache_ttl_seconds", 300)
        max_staleness = kwargs.get("max_staleness_seconds", 3600)
        strict_staleness = kwargs.get("strict_staleness", False)

        # Fallback oracle configuration
        fallback_oracle = None
        if kwargs.get("fallback_to_mock", False):
            fallback_oracle = MockPriceOracle()
            logger.info("Configured Chainlink oracle with mock fallback")

        return ChainlinkPriceOracle(
            network=network,
            rpc_url=rpc_url,
            price_network=price_network,
            cache_ttl_seconds=cache_ttl,
            max_staleness_seconds=max_staleness,
            fallback_oracle=fallback_oracle,
            strict_staleness=strict_staleness,
        )

    else:
        raise ValueError(
            f"Unsupported oracle type: {oracle_type}. "
            f"Supported types: 'mock', 'chainlink'"
        )
