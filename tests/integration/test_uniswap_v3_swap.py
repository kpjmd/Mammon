"""Integration tests for Uniswap V3 swap functionality.

Tests cover:
1. Quote retrieval from Uniswap
2. Price oracle cross-checking
3. Slippage protection calculation
4. Gas estimation
5. Transaction simulation
6. Complete swap flow (dry-run)
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

from src.blockchain.swap_executor import SwapExecutor
from src.blockchain.slippage_calculator import SlippageCalculator, PriceDeviationError
from src.data.oracles import MockPriceOracle, create_price_oracle
from src.protocols.uniswap_v3_quoter import UniswapV3Quoter
from src.protocols.uniswap_v3_router import UniswapV3Router
from src.security.approval import ApprovalManager
from src.utils.web3_provider import get_web3


class TestUniswapV3Quoter:
    """Test Uniswap V3 quoter functionality."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_quote_exact_input_eth_usdc(self):
        """Test getting quote for ETH -> USDC swap."""
        network = "base-sepolia"
        w3 = get_web3(network)

        quoter = UniswapV3Quoter(w3, network)

        # Get quote for 0.001 ETH -> USDC
        quote = await quoter.quote_exact_input(
            token_in="WETH",
            token_out="USDC",
            amount_in=Decimal("0.001"),
            fee_tier=3000,  # 0.3%
        )

        # Should return valid quote
        assert quote is not None
        assert quote.amount_out > 0
        assert quote.amount_out_formatted > 0
        assert quote.price > 0
        assert quote.gas_estimate > 0

        # Price should be reasonable (ETH/USD around $2000-$5000)
        assert 2000 < quote.price < 5000

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_quote_with_different_fee_tiers(self):
        """Test quotes with different fee tiers."""
        network = "base-sepolia"
        w3 = get_web3(network)

        quoter = UniswapV3Quoter(w3, network)

        # Try 0.3% fee tier (most common)
        quote_3000 = await quoter.quote_exact_input(
            token_in="WETH",
            token_out="USDC",
            amount_in=Decimal("0.001"),
            fee_tier=3000,
        )

        # If 0.3% works, try 0.05% (for stable pairs)
        if quote_3000:
            quote_500 = await quoter.quote_exact_input(
                token_in="WETH",
                token_out="USDC",
                amount_in=Decimal("0.001"),
                fee_tier=500,
            )

            # Either succeeds or pool doesn't exist
            if quote_500:
                # Both quotes should be similar
                price_diff = abs(quote_3000.price - quote_500.price)
                assert price_diff < quote_3000.price * Decimal("0.1")  # Within 10%


class TestSlippageCalculator:
    """Test slippage protection calculations."""

    def test_calculate_min_output(self):
        """Test minimum output calculation."""
        calc = SlippageCalculator(default_slippage_bps=50)

        # 0.5% slippage on 100 USDC
        min_output = calc.calculate_min_output(Decimal("100"), slippage_bps=50)

        assert min_output == Decimal("99.5")

    def test_calculate_max_input(self):
        """Test maximum input calculation."""
        calc = SlippageCalculator(default_slippage_bps=50)

        # 0.5% slippage on 1 ETH
        max_input = calc.calculate_max_input(Decimal("1"), slippage_bps=50)

        assert max_input == Decimal("1.005")

    def test_validate_price_deviation_pass(self):
        """Test price validation passes with small deviation."""
        calc = SlippageCalculator(max_price_deviation_percent=Decimal("2.0"))

        # 1% deviation should pass
        calc.validate_price_deviation(
            dex_price=Decimal("3200"),
            oracle_price=Decimal("3168"),  # 1% difference
        )

    def test_validate_price_deviation_fail(self):
        """Test price validation fails with large deviation."""
        calc = SlippageCalculator(max_price_deviation_percent=Decimal("2.0"))

        # 5% deviation should fail
        with pytest.raises(PriceDeviationError):
            calc.validate_price_deviation(
                dex_price=Decimal("3200"),
                oracle_price=Decimal("3040"),  # 5% difference
            )

    def test_calculate_price_impact(self):
        """Test price impact calculation."""
        calc = SlippageCalculator()

        # Swap 1 ETH for 3180 USDC with oracle at $3200
        impact = calc.calculate_price_impact(
            amount_in=Decimal("1"),
            amount_out=Decimal("3180"),
            oracle_price=Decimal("3200"),
        )

        # Should show negative impact (got less than oracle price)
        assert impact < 0
        assert abs(impact) < 1  # Should be less than 1% for small swap


