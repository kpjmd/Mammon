"""Integration tests for wallet manager with price oracle.

Tests the integration between WalletManager and PriceOracle added in Phase 1C Sprint 2.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from src.blockchain.wallet import WalletManager
from src.data.oracles import MockPriceOracle, create_price_oracle


class TestWalletManagerPriceOracleIntegration:
    """Test WalletManager integration with PriceOracle."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return {
            "network": "base-sepolia",
            "dry_run_mode": True,
            "max_transaction_usd": Decimal("1000"),
            "daily_limit_usd": Decimal("5000"),
        }

    @pytest.fixture
    def wallet(self, config):
        """Create WalletManager with mock oracle."""
        oracle = MockPriceOracle()
        return WalletManager(config, price_oracle=oracle)

    @pytest.mark.asyncio
    async def test_wallet_initialization_with_oracle(self, config):
        """Test wallet can be initialized with custom oracle."""
        oracle = MockPriceOracle()
        wallet = WalletManager(config, price_oracle=oracle)

        assert wallet.price_oracle is oracle
        assert wallet.price_oracle is not None

    @pytest.mark.asyncio
    async def test_wallet_defaults_to_mock_oracle(self, config):
        """Test wallet defaults to MockPriceOracle when none provided."""
        wallet = WalletManager(config)

        assert wallet.price_oracle is not None
        assert isinstance(wallet.price_oracle, MockPriceOracle)

    @pytest.mark.asyncio
    async def test_convert_to_usd_uses_oracle(self, wallet):
        """Test that _convert_to_usd uses the price oracle."""
        amount = Decimal("1.0")

        # Get price from oracle directly
        expected_price = await wallet.price_oracle.get_price("ETH")
        expected_usd = amount * expected_price

        # Convert using wallet
        actual_usd = await wallet._convert_to_usd(amount, "ETH")

        assert actual_usd == expected_usd == Decimal("3000.00")

    @pytest.mark.asyncio
    async def test_convert_different_tokens(self, wallet):
        """Test converting different tokens to USD."""
        # ETH
        eth_usd = await wallet._convert_to_usd(Decimal("1.0"), "ETH")
        assert eth_usd == Decimal("3000.00")

        # USDC
        usdc_usd = await wallet._convert_to_usd(Decimal("100.0"), "USDC")
        assert usdc_usd == Decimal("100.00")

        # AERO
        aero_usd = await wallet._convert_to_usd(Decimal("100.0"), "AERO")
        assert aero_usd == Decimal("50.00")  # 100 * $0.50

    @pytest.mark.asyncio
    async def test_spending_limits_use_oracle_prices(self, wallet):
        """Test that spending limits use oracle prices for conversion."""
        # Mock wallet provider
        wallet.wallet_provider = MagicMock()
        wallet.wallet_provider.get_address = AsyncMock(return_value="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4")
        wallet.address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"

        # Try to build transaction with 0.1 ETH
        # At $3000/ETH, this is $300
        amount = Decimal("0.1")

        tx = await wallet.build_transaction(
            to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
            amount=amount,
            token="ETH"
        )

        # Should succeed (under $1000 limit)
        assert tx is not None
        assert tx["dry_run"] is True
        assert Decimal(tx["transaction"]["estimated_cost_usd"]) == Decimal("300.00")

    @pytest.mark.asyncio
    async def test_spending_limit_enforced_with_oracle_price(self, wallet):
        """Test that spending limits are enforced using oracle prices."""
        wallet.wallet_provider = MagicMock()
        wallet.wallet_provider.get_address = AsyncMock(return_value="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4")
        wallet.address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"

        # Try to send 1 ETH = $3000, which exceeds $1000 limit
        amount = Decimal("1.0")

        with pytest.raises(ValueError, match="exceeds spending limits"):
            await wallet.build_transaction(
                to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
                amount=amount,
                token="ETH"
            )

    @pytest.mark.asyncio
    async def test_custom_oracle_prices_affect_limits(self, config):
        """Test that custom oracle prices affect spending limit checks."""
        # Create oracle with custom ETH price
        oracle = MockPriceOracle()
        oracle.set_price("ETH", Decimal("1000.00"))  # Lower price

        wallet = WalletManager(config, price_oracle=oracle)
        wallet.wallet_provider = MagicMock()
        wallet.wallet_provider.get_address = AsyncMock(return_value="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4")
        wallet.address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"

        # At $1000/ETH, 0.5 ETH = $500 (under $1000 limit)
        amount = Decimal("0.5")

        tx = await wallet.build_transaction(
            to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
            amount=amount,
            token="ETH"
        )

        assert tx is not None
        assert Decimal(tx["transaction"]["estimated_cost_usd"]) == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_oracle_used_for_stablecoin_transfers(self, wallet):
        """Test oracle is used even for stablecoins."""
        wallet.wallet_provider = MagicMock()
        wallet.wallet_provider.get_address = AsyncMock(return_value="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4")
        wallet.address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"

        # Send 500 USDC (should be $500)
        amount = Decimal("500.0")

        tx = await wallet.build_transaction(
            to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
            amount=amount,
            token="USDC"
        )

        assert tx is not None
        assert Decimal(tx["transaction"]["estimated_cost_usd"]) == Decimal("500.00")


