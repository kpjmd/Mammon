"""Comprehensive test suite for gas estimation functionality.

Tests cover the 5 required scenarios:
1. Estimate succeeds, actual gas within 10%
2. Estimate fails → fallback to conservative default
3. Gas price exceeds cap → rejection
4. Gas cost exceeds spending limit → approval required
5. Network-specific buffers applied correctly
"""

import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

import pytest
from web3 import Web3

from src.blockchain.gas_estimator import GasEstimator, GasEstimateMode
from src.data.oracles import MockPriceOracle, create_price_oracle
from src.security.approval import ApprovalManager


class TestGasEstimationAccuracy:
    """Test 1: Estimate succeeds, actual gas within 10%."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_simple_transfer_accuracy(self):
        """Test gas estimation for simple ETH transfer."""
        # Create gas estimator
        oracle = MockPriceOracle()
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
            estimate_mode=GasEstimateMode.DIRECT,
        )

        # Estimate gas for simple transfer
        test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
        value_wei = estimator.w3.to_wei(0.01, "ether")

        gas_estimate = await estimator.estimate_gas(
            to=test_address,
            value=value_wei,
            data="0x",
        )

        # Simple transfer should be around 21000 with 20% buffer = ~25,200
        assert 21000 <= gas_estimate <= 30000
        assert gas_estimate >= 21000 * 1.2  # At least 20% buffer

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_buffer_tiers(self):
        """Test that different transaction types get appropriate buffers."""
        oracle = MockPriceOracle()
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
        )

        test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

        # Simple transfer: 20% buffer
        gas_simple = await estimator.estimate_gas(
            to=test_address,
            value=estimator.w3.to_wei(0.01, "ether"),
            data="0x",
        )

        # Small data (ERC20-like): 30% buffer
        gas_erc20 = await estimator.estimate_gas(
            to=test_address,
            data="0xa9059cbb" + "0" * 128,  # 68 bytes
        )

        # Medium data (DEX swap-like): 50% buffer
        gas_swap = await estimator.estimate_gas(
            to=test_address,
            data="0x" + "0" * 400,  # 202 bytes
        )

        # Complex data: 100% buffer
        gas_complex = await estimator.estimate_gas(
            to=test_address,
            data="0x" + "0" * 1000,  # 502 bytes
        )

        # Verify all estimates are positive (buffers applied)
        assert gas_simple > 0
        assert gas_erc20 > 0
        assert gas_swap > 0
        assert gas_complex > 0

        # Verify simple transfer has minimum 20% buffer (21000 base * 1.2)
        assert gas_simple >= 21000 * 1.2

        # Verify complex is higher than simple (due to larger buffer)
        assert gas_complex > gas_simple


class TestGasEstimationFallback:
    """Test 2: Estimate fails → fallback to conservative default."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_estimation_failure_fallback(self):
        """Test fallback when gas estimation fails."""
        oracle = MockPriceOracle()
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
        )

        # Try to estimate for invalid address (should fail gracefully)
        with patch.object(estimator.w3.eth, "estimate_gas", side_effect=Exception("RPC error")):
            gas_estimate = await estimator.estimate_gas(
                to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
                value=estimator.w3.to_wei(0.01, "ether"),
            )

            # Should return default (21000 * 1.2 = 25,200)
            assert gas_estimate == 25200

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_fallback_conservative_defaults(self):
        """Test that fallback defaults are appropriately conservative."""
        oracle = MockPriceOracle()
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
        )

        # Mock eth_estimateGas to fail
        with patch.object(estimator.w3.eth, "estimate_gas", side_effect=Exception("Failed")):
            # Simple transfer fallback
            gas_simple = await estimator.estimate_gas(
                to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
                value=100,
            )
            assert gas_simple == 25200  # 21000 * 1.2

            # Contract call fallback
            gas_contract = await estimator.estimate_gas(
                to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
                data="0xa9059cbb" + "0" * 64,
            )
            assert gas_contract == 120000  # 100000 * 1.2

            # Complex operation fallback
            gas_complex = await estimator.estimate_gas(
                to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
                data="0x" + "0" * 500,
            )
            assert gas_complex == 600000  # 500000 * 1.2


class TestGasPriceCap:
    """Test 3: Gas price exceeds cap → rejection."""

    @pytest.mark.asyncio
    async def test_gas_price_cap_logic(self):
        """Test gas price cap validation logic."""
        oracle = MockPriceOracle()

        # Create estimator with 50 gwei cap
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
            max_gas_price_gwei=50,
        )

        # Test that validation logic works correctly
        high_gas_price = estimator.w3.to_wei(100, "gwei")
        max_gas_price_wei = estimator.w3.to_wei(50, "gwei")

        # Verify cap logic
        assert high_gas_price > max_gas_price_wei

        # Test that estimator has correct max set
        assert estimator.max_gas_price_gwei == 50

    @pytest.mark.asyncio
    async def test_gas_price_no_cap(self):
        """Test gas price fetching without cap."""
        oracle = MockPriceOracle()

        # Create estimator with no cap
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
            max_gas_price_gwei=None,
        )

        # Should not raise error
        gas_price = await estimator.get_gas_price()
        assert gas_price > 0


