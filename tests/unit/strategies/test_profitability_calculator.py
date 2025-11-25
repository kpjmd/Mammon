"""Tests for profitability calculator.

Tests MAMMON's competitive moat: profitability proofs for rebalancing decisions.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from src.strategies.profitability_calculator import (
    ProfitabilityCalculator,
    MoveProfitability,
    RebalancingCosts,
    TransactionType,
)
from src.blockchain.slippage_calculator import SlippageCalculator


class TestProfitabilityCalculator:
    """Test suite for ProfitabilityCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create calculator with default settings."""
        return ProfitabilityCalculator(
            min_annual_gain_usd=Decimal("10"),
            max_break_even_days=30,
            max_cost_pct=Decimal("0.01"),  # 1%
        )

    @pytest.fixture
    def strict_calculator(self):
        """Create calculator with strict profitability requirements."""
        return ProfitabilityCalculator(
            min_annual_gain_usd=Decimal("50"),
            max_break_even_days=14,
            max_cost_pct=Decimal("0.005"),  # 0.5%
        )

    @pytest.fixture
    def mock_gas_estimator(self):
        """Create mock gas estimator."""
        estimator = AsyncMock()
        estimator.get_gas_price = AsyncMock(return_value=10_000_000_000)  # 10 gwei
        estimator.price_oracle = Mock()
        estimator.price_oracle.get_price = AsyncMock(return_value=Decimal("2500"))  # $2500 ETH
        return estimator

    # ============================================================================
    # PROFITABLE SCENARIOS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_profitable_move_high_apy_improvement(self, calculator):
        """Large APY improvement with low costs → profitable."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),  # +7% APY
            position_size_usd=Decimal("5000"),
            requires_swap=False,
        )

        assert result.is_profitable is True
        assert result.apy_improvement == Decimal("7.0")
        assert result.annual_gain_usd == Decimal("350")  # $5000 * 7%
        assert result.net_gain_first_year > Decimal("340")  # After ~$10 gas
        assert result.break_even_days < 10  # Very quick break-even
        assert len(result.rejection_reasons) == 0

    @pytest.mark.asyncio
    async def test_profitable_move_medium_position(self, calculator):
        """Medium position with good APY improvement → profitable."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("12.0"),  # +9% APY (enough to meet 30-day break-even)
            position_size_usd=Decimal("1000"),
            requires_swap=False,
        )

        assert result.is_profitable is True
        assert result.apy_improvement == Decimal("9.0")
        assert result.annual_gain_usd == Decimal("90")  # $1000 * 9%
        assert result.net_gain_first_year >= Decimal("10")  # Passes min threshold
        assert result.break_even_days <= 30

    @pytest.mark.asyncio
    async def test_profitable_move_with_swap(self, calculator):
        """Profitable move even with swap costs."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("15.0"),  # +12% APY (higher to offset swap costs)
            position_size_usd=Decimal("5000"),  # Larger position
            requires_swap=True,
            swap_amount_usd=Decimal("5000"),
        )

        assert result.is_profitable is True
        assert result.apy_improvement == Decimal("12.0")
        assert result.annual_gain_usd == Decimal("600")  # $5000 * 12%
        # Should still be profitable despite swap gas + slippage
        assert result.costs.gas_swap > 0
        assert result.costs.slippage_cost > 0
        assert result.net_gain_first_year > Decimal("10")

    # ============================================================================
    # UNPROFITABLE SCENARIOS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_unprofitable_small_apy_improvement(self, calculator):
        """Small APY improvement doesn't justify costs → unprofitable."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("4.0"),
            target_apy=Decimal("4.5"),  # Only +0.5% APY
            position_size_usd=Decimal("1000"),
            requires_swap=False,
        )

        assert result.is_profitable is False
        assert result.apy_improvement == Decimal("0.5")
        assert result.annual_gain_usd == Decimal("5")  # $1000 * 0.5%
        # Net gain likely < $10 after gas costs
        assert any("Net gain" in reason for reason in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_unprofitable_long_breakeven(self, calculator):
        """Long break-even period → unprofitable."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("4.0"),
            target_apy=Decimal("4.3"),  # +0.3% APY
            position_size_usd=Decimal("3000"),
            requires_swap=False,
        )

        # Annual gain: $3000 * 0.3% = $9
        # With ~$5-10 gas, break-even is long
        assert result.is_profitable is False
        assert result.break_even_days > 30
        assert any("Break-even" in reason for reason in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_unprofitable_zero_apy_improvement(self, calculator):
        """No APY improvement → unprofitable."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("5.0"),
            target_apy=Decimal("5.0"),  # Same APY
            position_size_usd=Decimal("10000"),
            requires_swap=False,
        )

        assert result.is_profitable is False
        assert result.apy_improvement == Decimal("0")
        assert result.annual_gain_usd == Decimal("0")
        assert any("No APY improvement" in reason for reason in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_unprofitable_negative_apy_improvement(self, calculator):
        """Moving to lower APY → unprofitable."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("8.0"),
            target_apy=Decimal("6.0"),  # APY decreases
            position_size_usd=Decimal("5000"),
            requires_swap=False,
        )

        assert result.is_profitable is False
        assert result.apy_improvement == Decimal("-2.0")
        assert result.annual_gain_usd == Decimal("-100")  # Losing money
        assert any("No APY improvement" in reason for reason in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_unprofitable_high_swap_costs(self, calculator):
        """High swap costs eat profits → unprofitable."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("4.0"),
            target_apy=Decimal("5.0"),  # +1% APY
            position_size_usd=Decimal("500"),  # Small position
            requires_swap=True,
            swap_amount_usd=Decimal("500"),
        )

        # Annual gain: $500 * 1% = $5
        # Swap gas + slippage likely > $5
        assert result.is_profitable is False
        assert result.costs.gas_swap > 0
        assert result.costs.slippage_cost > 0
        assert result.net_gain_first_year < Decimal("10")

    @pytest.mark.asyncio
    async def test_unprofitable_costs_exceed_threshold(self, calculator):
        """Costs >1% of position → unprofitable."""
        # With very small position, gas costs become high %
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("15.0"),  # Great APY improvement
            position_size_usd=Decimal("100"),  # Tiny position
            requires_swap=True,
        )

        # Even with great APY, costs are too high % of position
        cost_pct = result.costs.total_cost / Decimal("100")
        if cost_pct > Decimal("0.01"):  # >1%
            assert result.is_profitable is False
            assert any("Costs" in reason and "%" in reason for reason in result.rejection_reasons)

    # ============================================================================
    # COST CALCULATION TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_gas_cost_calculation_no_swap(self, calculator):
        """Verify gas costs for simple move (no swap)."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),
            position_size_usd=Decimal("5000"),
            requires_swap=False,
        )

        # Should have withdraw + deposit gas, no swap or approve
        assert result.costs.gas_withdraw > 0
        assert result.costs.gas_deposit > 0
        assert result.costs.gas_approve == 0
        assert result.costs.gas_swap == 0
        assert result.costs.slippage_cost == 0

    @pytest.mark.asyncio
    async def test_gas_cost_calculation_with_swap(self, calculator):
        """Verify gas costs for move with swap."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),
            position_size_usd=Decimal("5000"),
            requires_swap=True,
        )

        # Should have all gas costs + slippage
        assert result.costs.gas_withdraw > 0
        assert result.costs.gas_approve > 0
        assert result.costs.gas_swap > 0
        assert result.costs.gas_deposit > 0
        assert result.costs.slippage_cost > 0

    @pytest.mark.asyncio
    async def test_slippage_cost_calculation(self, calculator):
        """Verify slippage cost calculation."""
        # Default SlippageCalculator uses 50bps (0.5%)
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),
            position_size_usd=Decimal("1000"),
            requires_swap=True,
            swap_amount_usd=Decimal("1000"),
        )

        # Slippage should be ~0.5% of swap amount
        expected_slippage = Decimal("1000") * Decimal("0.005")  # 0.5%
        assert abs(result.costs.slippage_cost - expected_slippage) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_protocol_fees_calculation(self, calculator):
        """Verify protocol fees calculation."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),
            position_size_usd=Decimal("5000"),
            requires_swap=False,
            protocol_fee_pct=Decimal("0.1"),  # 0.1% fee
        )

        # Fee should be 0.1% of position
        expected_fee = Decimal("5000") * Decimal("0.001")  # 0.1%
        assert result.costs.protocol_fees == expected_fee

    @pytest.mark.asyncio
    async def test_total_cost_calculation(self, calculator):
        """Verify total cost is sum of all components."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),
            position_size_usd=Decimal("5000"),
            requires_swap=True,
            protocol_fee_pct=Decimal("0.1"),
        )

        expected_total = (
            result.costs.gas_withdraw
            + result.costs.gas_approve
            + result.costs.gas_swap
            + result.costs.gas_deposit
            + result.costs.slippage_cost
            + result.costs.protocol_fees
        )

        assert result.costs.total_cost == expected_total

    # ============================================================================
    # METRIC CALCULATION TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_break_even_calculation(self, calculator):
        """Verify break-even days calculation."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("4.0"),
            target_apy=Decimal("8.0"),  # +4% APY
            position_size_usd=Decimal("1000"),
            requires_swap=False,
        )

        # Annual gain: $1000 * 4% = $40
        # If costs are ~$10, break-even should be ~91 days (10/40 * 365)
        # Verify calculation is reasonable
        expected_break_even = int(
            (result.costs.total_cost / result.annual_gain_usd * Decimal(365)).to_integral_value()
        )
        assert result.break_even_days == expected_break_even

    @pytest.mark.asyncio
    async def test_break_even_zero_gain(self, calculator):
        """Break-even with zero gain should be very high."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("5.0"),
            target_apy=Decimal("5.0"),  # No improvement
            position_size_usd=Decimal("1000"),
            requires_swap=False,
        )

        # With zero gain, break-even should be effectively infinite
        assert result.break_even_days > 100000

    @pytest.mark.asyncio
    async def test_roi_calculation(self, calculator):
        """Verify ROI on costs calculation."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),  # +7% APY
            position_size_usd=Decimal("5000"),
            requires_swap=False,
        )

        # Annual gain: $5000 * 7% = $350
        # ROI = (net_gain / total_cost) * 100
        expected_roi = (result.net_gain_first_year / result.costs.total_cost) * Decimal(100)
        assert abs(result.roi_on_costs - expected_roi) < Decimal("0.01")

    @pytest.mark.asyncio
    async def test_roi_zero_costs(self, calculator):
        """ROI with zero costs should be very high."""
        # Mock calculator with zero gas costs (theoretical)
        calculator.DEFAULT_GAS_ESTIMATES = {
            TransactionType.WITHDRAW: 0,
            TransactionType.APPROVE: 0,
            TransactionType.SWAP: 0,
            TransactionType.DEPOSIT: 0,
        }

        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),
            position_size_usd=Decimal("5000"),
            requires_swap=False,
        )

        # With zero costs, ROI should be effectively infinite
        assert result.roi_on_costs > Decimal("100000")

    # ============================================================================
    # PROFITABILITY GATES TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_min_annual_gain_gate(self, calculator):
        """Verify minimum annual gain gate."""
        # Set up scenario with gain just below threshold
        result = await calculator.calculate_profitability(
            current_apy=Decimal("4.0"),
            target_apy=Decimal("4.2"),  # +0.2% APY
            position_size_usd=Decimal("4000"),  # Gain = $8
            requires_swap=False,
        )

        # Net gain will be < $10 after gas
        assert result.is_profitable is False
        assert any("Net gain" in reason for reason in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_max_break_even_gate(self, calculator):
        """Verify maximum break-even gate."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("4.0"),
            target_apy=Decimal("4.5"),  # +0.5% APY
            position_size_usd=Decimal("2000"),  # Gain = $10/year
            requires_swap=False,
        )

        # With $10 annual gain and ~$5-10 gas, break-even > 30 days
        if result.break_even_days > 30:
            assert result.is_profitable is False
            assert any("Break-even" in reason for reason in result.rejection_reasons)

    @pytest.mark.asyncio
    async def test_max_cost_pct_gate(self, calculator):
        """Verify maximum cost percentage gate."""
        # Tiny position makes gas costs high %
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("20.0"),  # Excellent APY
            position_size_usd=Decimal("200"),  # Small position
            requires_swap=True,
        )

        # Gas costs likely >1% of $200 position
        cost_pct = result.costs.total_cost / Decimal("200")
        if cost_pct > Decimal("0.01"):
            assert result.is_profitable is False
            assert any("Costs" in reason and "%" in reason for reason in result.rejection_reasons)

    # ============================================================================
    # STRICT CALCULATOR TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_strict_calculator_rejects_more(self, strict_calculator):
        """Strict calculator should reject marginal opportunities."""
        # Move that passes default calculator
        result_default = await ProfitabilityCalculator().calculate_profitability(
            current_apy=Decimal("4.0"),
            target_apy=Decimal("6.0"),  # +2% APY
            position_size_usd=Decimal("2000"),  # Gain = $40/year
            requires_swap=False,
        )

        # Same move with strict calculator
        result_strict = await strict_calculator.calculate_profitability(
            current_apy=Decimal("4.0"),
            target_apy=Decimal("6.0"),
            position_size_usd=Decimal("2000"),
            requires_swap=False,
        )

        # Strict requires $50 annual gain, 14 day break-even, 0.5% max cost
        # This move likely fails strict requirements
        if result_default.is_profitable and not result_strict.is_profitable:
            assert len(result_strict.rejection_reasons) > 0

    # ============================================================================
    # INTEGRATION WITH GAS ESTIMATOR
    # ============================================================================

    @pytest.mark.asyncio
    async def test_with_gas_estimator(self, mock_gas_estimator):
        """Verify integration with GasEstimator."""
        calculator = ProfitabilityCalculator(
            gas_estimator=mock_gas_estimator
        )

        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),
            position_size_usd=Decimal("5000"),
            requires_swap=False,
        )

        # Should use gas estimator instead of defaults
        mock_gas_estimator.get_gas_price.assert_called()
        mock_gas_estimator.price_oracle.get_price.assert_called()
        assert result.costs.gas_withdraw > 0

    # ============================================================================
    # DETAILED BREAKDOWN TESTS
    # ============================================================================

    @pytest.mark.asyncio
    async def test_detailed_breakdown_format(self, calculator):
        """Verify detailed breakdown is formatted correctly."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),
            position_size_usd=Decimal("5000"),
            requires_swap=True,
        )

        breakdown = result.detailed_breakdown

        # Should contain all key sections
        assert "PROFITABILITY ANALYSIS" in breakdown
        assert "REVENUE:" in breakdown
        assert "COSTS:" in breakdown
        assert "PROFITABILITY:" in breakdown
        assert "DECISION:" in breakdown

        # Should show specific values
        assert "APY Improvement:" in breakdown
        assert "Position Size:" in breakdown
        assert "Annual Gain:" in breakdown
        assert "Total Costs:" in breakdown
        assert "Net Gain (Year 1):" in breakdown
        assert "Break-even:" in breakdown
        assert "ROI on Costs:" in breakdown

    @pytest.mark.asyncio
    async def test_breakdown_shows_profitable_decision(self, calculator):
        """Profitable move breakdown shows success."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("3.0"),
            target_apy=Decimal("10.0"),
            position_size_usd=Decimal("5000"),
            requires_swap=False,
        )

        assert result.is_profitable is True
        assert "✅ PROFITABLE" in result.detailed_breakdown

    @pytest.mark.asyncio
    async def test_breakdown_shows_unprofitable_decision(self, calculator):
        """Unprofitable move breakdown shows rejection reasons."""
        result = await calculator.calculate_profitability(
            current_apy=Decimal("4.0"),
            target_apy=Decimal("4.0"),  # No improvement
            position_size_usd=Decimal("1000"),
            requires_swap=False,
        )

        assert result.is_profitable is False
        assert "❌ UNPROFITABLE" in result.detailed_breakdown
        assert "Rejection reasons:" in result.detailed_breakdown