class TestPriceOraclePrecision:
    """Test precision handling in price oracle conversions."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return {
            "network": "base-sepolia",
            "dry_run_mode": True,
            "max_transaction_usd": Decimal("1000"),
            "daily_limit_usd": Decimal("5000"),
        }

    @pytest.mark.asyncio
    async def test_precise_usd_conversion(self, config):
        """Test that USD conversion maintains precision."""
        oracle = MockPriceOracle()
        wallet = WalletManager(config, price_oracle=oracle)

        # Convert small amount
        amount = Decimal("0.123456789")
        usd_amount = await wallet._convert_to_usd(amount, "ETH")

        # Should maintain precision: 0.123456789 * 3000
        expected = Decimal("370.370367")
        assert usd_amount == expected

    @pytest.mark.asyncio
    async def test_fractional_cents_handling(self, config):
        """Test handling of fractional cents in conversion."""
        oracle = MockPriceOracle()
        wallet = WalletManager(config, price_oracle=oracle)

        # Amount that results in fractional cents
        amount = Decimal("0.0000033")  # Tiny amount
        usd_amount = await wallet._convert_to_usd(amount, "ETH")

        # Should be precise: 0.0000033 * 3000 = 0.0099
        expected = Decimal("0.0099")
        assert usd_amount == expected


class TestMultiTokenSupport:
    """Test wallet support for multiple tokens via oracle."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return {
            "network": "base-sepolia",
            "dry_run_mode": True,
            "max_transaction_usd": Decimal("1000"),
            "daily_limit_usd": Decimal("5000"),
        }

    @pytest.fixture
    def wallet(self, config):
        """Create WalletManager with mock oracle."""
        oracle = MockPriceOracle()
        wallet = WalletManager(config, price_oracle=oracle)
        wallet.wallet_provider = MagicMock()
        wallet.wallet_provider.get_address = AsyncMock(return_value="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4")
        wallet.address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"
        return wallet

    @pytest.mark.asyncio
    async def test_build_transaction_with_different_tokens(self, wallet):
        """Test building transactions with different token types."""
        test_cases = [
            ("ETH", Decimal("0.1"), Decimal("300.00")),
            ("USDC", Decimal("500"), Decimal("500.00")),
            ("AERO", Decimal("100"), Decimal("50.00")),
        ]

        for token, amount, expected_usd in test_cases:
            tx = await wallet.build_transaction(
                to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
                amount=amount,
                token=token
            )

            assert tx is not None
            assert Decimal(tx["transaction"]["estimated_cost_usd"]) == expected_usd
            assert tx["transaction"]["token"] == token

    @pytest.mark.asyncio
    async def test_unknown_token_defaults_to_one_dollar(self, wallet):
        """Test that unknown tokens default to $1 via MockPriceOracle."""
        # Unknown token should default to $1.00 in mock oracle
        amount = Decimal("100")

        tx = await wallet.build_transaction(
            to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
            amount=amount,
            token="UNKNOWN"
        )

        assert tx is not None
        # 100 UNKNOWN @ $1.00 each = $100.00
        assert Decimal(tx["transaction"]["estimated_cost_usd"]) == Decimal("100.00")


class TestOracleIntegrationEdgeCases:
    """Test edge cases in oracle integration."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return {
            "network": "base-sepolia",
            "dry_run_mode": True,
            "max_transaction_usd": Decimal("1000"),
            "daily_limit_usd": Decimal("5000"),
        }

    @pytest.mark.asyncio
    async def test_zero_amount_conversion(self, config):
        """Test converting zero amount to USD."""
        wallet = WalletManager(config)
        usd_amount = await wallet._convert_to_usd(Decimal("0"), "ETH")

        assert usd_amount == Decimal("0")

    @pytest.mark.asyncio
    async def test_very_large_amount_conversion(self, config):
        """Test converting very large amount to USD."""
        wallet = WalletManager(config)

        # 1000 ETH @ $3000 = $3,000,000
        usd_amount = await wallet._convert_to_usd(Decimal("1000"), "ETH")

        assert usd_amount == Decimal("3000000")

    @pytest.mark.asyncio
    async def test_case_insensitive_token_names(self, config):
        """Test that token names are case-insensitive."""
        wallet = WalletManager(config)

        amount = Decimal("1.0")

        # All should give same result
        eth_upper = await wallet._convert_to_usd(amount, "ETH")
        eth_lower = await wallet._convert_to_usd(amount, "eth")
        eth_mixed = await wallet._convert_to_usd(amount, "Eth")

        assert eth_upper == eth_lower == eth_mixed == Decimal("3000.00")

    @pytest.mark.asyncio
    async def test_oracle_integration_with_daily_limits(self, config):
        """Test that oracle prices work correctly with daily spending limits."""
        wallet = WalletManager(config)
        wallet.wallet_provider = MagicMock()
        wallet.wallet_provider.get_address = AsyncMock(return_value="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4")
        wallet.address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"

        # Spend 0.2 ETH (=$600, under $1000 per-tx limit)
        amount1 = Decimal("0.2")
        tx1 = await wallet.build_transaction(
            to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
            amount=amount1,
            token="ETH"
        )
        assert tx1 is not None

        # Record spending
        wallet.spending_limits.record_transaction(Decimal("600"))

        # Try to spend another 0.2 ETH (another $600, total $1200 - under $5000 daily limit)
        tx2 = await wallet.build_transaction(
            to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
            amount=amount1,
            token="ETH"
        )
        assert tx2 is not None

        # Record second transaction
        wallet.spending_limits.record_transaction(Decimal("600"))

        # Spend more to get close to daily limit
        for _ in range(6):  # 6 more transactions of $600 each = $3600, total $4800
            tx = await wallet.build_transaction(
                to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
                amount=amount1,
                token="ETH"
            )
            assert tx is not None
            wallet.spending_limits.record_transaction(Decimal("600"))

        # Now total is $4800, try one more $600 (would be $5400 - exceeds $5000 daily limit)
        with pytest.raises(ValueError, match="exceeds spending limits"):
            await wallet.build_transaction(
                to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
                amount=amount1,
                token="ETH"
            )