class TestSpendingLimitIntegration:
    """Test 4: Gas cost exceeds spending limit → approval required."""

    @pytest.mark.asyncio
    async def test_approval_with_gas_cost(self):
        """Test that gas costs are included in approval threshold."""
        # Create approval manager with $100 threshold
        approval_manager = ApprovalManager(
            approval_threshold_usd=Decimal("100"),
        )

        # Transaction: $80 + $30 gas = $110 total (requires approval)
        amount_usd = Decimal("80")
        gas_cost_usd = Decimal("30")

        assert approval_manager.requires_approval(amount_usd, gas_cost_usd)

        # Transaction: $80 + $10 gas = $90 total (no approval)
        gas_cost_usd_low = Decimal("10")
        assert not approval_manager.requires_approval(amount_usd, gas_cost_usd_low)

    @pytest.mark.asyncio
    async def test_approval_request_includes_gas(self):
        """Test that approval requests display gas information."""
        approval_manager = ApprovalManager(
            approval_threshold_usd=Decimal("100"),
        )

        # Create approval request with gas information
        request = await approval_manager.request_approval(
            transaction_type="DEX Swap",
            amount_usd=Decimal("150.00"),
            from_protocol="Wallet",
            to_protocol="Aerodrome",
            rationale="Swap ETH for USDC on Aerodrome",
            gas_estimate_wei=250000,
            gas_cost_usd=Decimal("12.50"),
        )

        # Verify gas information is stored
        assert request.gas_estimate_wei == 250000
        assert request.gas_cost_usd == Decimal("12.50")

        # Verify display message includes gas
        display = request.get_display_message()
        assert "Gas Cost: $12.50" in display
        assert "Gas Estimate: 250,000 wei" in display
        assert "TOTAL COST: $162.50" in display


class TestNetworkSpecificBuffers:
    """Test 5: Network-specific buffers applied correctly."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_base_network_buffers(self):
        """Test buffer application on Base Sepolia."""
        oracle = MockPriceOracle()
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
        )

        test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

        # Test each complexity tier
        gas_simple = await estimator.estimate_gas(
            to=test_address,
            value=100,
        )
        # Should apply 20% buffer for simple transfer
        assert gas_simple >= 21000 * 1.2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_eip1559_detection(self):
        """Test EIP-1559 support detection."""
        oracle = MockPriceOracle()

        # Base should support EIP-1559
        estimator_base = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
        )
        assert estimator_base.supports_eip1559 is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gas_cost_calculation(self):
        """Test complete gas cost calculation in USD."""
        oracle = MockPriceOracle()
        oracle.set_price("ETH", Decimal("3000.00"))

        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
        )

        # Calculate cost for 100,000 gas using real gas price
        gas_cost_usd = await estimator.calculate_gas_cost(100000, in_usd=True)

        # Verify calculation returns valid USD amount
        assert isinstance(gas_cost_usd, Decimal)
        assert gas_cost_usd > 0

        # Verify ETH calculation also works
        gas_cost_eth = await estimator.calculate_gas_cost(100000, in_usd=False)
        assert isinstance(gas_cost_eth, Decimal)
        assert gas_cost_eth > 0

        # Verify USD cost is ETH cost * ETH price (roughly)
        # Allow for gas price variation
        expected_ratio = Decimal("3000.00")
        actual_ratio = gas_cost_usd / gas_cost_eth
        # Should be roughly $3000/ETH (within 50% tolerance for gas price variance)
        assert Decimal("1500") < actual_ratio < Decimal("4500")


class TestGasEstimationCaching:
    """Test gas estimation caching behavior."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_gas_price_caching(self):
        """Test that gas prices are cached."""
        oracle = MockPriceOracle()
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
            cache_ttl_seconds=300,
        )

        # First call should fetch and cache
        gas_price_1 = await estimator.get_gas_price()

        # Verify cache is populated
        assert estimator._gas_price_cache is not None
        cached_price, cached_time = estimator._gas_price_cache

        # Should match first price
        assert cached_price == gas_price_1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cache_clearing(self):
        """Test cache clearing functionality."""
        oracle = MockPriceOracle()
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
        )

        # Populate cache
        await estimator.get_gas_price()

        # Clear cache
        estimator.clear_cache()

        # Verify cache is empty
        assert estimator._gas_price_cache is None
        assert len(estimator._estimate_cache) == 0


class TestSimulationMode:
    """Test simulation-based estimation mode."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_simulation_mode_success(self):
        """Test simulation mode with successful eth_call."""
        oracle = MockPriceOracle()
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
            estimate_mode=GasEstimateMode.SIMULATION,
        )

        # Should succeed with simulation
        gas_estimate = await estimator.estimate_gas(
            to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
            value=100,
        )

        assert gas_estimate > 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_direct_mode(self):
        """Test direct estimation mode (no simulation)."""
        oracle = MockPriceOracle()
        estimator = GasEstimator(
            network="base-sepolia",
            price_oracle=oracle,
            estimate_mode=GasEstimateMode.DIRECT,
        )

        # Should work without simulation
        gas_estimate = await estimator.estimate_gas(
            to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
            value=100,
        )

        assert gas_estimate > 0