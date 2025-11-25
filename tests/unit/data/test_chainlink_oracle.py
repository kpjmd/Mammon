"""Unit tests for Chainlink price oracle implementation.

Tests the ChainlinkPriceOracle added in Phase 2A Sprint 2.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import time

from src.data.oracles import ChainlinkPriceOracle, MockPriceOracle, create_price_oracle
from src.utils.chainlink_feeds import get_feed_address, get_canonical_symbol


class TestChainlinkPriceOracle:
    """Test ChainlinkPriceOracle implementation."""

    @pytest.fixture
    def mock_w3(self):
        """Create a mock Web3 instance."""
        mock = Mock()
        mock.eth = Mock()
        mock.to_checksum_address = lambda addr: addr
        return mock

    @pytest.fixture
    def mock_contract(self):
        """Create a mock Chainlink contract."""
        mock = Mock()

        # Mock latestRoundData() response
        mock.functions.latestRoundData.return_value.call.return_value = (
            1,  # roundId
            300000000000,  # answer (price with 8 decimals: $3000.00)
            int(time.time()) - 60,  # startedAt (1 min ago)
            int(time.time()) - 60,  # updatedAt (1 min ago)
            1,  # answeredInRound
        )

        # Mock decimals() response
        mock.functions.decimals.return_value.call.return_value = 8

        return mock

    @pytest.fixture
    @patch("src.data.oracles.get_web3")
    def oracle(self, mock_get_web3):
        """Create a ChainlinkPriceOracle instance with mocked Web3."""
        mock_w3 = Mock()
        mock_w3.eth = Mock()
        mock_w3.to_checksum_address = lambda addr: addr
        mock_get_web3.return_value = mock_w3

        oracle = ChainlinkPriceOracle(
            network="arbitrum-sepolia",
            price_network="base-mainnet",
            cache_ttl_seconds=300,
            max_staleness_seconds=3600,
        )
        oracle._mock_w3 = mock_w3  # Store for test access
        return oracle

    def test_initialization(self, oracle):
        """Test oracle initializes with correct parameters."""
        assert oracle.execution_network == "arbitrum-sepolia"
        assert oracle.price_network == "base-mainnet"
        assert oracle.cache_ttl == 300
        assert oracle.max_staleness == 3600
        assert oracle.cache == {}

    def test_initialization_with_fallback(self):
        """Test oracle initializes with fallback oracle."""
        with patch("src.data.oracles.get_web3"):
            fallback = MockPriceOracle()
            oracle = ChainlinkPriceOracle(
                network="arbitrum-sepolia",
                fallback_oracle=fallback,
            )
            assert oracle.fallback_oracle == fallback

    def test_is_price_stale_no_cache(self, oracle):
        """Test staleness check with no cached data."""
        assert oracle.is_price_stale("ETH") is True

    def test_is_price_stale_fresh_cache(self, oracle):
        """Test staleness check with fresh cached data."""
        oracle.cache["ETH"] = (Decimal("3000"), time.time(), int(time.time()))
        assert oracle.is_price_stale("ETH", max_age_seconds=300) is False

    def test_is_price_stale_old_cache(self, oracle):
        """Test staleness check with stale cached data."""
        old_time = time.time() - 400  # 400 seconds ago
        oracle.cache["ETH"] = (Decimal("3000"), old_time, int(old_time))
        assert oracle.is_price_stale("ETH", max_age_seconds=300) is True

    def test_clear_cache_single_token(self, oracle):
        """Test clearing cache for a single token."""
        oracle.cache["ETH"] = (Decimal("3000"), time.time(), int(time.time()))
        oracle.cache["USDC"] = (Decimal("1"), time.time(), int(time.time()))

        oracle.clear_cache("ETH")

        assert "ETH" not in oracle.cache
        assert "USDC" in oracle.cache

    def test_clear_cache_all(self, oracle):
        """Test clearing all cache."""
        oracle.cache["ETH"] = (Decimal("3000"), time.time(), int(time.time()))
        oracle.cache["USDC"] = (Decimal("1"), time.time(), int(time.time()))

        oracle.clear_cache()

        assert len(oracle.cache) == 0

    def test_get_cache_stats_empty(self, oracle):
        """Test cache statistics with empty cache."""
        stats = oracle.get_cache_stats()
        assert stats["size"] == 0
        assert stats["tokens"] == []

    def test_get_cache_stats_with_data(self, oracle):
        """Test cache statistics with cached data."""
        now = time.time()
        oracle.cache["ETH"] = (Decimal("3000"), now, int(now))
        oracle.cache["USDC"] = (Decimal("1"), now - 200, int(now - 200))

        stats = oracle.get_cache_stats()
        assert stats["size"] == 2
        assert len(stats["tokens"]) == 2

        # Check token details
        token_symbols = [t["symbol"] for t in stats["tokens"]]
        assert "ETH" in token_symbols
        assert "USDC" in token_symbols

    @pytest.mark.asyncio
    async def test_get_price_cache_hit(self, oracle):
        """Test get_price returns cached value."""
        # Populate cache
        oracle.cache["ETH"] = (Decimal("3000"), time.time(), int(time.time()))

        price = await oracle.get_price("ETH")

        assert price == Decimal("3000")

    @pytest.mark.asyncio
    @patch("src.data.oracles.get_feed_address")
    async def test_get_price_no_feed_with_fallback(self, mock_get_feed, oracle):
        """Test get_price uses fallback when feed unavailable."""
        mock_get_feed.return_value = None
        oracle.fallback_oracle = MockPriceOracle()

        price = await oracle.get_price("UNKNOWN")

        assert price == Decimal("1.00")  # Mock oracle default

    @pytest.mark.asyncio
    @patch("src.data.oracles.get_feed_address")
    async def test_get_price_no_feed_no_fallback(self, mock_get_feed, oracle):
        """Test get_price raises error when feed unavailable and no fallback."""
        mock_get_feed.return_value = None
        oracle.fallback_oracle = None

        with pytest.raises(ValueError, match="No Chainlink price feed"):
            await oracle.get_price("UNKNOWN")

    @pytest.mark.asyncio
    @patch("src.data.oracles.get_feed_address")
    async def test_get_price_with_canonical_symbol_mapping(self, mock_get_feed, oracle):
        """Test get_price maps WETH to ETH feed."""
        # Set up feed address for ETH (WETH will map to this)
        mock_get_feed.return_value = "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70"

        # Mock contract response
        mock_contract = Mock()
        mock_contract.functions.latestRoundData.return_value.call.return_value = (
            1, 300000000000, int(time.time()), int(time.time()), 1
        )
        mock_contract.functions.decimals.return_value.call.return_value = 8

        oracle._mock_w3.eth.contract = Mock(return_value=mock_contract)

        # Query WETH price (should use ETH feed)
        price = await oracle.get_price("WETH")

        # Should get ETH price and cache under WETH key
        assert price == Decimal("3000.00")
        assert "WETH" in oracle.cache

    @pytest.mark.asyncio
    @patch("src.data.oracles.get_feed_address")
    async def test_get_price_stale_price_with_fallback(self, mock_get_feed, oracle):
        """Test get_price uses fallback for stale on-chain price."""
        mock_get_feed.return_value = "0x1234567890123456789012345678901234567890"
        oracle.fallback_oracle = MockPriceOracle()

        # Mock contract that returns very old price
        mock_contract = Mock()
        mock_contract.functions.latestRoundData.return_value.call.return_value = (
            1, 300000000000, 0, int(time.time()) - 7200, 1  # 2 hours old
        )
        mock_contract.functions.decimals.return_value.call.return_value = 8

        oracle._mock_w3.eth.contract = Mock(return_value=mock_contract)

        price = await oracle.get_price("ETH")

        # Should use fallback due to staleness
        assert price == Decimal("3000.00")  # Mock oracle price

    @pytest.mark.asyncio
    async def test_get_prices_batch(self, oracle):
        """Test get_prices handles multiple tokens."""
        # Populate cache
        now = time.time()
        oracle.cache["ETH"] = (Decimal("3000"), now, int(now))
        oracle.cache["USDC"] = (Decimal("1"), now, int(now))

        prices = await oracle.get_prices(["ETH", "USDC"])

        assert len(prices) == 2
        assert prices["ETH"] == Decimal("3000")
        assert prices["USDC"] == Decimal("1")

    @pytest.mark.asyncio
    async def test_get_prices_empty_list(self, oracle):
        """Test get_prices with empty token list."""
        prices = await oracle.get_prices([])
        assert prices == {}

    @pytest.mark.asyncio
    async def test_get_prices_partial_failure(self, oracle):
        """Test get_prices handles partial failures gracefully."""
        # Populate cache for one token
        oracle.cache["ETH"] = (Decimal("3000"), time.time(), int(time.time()))

        # Mock get_price to fail for USDC
        original_get_price = oracle.get_price

        async def mock_get_price(token, quote="USD"):
            if token == "USDC":
                raise ValueError("Feed not available")
            return await original_get_price(token, quote)

        oracle.get_price = mock_get_price

        prices = await oracle.get_prices(["ETH", "USDC"])

        # Should only include ETH
        assert "ETH" in prices
        assert "USDC" not in prices


class TestChainlinkFeedRegistry:
    """Test Chainlink feed registry functions."""

    def test_get_feed_address_base_mainnet(self):
        """Test getting ETH/USD feed address on Base mainnet."""
        address = get_feed_address("base-mainnet", "ETH", "USD")
        assert address == "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70"

    def test_get_feed_address_usdc(self):
        """Test getting USDC/USD feed address."""
        address = get_feed_address("base-mainnet", "USDC", "USD")
        assert address == "0x7e860098F58bBFC8648a4311b374B1D669a2bc6B"

    def test_get_feed_address_weth_maps_to_eth(self):
        """Test WETH maps to ETH feed."""
        eth_address = get_feed_address("base-mainnet", "ETH", "USD")
        weth_address = get_feed_address("base-mainnet", "WETH", "USD")
        assert eth_address == weth_address

    def test_get_feed_address_unknown_token(self):
        """Test unknown token returns None."""
        address = get_feed_address("base-mainnet", "UNKNOWN", "USD")
        assert address is None

    def test_get_feed_address_unknown_network(self):
        """Test unknown network returns None."""
        address = get_feed_address("unknown-network", "ETH", "USD")
        assert address is None

    def test_get_canonical_symbol_weth(self):
        """Test WETH canonical symbol."""
        assert get_canonical_symbol("WETH") == "ETH"
        assert get_canonical_symbol("weth") == "ETH"

    def test_get_canonical_symbol_regular(self):
        """Test regular token returns same symbol."""
        assert get_canonical_symbol("USDC") == "USDC"
        assert get_canonical_symbol("eth") == "ETH"


class TestCreatePriceOracleChainlink:
    """Test factory function for creating Chainlink oracle."""

    @patch("src.data.oracles.get_web3")
    def test_create_chainlink_with_price_network(self, mock_get_web3):
        """Test creating Chainlink oracle with separate price network."""
        mock_get_web3.return_value = Mock()

        oracle = create_price_oracle(
            "chainlink",
            network="arbitrum-sepolia",
            price_network="base-mainnet",
        )

        assert isinstance(oracle, ChainlinkPriceOracle)
        assert oracle.execution_network == "arbitrum-sepolia"
        assert oracle.price_network == "base-mainnet"

    @patch("src.data.oracles.get_web3")
    def test_create_chainlink_with_fallback_to_mock(self, mock_get_web3):
        """Test creating Chainlink oracle with mock fallback."""
        mock_get_web3.return_value = Mock()

        oracle = create_price_oracle(
            "chainlink",
            network="arbitrum-sepolia",
            fallback_to_mock=True,
        )

        assert isinstance(oracle, ChainlinkPriceOracle)
        assert isinstance(oracle.fallback_oracle, MockPriceOracle)

    @patch("src.data.oracles.get_web3")
    def test_create_chainlink_custom_cache_params(self, mock_get_web3):
        """Test creating Chainlink oracle with custom cache parameters."""
        mock_get_web3.return_value = Mock()

        oracle = create_price_oracle(
            "chainlink",
            network="base-mainnet",
            cache_ttl_seconds=600,
            max_staleness_seconds=1800,
        )

        assert oracle.cache_ttl == 600
        assert oracle.max_staleness == 1800

    def test_create_chainlink_missing_network(self):
        """Test creating Chainlink oracle without network raises error."""
        with pytest.raises(ValueError, match="ChainlinkPriceOracle requires 'network' parameter"):
            create_price_oracle("chainlink")
