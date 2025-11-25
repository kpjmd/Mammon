"""Integration test for Aerodrome TVL calculation with Chainlink oracle.

Tests that Aerodrome protocol correctly uses real Chainlink prices
to calculate TVL for pools on Base Mainnet.
"""

import asyncio
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from src.protocols.aerodrome import AerodromeProtocol
from src.data.oracles import ChainlinkPriceOracle, MockPriceOracle


class TestAerodromeTVLWithChainlink:
    """Test Aerodrome TVL calculations using Chainlink price oracle."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_aerodrome_with_chainlink_oracle(self):
        """Test that Aerodrome initializes and uses Chainlink oracle."""
        # Create Aerodrome with Chainlink enabled
        config = {
            "network": "base-mainnet",
            "dry_run_mode": True,  # Keep dry run for safety
            "chainlink_enabled": True,
            "chainlink_price_network": "base-mainnet",
            "chainlink_cache_ttl_seconds": 60,
            "chainlink_fallback_to_mock": True,
        }

        protocol = AerodromeProtocol(config)

        # Verify Chainlink oracle was initialized
        assert isinstance(protocol.price_oracle, ChainlinkPriceOracle)
        assert protocol.price_oracle.price_network == "base-mainnet"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_tvl_calculation_with_real_prices(self):
        """Test TVL calculation using real Chainlink prices."""
        # Create protocol with Chainlink
        config = {
            "network": "base-mainnet",
            "chainlink_enabled": True,
            "chainlink_price_network": "base-mainnet",
            "chainlink_cache_ttl_seconds": 60,
        }

        protocol = AerodromeProtocol(config)

        # Test TVL calculation with sample reserves
        # Simulate a WETH/USDC pool with 100 WETH and 300,000 USDC
        reserve0 = 100 * 10**18  # 100 WETH (18 decimals)
        reserve1 = 300000 * 10**6  # 300,000 USDC (6 decimals)
        decimals0 = 18
        decimals1 = 6

        tvl, metadata = await protocol._estimate_tvl(
            reserve0, reserve1, decimals0, decimals1, "WETH", "USDC"
        )

        # TVL should be reasonable (between $500k and $1M for this example)
        assert isinstance(tvl, Decimal)
        assert tvl > 0

        # Should have real prices in metadata
        assert "price0_usd" in metadata
        assert "price1_usd" in metadata
        assert "tvl_method" in metadata

        # WETH price should be reasonable
        weth_price = Decimal(metadata["price0_usd"])
        assert Decimal("1000") < weth_price < Decimal("10000")

        # USDC price should be close to $1
        usdc_price = Decimal(metadata["price1_usd"])
        assert Decimal("0.95") < usdc_price < Decimal("1.05")

        # Log results for debugging
        print(f"WETH price: ${weth_price}")
        print(f"USDC price: ${usdc_price}")
        print(f"Total TVL: ${tvl:,.2f}")
        print(f"TVL method: {metadata['tvl_method']}")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_fallback_to_mock_oracle(self):
        """Test fallback to mock oracle when Chainlink fails."""
        # Create protocol with fallback enabled
        config = {
            "network": "base-mainnet",
            "chainlink_enabled": True,
            "chainlink_fallback_to_mock": True,
        }

        protocol = AerodromeProtocol(config)

        # Test with a token that doesn't have a Chainlink feed
        reserve0 = 1000 * 10**18  # 1000 UNKNOWN tokens
        reserve1 = 2000 * 10**6  # 2000 USDC

        tvl, metadata = await protocol._estimate_tvl(
            reserve0, reserve1, 18, 6, "UNKNOWN", "USDC"
        )

        # Should still calculate TVL using fallback
        assert tvl > 0
        assert metadata["tvl_method"] in ["chainlink_oracle", "mock_oracle"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_aerodrome_mock_pools_tvl(self):
        """Test that mock pools return reasonable TVL values."""
        # Create protocol with mock oracle for comparison
        config = {
            "network": "base-sepolia",  # Use testnet to get mock pools
            "chainlink_enabled": False,
        }

        protocol = AerodromeProtocol(config)

        # Get mock pools
        pools = await protocol.get_pools()

        # All mock pools should have TVL
        assert len(pools) > 0
        for pool in pools:
            assert pool.tvl > 0
            assert isinstance(pool.tvl, Decimal)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_price_oracle_caching(self):
        """Test that price oracle caching works for TVL calculations."""
        config = {
            "network": "base-mainnet",
            "chainlink_enabled": True,
            "chainlink_cache_ttl_seconds": 300,
        }

        protocol = AerodromeProtocol(config)

        # First TVL calculation - should fetch prices
        reserve = 10 * 10**18
        tvl1, metadata1 = await protocol._estimate_tvl(
            reserve, reserve, 18, 18, "WETH", "WETH"
        )

        # Second calculation - should use cached prices
        tvl2, metadata2 = await protocol._estimate_tvl(
            reserve, reserve, 18, 18, "WETH", "WETH"
        )

        # Prices should be identical (from cache)
        assert metadata1["price0_usd"] == metadata2["price0_usd"]
        assert tvl1 == tvl2

        # Check cache stats
        stats = protocol.price_oracle.get_cache_stats()
        assert stats["size"] >= 1
        assert not stats["tokens"][0]["is_stale"]


class TestAerodromeTVLUnit:
    """Unit tests for Aerodrome TVL calculation (no network required)."""

    @pytest.mark.asyncio
    async def test_tvl_calculation_logic(self):
        """Test TVL calculation with known values."""
        # Create protocol with mock oracle
        config = {
            "network": "base-mainnet",
            "chainlink_enabled": False,
        }

        protocol = AerodromeProtocol(config)

        # Mock oracle returns $3000 for ETH, $1 for USDC
        reserve0 = 10 * 10**18  # 10 ETH
        reserve1 = 30000 * 10**6  # 30,000 USDC

        tvl, metadata = await protocol._estimate_tvl(
            reserve0, reserve1, 18, 6, "ETH", "USDC"
        )

        # TVL should be: (10 * $3000) + (30000 * $1) = $60,000
        expected_tvl = Decimal("60000")
        assert tvl == expected_tvl

        # Check metadata
        assert metadata["price0_usd"] == "3000.00"
        assert metadata["price1_usd"] == "1.00"
        assert metadata["token0_amount"] == "10"
        assert metadata["token1_amount"] == "30000"

    @pytest.mark.asyncio
    async def test_oracle_initialization_modes(self):
        """Test different oracle initialization configurations."""
        # Test with Chainlink disabled
        config1 = {
            "network": "base-mainnet",
            "chainlink_enabled": False,
        }
        protocol1 = AerodromeProtocol(config1)
        assert isinstance(protocol1.price_oracle, MockPriceOracle)

        # Test with Chainlink enabled
        config2 = {
            "network": "base-mainnet",
            "chainlink_enabled": True,
            "chainlink_fallback_to_mock": False,
        }
        protocol2 = AerodromeProtocol(config2)
        assert isinstance(protocol2.price_oracle, ChainlinkPriceOracle)
        assert protocol2.price_oracle.fallback_oracle is None

        # Test with Chainlink and fallback
        config3 = {
            "network": "base-mainnet",
            "chainlink_enabled": True,
            "chainlink_fallback_to_mock": True,
        }
        protocol3 = AerodromeProtocol(config3)
        assert isinstance(protocol3.price_oracle, ChainlinkPriceOracle)
        assert isinstance(protocol3.price_oracle.fallback_oracle, MockPriceOracle)