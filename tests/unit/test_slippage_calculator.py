"""Unit tests for slippage calculator edge cases.

Tests cover boundary conditions, extreme values, and error handling.
"""

import pytest
from decimal import Decimal

from src.blockchain.slippage_calculator import SlippageCalculator, PriceDeviationError


class TestSlippageCalculationEdgeCases:
    """Test slippage calculation edge cases."""

    def test_zero_slippage(self):
        """Test 0% slippage (no tolerance)."""
        calc = SlippageCalculator(default_slippage_bps=0)

        min_output = calc.calculate_min_output(Decimal("100"), slippage_bps=0)

        # With 0% slippage, min should equal expected
        assert min_output == Decimal("100")

    def test_100_percent_slippage(self):
        """Test 100% slippage (10000 bps)."""
        calc = SlippageCalculator()

        min_output = calc.calculate_min_output(Decimal("100"), slippage_bps=10000)

        # 100% slippage means minimum is 0
        assert min_output == Decimal("0")

    def test_50_percent_slippage(self):
        """Test 50% slippage (5000 bps)."""
        calc = SlippageCalculator()

        min_output = calc.calculate_min_output(Decimal("100"), slippage_bps=5000)

        # 50% slippage means minimum is 50
        assert min_output == Decimal("50")

    def test_very_small_amount(self):
        """Test slippage with very small amounts."""
        calc = SlippageCalculator(default_slippage_bps=50)

        # 0.000001 with 0.5% slippage
        min_output = calc.calculate_min_output(Decimal("0.000001"), slippage_bps=50)

        expected = Decimal("0.000001") * Decimal("0.995")
        assert abs(min_output - expected) < Decimal("0.0000000001")

    def test_very_large_amount(self):
        """Test slippage with very large amounts."""
        calc = SlippageCalculator(default_slippage_bps=50)

        # 1 billion with 0.5% slippage
        min_output = calc.calculate_min_output(Decimal("1000000000"), slippage_bps=50)

        expected = Decimal("1000000000") * Decimal("0.995")
        assert min_output == expected

    def test_negative_amount_handling(self):
        """Test that negative amounts are handled."""
        calc = SlippageCalculator()

        # Negative amount should still apply slippage formula
        min_output = calc.calculate_min_output(Decimal("-100"), slippage_bps=50)

        # -100 * 0.995 = -99.5
        assert min_output == Decimal("-99.5")

    def test_max_input_zero_slippage(self):
        """Test max input with 0% slippage."""
        calc = SlippageCalculator()

        max_input = calc.calculate_max_input(Decimal("100"), slippage_bps=0)

        assert max_input == Decimal("100")

    def test_max_input_100_percent_slippage(self):
        """Test max input with 100% slippage."""
        calc = SlippageCalculator()

        max_input = calc.calculate_max_input(Decimal("100"), slippage_bps=10000)

        # Max input with 100% slippage is 2x
        assert max_input == Decimal("200")

    def test_basis_point_conversion_exact(self):
        """Test basis point to percentage conversion."""
        calc = SlippageCalculator()

        # 50 bps = 0.5%
        formatted = calc.format_slippage_bps(50)
        assert formatted == "0.50%"

        # 100 bps = 1%
        formatted = calc.format_slippage_bps(100)
        assert formatted == "1.00%"

        # 10000 bps = 100%
        formatted = calc.format_slippage_bps(10000)
        assert formatted == "100.00%"

    def test_calculate_slippage_from_amounts(self):
        """Test reverse calculation of slippage from amounts."""
        calc = SlippageCalculator()

        # 100 expected, 99.5 minimum = 0.5% = 50 bps
        slippage_bps = calc.calculate_slippage_from_amounts(
            Decimal("100"), Decimal("99.5")
        )
        assert slippage_bps == 50

        # 100 expected, 95 minimum = 5% = 500 bps
        slippage_bps = calc.calculate_slippage_from_amounts(
            Decimal("100"), Decimal("95")
        )
        assert slippage_bps == 500

    def test_zero_expected_amount(self):
        """Test slippage calculation with zero expected amount."""
        calc = SlippageCalculator()

        slippage_bps = calc.calculate_slippage_from_amounts(
            Decimal("0"), Decimal("0")
        )
        assert slippage_bps == 0


