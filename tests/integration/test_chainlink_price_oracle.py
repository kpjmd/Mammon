"""Integration tests for ChainlinkPriceOracle on real networks.

These tests verify price oracle functionality against real Chainlink feeds
on Base Mainnet. Tests are marked as integration tests and require network access.
"""

import asyncio
import os
import time
from decimal import Decimal

import pytest

from src.data.oracles import ChainlinkPriceOracle, MockPriceOracle, create_price_oracle
from src.utils.chainlink_feeds import get_feed_address, get_supported_tokens


class TestChainlinkPriceOracleIntegration:
    """Integration tests for Chainlink price oracle on real networks."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_base_mainnet_eth_price(self):
        """Test fetching ETH/USD price from Base Mainnet."""
        # Create oracle for Base Mainnet
        oracle = ChainlinkPriceOracle(
            network="base-mainnet",
            cache_ttl_seconds=60,
            max_staleness_seconds=3600,
        )

        # Fetch ETH price
        eth_price = await oracle.get_price("ETH", "USD")

        # Validate price is reasonable (between $1000 and $10000)
        assert isinstance(eth_price, Decimal)
        assert Decimal("1000") < eth_price < Decimal("10000"), (
            f"ETH price ${eth_price} seems unreasonable"
        )

        # Verify cache works
        cached_price = await oracle.get_price("ETH", "USD")
        assert cached_price == eth_price  # Should be from cache

        # Check cache stats
        stats = oracle.get_cache_stats()
        assert stats["size"] == 1
        assert stats["tokens"][0]["symbol"] == "ETH"
        assert not stats["tokens"][0]["is_stale"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_base_mainnet_multiple_tokens(self):
        """Test fetching multiple token prices from Base Mainnet."""
        oracle = ChainlinkPriceOracle(
            network="base-mainnet",
            cache_ttl_seconds=60,
            max_staleness_seconds=3600,
        )

        # Fetch multiple prices concurrently
        tokens = ["ETH", "USDC", "DAI"]
        prices = await oracle.get_prices(tokens, "USD")

        # Validate all prices fetched
        assert len(prices) == 3
        assert all(token in prices for token in tokens)

        # Validate price ranges
        assert Decimal("1000") < prices["ETH"] < Decimal("10000")
        assert Decimal("0.95") < prices["USDC"] < Decimal("1.05")
        assert Decimal("0.95") < prices["DAI"] < Decimal("1.05")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_weth_maps_to_eth(self):
        """Test that WETH price correctly maps to ETH feed."""
        oracle = ChainlinkPriceOracle(
            network="base-mainnet",
            cache_ttl_seconds=60,
        )

        # Fetch both ETH and WETH prices
        eth_price = await oracle.get_price("ETH", "USD")
        weth_price = await oracle.get_price("WETH", "USD")

        # Should be the same price
        assert weth_price == eth_price

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_base_sepolia_limited_feeds(self):
        """Test Base Sepolia with limited feed availability and fallback."""
        # Create oracle with mock fallback
        oracle = ChainlinkPriceOracle(
            network="base-sepolia",
            cache_ttl_seconds=60,
            fallback_oracle=MockPriceOracle(),
        )

        # ETH should work (if feed is available)
        eth_price = await oracle.get_price("ETH", "USD")
        assert isinstance(eth_price, Decimal)
        assert eth_price > 0

        # USDC might need fallback (if no feed on testnet)
        usdc_price = await oracle.get_price("USDC", "USD")
        assert isinstance(usdc_price, Decimal)
        assert usdc_price == Decimal("1.00")  # Mock fallback value

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_staleness_detection(self):
        """Test price staleness detection."""
        oracle = ChainlinkPriceOracle(
            network="base-mainnet",
            cache_ttl_seconds=1,  # Very short TTL for testing
            max_staleness_seconds=3600,
        )

        # Fetch price
        price1 = await oracle.get_price("ETH", "USD")
        assert not oracle.is_price_stale("ETH", max_age_seconds=5)

        # Wait for cache to become stale
        await asyncio.sleep(2)
        assert oracle.is_price_stale("ETH", max_age_seconds=1)

        # Fetch again should refresh
        price2 = await oracle.get_price("ETH", "USD")
        assert not oracle.is_price_stale("ETH", max_age_seconds=5)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cross_network_price_query(self):
        """Test querying Base Mainnet prices for use in another network context."""
        # Simulates getting reliable mainnet prices for testnet execution
        oracle = ChainlinkPriceOracle(
            network="base-sepolia",  # Execution network
            price_network="base-mainnet",  # Price source network
            cache_ttl_seconds=300,
        )

        # Should query Base Mainnet for prices
        eth_price = await oracle.get_price("ETH", "USD")
        assert Decimal("1000") < eth_price < Decimal("10000")

        # Cache should work across networks
        stats = oracle.get_cache_stats()
        assert stats["size"] == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_error_handling_with_fallback(self):
        """Test error handling and fallback behavior."""
        mock_fallback = MockPriceOracle()
        mock_fallback.set_price("UNKNOWN", Decimal("42.00"))

        oracle = ChainlinkPriceOracle(
            network="base-mainnet",
            fallback_oracle=mock_fallback,
        )

        # Try to fetch price for token without feed
        price = await oracle.get_price("UNKNOWN", "USD")
        assert price == Decimal("42.00")  # Should use fallback

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_factory_function(self):
        """Test create_price_oracle factory function."""
        # Create mock oracle
        mock_oracle = create_price_oracle("mock")
        assert isinstance(mock_oracle, MockPriceOracle)
        mock_price = await mock_oracle.get_price("ETH")
        assert mock_price == Decimal("3000.00")

        # Create Chainlink oracle with fallback
        chainlink_oracle = create_price_oracle(
            "chainlink",
            network="base-mainnet",
            price_network="base-mainnet",
            cache_ttl_seconds=300,
            fallback_to_mock=True,
        )
        assert isinstance(chainlink_oracle, ChainlinkPriceOracle)
        assert chainlink_oracle.fallback_oracle is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_btc_price_on_base_mainnet(self):
        """Test fetching BTC/USD price from Base Mainnet."""
        oracle = ChainlinkPriceOracle(
            network="base-mainnet",
            cache_ttl_seconds=60,
        )

        btc_price = await oracle.get_price("BTC", "USD")

        # BTC should be between $20k and $200k (wide range for volatility)
        assert isinstance(btc_price, Decimal)
        assert Decimal("20000") < btc_price < Decimal("200000"), (
            f"BTC price ${btc_price} seems unreasonable"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_price_feed_availability_check(self):
        """Test checking if price feeds are available."""
        from src.utils.chainlink_feeds import is_feed_available

        # Base Mainnet should have these feeds
        assert is_feed_available("base-mainnet", "ETH", "USD")
        assert is_feed_available("base-mainnet", "USDC", "USD")
        assert is_feed_available("base-mainnet", "DAI", "USD")
        assert is_feed_available("base-mainnet", "BTC", "USD")

        # Base Sepolia has limited feeds
        assert is_feed_available("base-sepolia", "ETH", "USD")
        assert not is_feed_available("base-sepolia", "AERO", "USD")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_price_queries(self):
        """Test concurrent price queries for performance."""
        oracle = ChainlinkPriceOracle(
            network="base-mainnet",
            cache_ttl_seconds=60,
        )

        # Query 10 prices concurrently
        tokens = ["ETH"] * 5 + ["USDC"] * 5  # Duplicate tokens
        start = time.time()
        prices = await oracle.get_prices(tokens, "USD")
        duration = time.time() - start

        # Should be fast due to caching after first fetch
        assert duration < 5.0  # Should complete within 5 seconds
        assert len(prices) == 10

        # All ETH prices should be the same (cached)
        eth_prices = [prices[token] for token in tokens[:5]]
        assert all(p == eth_prices[0] for p in eth_prices)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cache_clearing(self):
        """Test cache clearing functionality."""
        oracle = ChainlinkPriceOracle(
            network="base-mainnet",
            cache_ttl_seconds=300,
        )

        # Fetch some prices
        await oracle.get_price("ETH", "USD")
        await oracle.get_price("USDC", "USD")

        stats = oracle.get_cache_stats()
        assert stats["size"] == 2

        # Clear specific token
        oracle.clear_cache("ETH")
        stats = oracle.get_cache_stats()
        assert stats["size"] == 1
        assert stats["tokens"][0]["symbol"] == "USDC"

        # Clear all
        oracle.clear_cache()
        stats = oracle.get_cache_stats()
        assert stats["size"] == 0


class TestChainlinkPriceOracleUnit:
    """Unit tests for Chainlink price oracle (no network required)."""

    def test_supported_tokens_list(self):
        """Test getting list of supported tokens."""
        tokens = get_supported_tokens("base-mainnet", "USD")
        assert "ETH" in tokens
        assert "USDC" in tokens
        assert "DAI" in tokens
        assert "BTC" in tokens

    def test_feed_address_lookup(self):
        """Test feed address lookup."""
        # Base Mainnet feeds
        eth_feed = get_feed_address("base-mainnet", "ETH", "USD")
        assert eth_feed == "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70"

        usdc_feed = get_feed_address("base-mainnet", "USDC", "USD")
        assert usdc_feed == "0x7e860098F58bBFC8648a4311b374B1D669a2bc6B"

        # Base Sepolia limited feeds
        eth_sepolia_feed = get_feed_address("base-sepolia", "ETH", "USD")
        assert eth_sepolia_feed == "0x4aDC67696bA383F43DD60A9e78F2C97Fbbfc7cb1"

        # Non-existent feed
        unknown_feed = get_feed_address("base-mainnet", "UNKNOWN", "USD")
        assert unknown_feed is None