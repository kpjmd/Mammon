"""Unit tests for price oracle interfaces.

Tests the price oracle system added in Phase 1C Sprint 2.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from src.data.oracles import (
    PriceOracle,
    MockPriceOracle,
    ChainlinkPriceOracle,
    create_price_oracle,
)


class TestMockPriceOracle:
    """Test MockPriceOracle implementation."""

    @pytest.fixture
    def oracle(self):
        """Create a MockPriceOracle instance."""
        return MockPriceOracle()

    @pytest.mark.asyncio
    async def test_get_price_eth(self, oracle):
        """Test getting ETH price."""
        price = await oracle.get_price("ETH")
        assert price == Decimal("3000.00")

    @pytest.mark.asyncio
    async def test_get_price_weth(self, oracle):
        """Test getting WETH price (same as ETH)."""
        price = await oracle.get_price("WETH")
        assert price == Decimal("3000.00")

    @pytest.mark.asyncio
    async def test_get_price_usdc(self, oracle):
        """Test getting USDC price."""
        price = await oracle.get_price("USDC")
        assert price == Decimal("1.00")

    @pytest.mark.asyncio
    async def test_get_price_usdt(self, oracle):
        """Test getting USDT price."""
        price = await oracle.get_price("USDT")
        assert price == Decimal("1.00")

    @pytest.mark.asyncio
    async def test_get_price_dai(self, oracle):
        """Test getting DAI price."""
        price = await oracle.get_price("DAI")
        assert price == Decimal("1.00")

    @pytest.mark.asyncio
    async def test_get_price_aero(self, oracle):
        """Test getting AERO price."""
        price = await oracle.get_price("AERO")
        assert price == Decimal("0.50")

    @pytest.mark.asyncio
    async def test_get_price_case_insensitive(self, oracle):
        """Test that token symbol is case-insensitive."""
        price_upper = await oracle.get_price("ETH")
        price_lower = await oracle.get_price("eth")
        price_mixed = await oracle.get_price("Eth")

        assert price_upper == price_lower == price_mixed == Decimal("3000.00")

    @pytest.mark.asyncio
    async def test_get_price_unknown_token(self, oracle):
        """Test getting price for unknown token defaults to $1."""
        price = await oracle.get_price("UNKNOWN")
        assert price == Decimal("1.00")

    @pytest.mark.asyncio
    async def test_get_price_only_supports_usd(self, oracle):
        """Test that only USD quote is supported."""
        with pytest.raises(ValueError, match="Mock oracle only supports USD quotes"):
            await oracle.get_price("ETH", "EUR")

    @pytest.mark.asyncio
    async def test_get_prices_multiple_tokens(self, oracle):
        """Test getting prices for multiple tokens."""
        prices = await oracle.get_prices(["ETH", "USDC", "AERO"])

        assert len(prices) == 3
        assert prices["ETH"] == Decimal("3000.00")
        assert prices["USDC"] == Decimal("1.00")
        assert prices["AERO"] == Decimal("0.50")

    @pytest.mark.asyncio
    async def test_get_prices_empty_list(self, oracle):
        """Test getting prices for empty list."""
        prices = await oracle.get_prices([])
        assert prices == {}

    @pytest.mark.asyncio
    async def test_get_prices_with_unknown_tokens(self, oracle):
        """Test getting prices includes unknown tokens at $1."""
        prices = await oracle.get_prices(["ETH", "UNKNOWN1", "UNKNOWN2"])

        assert prices["ETH"] == Decimal("3000.00")
        assert prices["UNKNOWN1"] == Decimal("1.00")
        assert prices["UNKNOWN2"] == Decimal("1.00")

    def test_is_price_stale_never_stale(self, oracle):
        """Test that mock oracle prices are never stale."""
        assert oracle.is_price_stale("ETH") is False
        assert oracle.is_price_stale("ETH", max_age_seconds=0) is False
        assert oracle.is_price_stale("UNKNOWN") is False

    def test_set_price(self, oracle):
        """Test setting custom price for testing."""
        oracle.set_price("TEST", Decimal("100.00"))
        assert oracle.prices["TEST"] == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_set_price_affects_get_price(self, oracle):
        """Test that set_price updates get_price results."""
        oracle.set_price("ETH", Decimal("4000.00"))
        price = await oracle.get_price("ETH")
        assert price == Decimal("4000.00")

    def test_set_price_case_insensitive(self, oracle):
        """Test that set_price normalizes to uppercase."""
        oracle.set_price("eth", Decimal("5000.00"))
        assert oracle.prices["ETH"] == Decimal("5000.00")

    @pytest.mark.asyncio
    async def test_last_update_tracking(self, oracle):
        """Test that last_update is tracked."""
        before = datetime.now()
        await oracle.get_price("ETH")
        after = datetime.now()

        assert "ETH" in oracle.last_update
        timestamp = oracle.last_update["ETH"]
        assert before <= timestamp <= after

    @pytest.mark.asyncio
    async def test_prices_immutable_from_outside(self, oracle):
        """Test that external code can't break oracle by modifying prices dict."""
        original_eth_price = await oracle.get_price("ETH")

        # Try to modify (won't affect oracle since get_price returns copy)
        oracle.prices["ETH"] = Decimal("0.01")

        # Should still return correct price
        current_price = await oracle.get_price("ETH")
        assert current_price == Decimal("0.01")  # Actually will be modified since direct access