class TestPriceDeviationBoundaryTesting:
    """Test price deviation validation at boundaries."""

    def test_exactly_2_percent_deviation_passes(self):
        """Test that exactly 2.0% deviation passes."""
        calc = SlippageCalculator(max_price_deviation_percent=Decimal("2.0"))

        # DEX: 3000, Oracle: 2941.18 = exactly 2.0% deviation
        oracle_price = Decimal("3000") / Decimal("1.02")

        # Should not raise
        calc.validate_price_deviation(
            dex_price=Decimal("3000"),
            oracle_price=oracle_price,
        )

    def test_2_01_percent_deviation_fails(self):
        """Test that 2.01% deviation fails."""
        calc = SlippageCalculator(max_price_deviation_percent=Decimal("2.0"))

        # DEX: 3000, Oracle: 2940.45 = 2.01% deviation
        oracle_price = Decimal("3000") / Decimal("1.0201")

        # Should raise
        with pytest.raises(PriceDeviationError):
            calc.validate_price_deviation(
                dex_price=Decimal("3000"),
                oracle_price=oracle_price,
            )

    def test_1_99_percent_deviation_passes(self):
        """Test that 1.99% deviation passes."""
        calc = SlippageCalculator(max_price_deviation_percent=Decimal("2.0"))

        # DEX: 3000, Oracle: 2941.77 = 1.99% deviation
        oracle_price = Decimal("3000") / Decimal("1.0199")

        # Should not raise
        calc.validate_price_deviation(
            dex_price=Decimal("3000"),
            oracle_price=oracle_price,
        )

    def test_zero_deviation(self):
        """Test that 0% deviation (perfect match) passes."""
        calc = SlippageCalculator(max_price_deviation_percent=Decimal("2.0"))

        # Should not raise
        calc.validate_price_deviation(
            dex_price=Decimal("3000"),
            oracle_price=Decimal("3000"),
        )

    def test_negative_deviation_direction(self):
        """Test deviation when DEX price is lower than oracle."""
        calc = SlippageCalculator(max_price_deviation_percent=Decimal("2.0"))

        # DEX lower than oracle by 1.5%
        calc.validate_price_deviation(
            dex_price=Decimal("2955"),  # 1.5% below 3000
            oracle_price=Decimal("3000"),
        )

        # DEX lower than oracle by 2.5% should fail
        with pytest.raises(PriceDeviationError):
            calc.validate_price_deviation(
                dex_price=Decimal("2925"),  # 2.5% below 3000
                oracle_price=Decimal("3000"),
            )

    def test_very_small_prices(self):
        """Test price deviation with very small prices."""
        calc = SlippageCalculator(max_price_deviation_percent=Decimal("2.0"))

        # Should handle small prices correctly
        calc.validate_price_deviation(
            dex_price=Decimal("0.001"),
            oracle_price=Decimal("0.00102"),  # 2% difference
        )

    def test_very_large_prices(self):
        """Test price deviation with very large prices."""
        calc = SlippageCalculator(max_price_deviation_percent=Decimal("2.0"))

        # Should handle large prices correctly
        calc.validate_price_deviation(
            dex_price=Decimal("1000000"),
            oracle_price=Decimal("1020000"),  # 2% difference
        )

    def test_custom_max_deviation(self):
        """Test with custom max deviation parameter."""
        calc = SlippageCalculator(max_price_deviation_percent=Decimal("5.0"))

        # 4% deviation should pass with 5% limit
        calc.validate_price_deviation(
            dex_price=Decimal("3000"),
            oracle_price=Decimal("3120"),  # 4% difference
            max_deviation_percent=Decimal("5.0"),
        )

        # 6% deviation should fail with 5% limit
        with pytest.raises(PriceDeviationError):
            calc.validate_price_deviation(
                dex_price=Decimal("3000"),
                oracle_price=Decimal("3180"),  # 6% difference
                max_deviation_percent=Decimal("5.0"),
            )


class TestPriceImpactCalculation:
    """Test price impact calculation edge cases."""

    def test_zero_impact(self):
        """Test when execution price equals oracle price."""
        calc = SlippageCalculator()

        impact = calc.calculate_price_impact(
            amount_in=Decimal("1"),
            amount_out=Decimal("3000"),
            oracle_price=Decimal("3000"),
        )

        assert impact == Decimal("0")

    def test_positive_impact(self):
        """Test positive price impact (better than oracle)."""
        calc = SlippageCalculator()

        impact = calc.calculate_price_impact(
            amount_in=Decimal("1"),
            amount_out=Decimal("3030"),  # Got more than expected
            oracle_price=Decimal("3000"),
        )

        assert impact == Decimal("1")  # 1% better

    def test_negative_impact(self):
        """Test negative price impact (worse than oracle)."""
        calc = SlippageCalculator()

        impact = calc.calculate_price_impact(
            amount_in=Decimal("1"),
            amount_out=Decimal("2970"),  # Got less than expected
            oracle_price=Decimal("3000"),
        )

        assert impact == Decimal("-1")  # 1% worse

    def test_large_negative_impact(self):
        """Test large negative price impact."""
        calc = SlippageCalculator()

        impact = calc.calculate_price_impact(
            amount_in=Decimal("1"),
            amount_out=Decimal("2400"),  # 20% worse
            oracle_price=Decimal("3000"),
        )

        assert impact == Decimal("-20")


class TestDeadlineManagement:
    """Test deadline calculation and validation."""

    def test_calculate_deadline_default(self):
        """Test default deadline calculation."""
        calc = SlippageCalculator()

        import time
        deadline = calc.calculate_deadline()
        current = int(time.time())

        # Should be approximately 600 seconds from now
        assert 595 < (deadline - current) < 605

    def test_calculate_deadline_custom(self):
        """Test custom deadline calculation."""
        calc = SlippageCalculator()

        import time
        deadline = calc.calculate_deadline(seconds_from_now=300)
        current = int(time.time())

        # Should be approximately 300 seconds from now
        assert 295 < (deadline - current) < 305

    def test_validate_deadline_future(self):
        """Test validating a future deadline."""
        calc = SlippageCalculator()

        import time
        future_deadline = int(time.time()) + 600

        # Should not raise
        calc.validate_deadline(future_deadline)

    def test_validate_deadline_past(self):
        """Test validating a past deadline."""
        calc = SlippageCalculator()

        import time
        past_deadline = int(time.time()) - 10

        # Should raise
        with pytest.raises(ValueError, match="past"):
            calc.validate_deadline(past_deadline)

    def test_validate_deadline_now(self):
        """Test validating deadline at current time."""
        calc = SlippageCalculator()

        import time
        now_deadline = int(time.time())

        # Should raise (not in future)
        with pytest.raises(ValueError):
            calc.validate_deadline(now_deadline)