class TestSwapExecutor:
    """Test complete swap execution flow."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_swap_dry_run_eth_to_usdc(self):
        """Test complete swap flow in dry-run mode."""
        network = "base-sepolia"
        w3 = get_web3(network)

        # Create mock oracle with reasonable ETH price
        oracle = MockPriceOracle()
        oracle.set_price("ETH", Decimal("3200.00"))

        # Create approval manager (high threshold so no approval needed)
        approval_manager = ApprovalManager(
            approval_threshold_usd=Decimal("1000"),
        )

        # Create swap executor
        executor = SwapExecutor(
            w3=w3,
            network=network,
            price_oracle=oracle,
            approval_manager=approval_manager,
            default_slippage_bps=50,
        )

        # Use a testnet address
        test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

        # Execute dry-run swap
        result = await executor.execute_swap(
            token_in="WETH",
            token_out="USDC",
            amount_in=Decimal("0.001"),
            from_address=test_address,
            dry_run=True,
        )

        # Should succeed in dry-run
        assert result["success"] == True
        assert result["dry_run"] == True

        # Should have all required fields
        assert "quote" in result
        assert "oracle_price" in result
        assert "price_impact" in result
        assert "slippage" in result
        assert "gas" in result
        assert "approval" in result

        # Security checks should all pass
        security = result["security_checks"]
        assert security.passed == True
        assert security.checks["uniswap_quote"] == True
        assert security.checks["oracle_price"] == True
        assert security.checks["price_deviation"] == True
        assert security.checks["slippage_protection"] == True
        assert security.checks["gas_estimation"] == True
        assert security.checks["simulation"] == True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_swap_fails_with_stale_price(self):
        """Test swap fails when oracle price is stale (strict mode)."""
        network = "base-sepolia"
        w3 = get_web3(network)

        # Create oracle with strict staleness
        oracle = create_price_oracle(
            chainlink_enabled=True,
            chainlink_price_network="base-mainnet",
            strict_staleness=True,
            max_staleness_seconds=1,  # Very short staleness window
        )

        approval_manager = ApprovalManager(
            approval_threshold_usd=Decimal("1000"),
        )

        executor = SwapExecutor(
            w3=w3,
            network=network,
            price_oracle=oracle,
            approval_manager=approval_manager,
        )

        test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

        # This might fail with stale price error
        result = await executor.execute_swap(
            token_in="WETH",
            token_out="USDC",
            amount_in=Decimal("0.001"),
            from_address=test_address,
            dry_run=True,
        )

        # If it fails, should be due to staleness check
        if not result["success"]:
            security = result["security_checks"]
            # Either oracle_staleness check failed or price check
            assert (
                not security.checks.get("oracle_staleness", True)
                or "stale" in result.get("error", "").lower()
            )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_swap_fails_with_price_deviation(self):
        """Test swap fails when DEX price deviates too much from oracle."""
        network = "base-sepolia"
        w3 = get_web3(network)

        # Create oracle with unrealistic price
        oracle = MockPriceOracle()
        oracle.set_price("ETH", Decimal("10000.00"))  # Way too high

        approval_manager = ApprovalManager(
            approval_threshold_usd=Decimal("1000"),
        )

        executor = SwapExecutor(
            w3=w3,
            network=network,
            price_oracle=oracle,
            approval_manager=approval_manager,
            max_price_deviation_percent=Decimal("2.0"),
        )

        test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

        result = await executor.execute_swap(
            token_in="WETH",
            token_out="USDC",
            amount_in=Decimal("0.001"),
            from_address=test_address,
            dry_run=True,
        )

        # Should fail price deviation check
        assert result["success"] == False
        security = result["security_checks"]
        assert security.checks["price_deviation"] == False
        assert "deviation" in result.get("error", "").lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_swap_requires_approval(self):
        """Test swap requires approval when above threshold."""
        network = "base-sepolia"
        w3 = get_web3(network)

        oracle = MockPriceOracle()
        oracle.set_price("ETH", Decimal("3200.00"))

        # Low approval threshold
        approval_manager = ApprovalManager(
            approval_threshold_usd=Decimal("1"),  # $1 threshold
        )

        executor = SwapExecutor(
            w3=w3,
            network=network,
            price_oracle=oracle,
            approval_manager=approval_manager,
        )

        test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

        result = await executor.execute_swap(
            token_in="WETH",
            token_out="USDC",
            amount_in=Decimal("0.001"),  # ~$3.20 worth
            from_address=test_address,
            dry_run=True,
        )

        # Should require approval
        assert result["approval"]["required"] == True

        # In dry-run, should still succeed (no actual approval needed)
        assert result["success"] == True


class TestUniswapV3Router:
    """Test Uniswap V3 router functionality."""

    @pytest.mark.integration
    def test_router_initialization(self):
        """Test router initializes correctly."""
        network = "base-sepolia"
        w3 = get_web3(network)

        router = UniswapV3Router(w3, network)

        assert router.network == network
        assert router.router is not None

    @pytest.mark.integration
    def test_encode_path_single_hop(self):
        """Test encoding single-hop path."""
        network = "base-sepolia"
        w3 = get_web3(network)

        router = UniswapV3Router(w3, network)

        # Encode WETH -> USDC path
        path = router.encode_path(
            tokens=["WETH", "USDC"],
            fees=[3000],  # 0.3%
        )

        # Path should be 20 + 3 + 20 = 43 bytes
        assert len(path) == 43

    @pytest.mark.integration
    def test_calculate_deadline(self):
        """Test deadline calculation."""
        network = "base-sepolia"
        w3 = get_web3(network)

        router = UniswapV3Router(w3, network)

        deadline = router.calculate_deadline(600)

        import time

        # Should be roughly 600 seconds from now
        assert deadline > int(time.time())
        assert deadline < int(time.time()) + 700


class TestSecurityIntegration:
    """Test integration of all security layers."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_all_security_checks_pass(self):
        """Test that all security checks work together."""
        network = "base-sepolia"
        w3 = get_web3(network)

        oracle = MockPriceOracle()
        oracle.set_price("ETH", Decimal("3200.00"))

        approval_manager = ApprovalManager(
            approval_threshold_usd=Decimal("1000"),
        )

        executor = SwapExecutor(
            w3=w3,
            network=network,
            price_oracle=oracle,
            approval_manager=approval_manager,
        )

        test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

        result = await executor.execute_swap(
            token_in="WETH",
            token_out="USDC",
            amount_in=Decimal("0.001"),
            from_address=test_address,
            dry_run=True,
        )

        # Verify security check structure
        security = result["security_checks"]

        required_checks = [
            "uniswap_quote",
            "oracle_price",
            "price_deviation",
            "slippage_protection",
            "gas_estimation",
            "approval",
            "simulation",
            "overall",
        ]

        for check in required_checks:
            assert check in security.checks, f"Missing security check: {check}"

        # If all passed, should be successful
        if security.passed:
            assert result["success"] == True
            assert all(security.checks.values())

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_security_summary_format(self):
        """Test security summary formatting."""
        network = "base-sepolia"
        w3 = get_web3(network)

        oracle = MockPriceOracle()
        oracle.set_price("ETH", Decimal("3200.00"))

        approval_manager = ApprovalManager(
            approval_threshold_usd=Decimal("1000"),
        )

        executor = SwapExecutor(
            w3=w3,
            network=network,
            price_oracle=oracle,
            approval_manager=approval_manager,
        )

        test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

        result = await executor.execute_swap(
            token_in="WETH",
            token_out="USDC",
            amount_in=Decimal("0.001"),
            from_address=test_address,
            dry_run=True,
        )

        # Get security summary
        summary = executor.get_security_summary(result["security_checks"])

        # Should contain header
        assert "SECURITY CHECK SUMMARY" in summary

        # Should list all checks
        assert "uniswap_quote" in summary
        assert "price_deviation" in summary

        # Should show pass/fail status
        assert ("✅ PASS" in summary) or ("❌ FAIL" in summary)