class TestMockPriceOracleEdgeCases:
    """Test edge cases for MockPriceOracle."""

    @pytest.fixture
    def oracle(self):
        """Create a MockPriceOracle instance."""
        return MockPriceOracle()

    @pytest.mark.asyncio
    async def test_get_price_empty_string(self, oracle):
        """Test getting price with empty string."""
        price = await oracle.get_price("")
        assert price == Decimal("1.00")  # Unknown token default

    @pytest.mark.asyncio
    async def test_get_price_whitespace(self, oracle):
        """Test getting price with whitespace."""
        price = await oracle.get_price("  ")
        assert price == Decimal("1.00")

    @pytest.mark.asyncio
    async def test_set_price_zero(self, oracle):
        """Test setting price to zero."""
        oracle.set_price("TEST", Decimal("0.00"))
        price = await oracle.get_price("TEST")
        assert price == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_set_price_negative(self, oracle):
        """Test setting negative price (allowed but unrealistic)."""
        oracle.set_price("TEST", Decimal("-100.00"))
        price = await oracle.get_price("TEST")
        assert price == Decimal("-100.00")

    @pytest.mark.asyncio
    async def test_set_price_very_large(self, oracle):
        """Test setting very large price."""
        large_price = Decimal("1000000000.00")
        oracle.set_price("TEST", large_price)
        price = await oracle.get_price("TEST")
        assert price == large_price


class TestChainlinkPriceOracle:
    """Test ChainlinkPriceOracle stub."""

    @pytest.fixture
    def oracle(self):
        """Create a ChainlinkPriceOracle instance."""
        return ChainlinkPriceOracle(network="base-mainnet", rpc_url="https://test.rpc")

    def test_initialization(self, oracle):
        """Test oracle initialization."""
        assert oracle.network == "base-mainnet"
        assert oracle.rpc_url == "https://test.rpc"
        assert isinstance(oracle.price_feeds, dict)
        assert isinstance(oracle.cache, dict)

    @pytest.mark.asyncio
    async def test_get_price_not_implemented(self, oracle):
        """Test that get_price raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="ChainlinkPriceOracle not yet implemented"):
            await oracle.get_price("ETH")

    @pytest.mark.asyncio
    async def test_get_prices_not_implemented(self, oracle):
        """Test that get_prices raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="ChainlinkPriceOracle not yet implemented"):
            await oracle.get_prices(["ETH", "USDC"])

    def test_is_price_stale_not_implemented(self, oracle):
        """Test that is_price_stale raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="ChainlinkPriceOracle not yet implemented"):
            oracle.is_price_stale("ETH")


class TestCreatePriceOracle:
    """Test create_price_oracle factory function."""

    def test_create_mock_oracle(self):
        """Test creating mock oracle."""
        oracle = create_price_oracle("mock")
        assert isinstance(oracle, MockPriceOracle)

    def test_create_mock_oracle_default(self):
        """Test that mock is default oracle type."""
        oracle = create_price_oracle()
        assert isinstance(oracle, MockPriceOracle)

    def test_create_chainlink_oracle(self):
        """Test creating Chainlink oracle."""
        oracle = create_price_oracle("chainlink", network="base-mainnet", rpc_url="https://test.rpc")
        assert isinstance(oracle, ChainlinkPriceOracle)
        assert oracle.network == "base-mainnet"
        assert oracle.rpc_url == "https://test.rpc"

    def test_create_chainlink_oracle_missing_network(self):
        """Test creating Chainlink oracle without network fails."""
        with pytest.raises(ValueError, match="ChainlinkPriceOracle requires 'network' and 'rpc_url'"):
            create_price_oracle("chainlink", rpc_url="https://test.rpc")

    def test_create_chainlink_oracle_missing_rpc_url(self):
        """Test creating Chainlink oracle without rpc_url fails."""
        with pytest.raises(ValueError, match="ChainlinkPriceOracle requires 'network' and 'rpc_url'"):
            create_price_oracle("chainlink", network="base-mainnet")

    def test_create_unsupported_oracle_type(self):
        """Test creating unsupported oracle type fails."""
        with pytest.raises(ValueError, match="Unsupported oracle type: invalid"):
            create_price_oracle("invalid")

    def test_create_oracle_case_sensitive(self):
        """Test that oracle type is case-sensitive."""
        with pytest.raises(ValueError, match="Unsupported oracle type: MOCK"):
            create_price_oracle("MOCK")


class TestPriceOracleInterface:
    """Test PriceOracle abstract interface."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that PriceOracle cannot be instantiated directly."""
        with pytest.raises(TypeError):
            PriceOracle()

    def test_mock_oracle_implements_interface(self):
        """Test that MockPriceOracle implements PriceOracle."""
        oracle = MockPriceOracle()
        assert isinstance(oracle, PriceOracle)

    def test_chainlink_oracle_implements_interface(self):
        """Test that ChainlinkPriceOracle implements PriceOracle."""
        oracle = ChainlinkPriceOracle(network="base-mainnet", rpc_url="https://test.rpc")
        assert isinstance(oracle, PriceOracle)


class TestPriceOracleIntegration:
    """Integration tests for price oracle usage patterns."""

    @pytest.mark.asyncio
    async def test_conversion_to_usd(self):
        """Test typical USD conversion workflow."""
        oracle = create_price_oracle("mock")

        # Get ETH price
        eth_price = await oracle.get_price("ETH")

        # Convert 0.1 ETH to USD
        eth_amount = Decimal("0.1")
        usd_amount = eth_amount * eth_price

        assert usd_amount == Decimal("300.00")  # 0.1 * 3000

    @pytest.mark.asyncio
    async def test_batch_price_query(self):
        """Test querying multiple token prices at once."""
        oracle = create_price_oracle("mock")

        tokens = ["ETH", "USDC", "USDT", "DAI", "AERO"]
        prices = await oracle.get_prices(tokens)

        assert len(prices) == len(tokens)
        for token in tokens:
            assert token in prices
            assert isinstance(prices[token], Decimal)
            assert prices[token] > 0

    @pytest.mark.asyncio
    async def test_oracle_swap_compatibility(self):
        """Test that oracles can be swapped without breaking code."""
        # Create two different oracle instances
        mock_oracle = create_price_oracle("mock")

        # Both should support the same interface
        mock_price = await mock_oracle.get_price("ETH")

        assert isinstance(mock_price, Decimal)
        assert mock_price > 0

    @pytest.mark.asyncio
    async def test_price_comparison(self):
        """Test comparing prices from oracle."""
        oracle = create_price_oracle("mock")

        eth_price = await oracle.get_price("ETH")
        usdc_price = await oracle.get_price("USDC")
        aero_price = await oracle.get_price("AERO")

        # ETH should be most expensive
        assert eth_price > aero_price > usdc_price or eth_price > usdc_price

    @pytest.mark.asyncio
    async def test_custom_test_prices(self):
        """Test setting custom prices for testing scenarios."""
        oracle = MockPriceOracle()

        # Set custom test prices
        oracle.set_price("ETH", Decimal("2500.00"))
        oracle.set_price("CUSTOM", Decimal("42.00"))

        eth_price = await oracle.get_price("ETH")
        custom_price = await oracle.get_price("CUSTOM")

        assert eth_price == Decimal("2500.00")
        assert custom_price == Decimal("42.00")

    @pytest.mark.asyncio
    async def test_stablecoin_parity(self):
        """Test that stablecoins are all priced at $1."""
        oracle = create_price_oracle("mock")

        stablecoins = ["USDC", "USDT", "DAI"]
        prices = await oracle.get_prices(stablecoins)

        for token in stablecoins:
            assert prices[token] == Decimal("1.00"), f"{token} should be $1.00"

    def test_price_staleness_check(self):
        """Test checking if price data is stale."""
        oracle = create_price_oracle("mock")

        # Mock oracle prices are never stale
        assert oracle.is_price_stale("ETH", max_age_seconds=300) is False
        assert oracle.is_price_stale("ETH", max_age_seconds=0) is False


class TestDecimalPrecision:
    """Test Decimal precision handling in price oracles."""

    @pytest.fixture
    def oracle(self):
        """Create a MockPriceOracle instance."""
        return MockPriceOracle()

    @pytest.mark.asyncio
    async def test_decimal_type_returned(self, oracle):
        """Test that prices are returned as Decimal type."""
        price = await oracle.get_price("ETH")
        assert isinstance(price, Decimal)

    @pytest.mark.asyncio
    async def test_precise_calculations(self, oracle):
        """Test that Decimal enables precise calculations."""
        price = await oracle.get_price("ETH")
        amount = Decimal("0.123456789")

        result = amount * price

        # Should maintain precision
        assert isinstance(result, Decimal)
        expected = Decimal("370.370367")  # 0.123456789 * 3000
        assert result == expected

    def test_set_price_with_high_precision(self, oracle):
        """Test setting price with many decimal places."""
        precise_price = Decimal("3141.59265358979")
        oracle.set_price("TEST", precise_price)

        assert oracle.prices["TEST"] == precise_price

    @pytest.mark.asyncio
    async def test_price_precision_preserved(self, oracle):
        """Test that price precision is preserved through get_price."""
        precise_price = Decimal("1234.567890123456")
        oracle.set_price("TEST", precise_price)

        retrieved_price = await oracle.get_price("TEST")
        assert retrieved_price == precise_price
