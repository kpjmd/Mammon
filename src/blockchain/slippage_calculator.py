"""Slippage protection and price validation utilities.

This module provides slippage calculation, price deviation checks,
and deadline management for swap protection.
"""

from decimal import Decimal
from typing import Optional
import time

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PriceDeviationError(Exception):
    """Raised when price deviates too much from oracle."""

    pass


class SlippageCalculator:
    """Calculator for slippage protection and price validation.

    Provides utilities for:
    - Calculating minimum output amounts with slippage tolerance
    - Validating price impact
    - Cross-checking prices between DEX and oracles
    - Managing transaction deadlines

    Attributes:
        default_slippage_bps: Default slippage tolerance in basis points
        max_price_deviation_percent: Maximum allowed price deviation from oracle
    """

    def __init__(
        self,
        default_slippage_bps: int = 50,
        max_price_deviation_percent: Decimal = Decimal("2.0"),
    ):
        """Initialize slippage calculator.

        Args:
            default_slippage_bps: Default slippage in basis points (50 = 0.5%)
            max_price_deviation_percent: Max price deviation from oracle (2.0 = 2%)
        """
        self.default_slippage_bps = default_slippage_bps
        self.max_price_deviation_percent = max_price_deviation_percent

        logger.info(
            f"Initialized SlippageCalculator: "
            f"slippage={default_slippage_bps}bps, "
            f"max_deviation={max_price_deviation_percent}%"
        )

    def calculate_min_output(
        self,
        expected_amount: Decimal,
        slippage_bps: Optional[int] = None,
    ) -> Decimal:
        """Calculate minimum output amount with slippage protection.

        Args:
            expected_amount: Expected output amount
            slippage_bps: Slippage tolerance in basis points (None = use default)

        Returns:
            Minimum acceptable output amount

        Example:
            >>> calc = SlippageCalculator()
            >>> calc.calculate_min_output(Decimal("100"), 50)  # 0.5% slippage
            Decimal('99.5')
        """
        slippage = slippage_bps if slippage_bps is not None else self.default_slippage_bps

        # Convert basis points to percentage (50 bps = 0.5%)
        slippage_percent = Decimal(slippage) / Decimal(10000)

        # Calculate minimum: expected * (1 - slippage)
        min_output = expected_amount * (Decimal(1) - slippage_percent)

        logger.debug(
            f"Slippage protection: expected={expected_amount}, "
            f"slippage={slippage}bps, min={min_output}"
        )

        return min_output

    def calculate_max_input(
        self,
        expected_amount: Decimal,
        slippage_bps: Optional[int] = None,
    ) -> Decimal:
        """Calculate maximum input amount with slippage protection.

        Used for exact output swaps where you want to limit input.

        Args:
            expected_amount: Expected input amount
            slippage_bps: Slippage tolerance in basis points (None = use default)

        Returns:
            Maximum acceptable input amount

        Example:
            >>> calc = SlippageCalculator()
            >>> calc.calculate_max_input(Decimal("100"), 50)  # 0.5% slippage
            Decimal('100.5')
        """
        slippage = slippage_bps if slippage_bps is not None else self.default_slippage_bps

        # Convert basis points to percentage
        slippage_percent = Decimal(slippage) / Decimal(10000)

        # Calculate maximum: expected * (1 + slippage)
        max_input = expected_amount * (Decimal(1) + slippage_percent)

        logger.debug(
            f"Slippage protection (input): expected={expected_amount}, "
            f"slippage={slippage}bps, max={max_input}"
        )

        return max_input

    def validate_price_deviation(
        self,
        dex_price: Decimal,
        oracle_price: Decimal,
        max_deviation_percent: Optional[Decimal] = None,
    ) -> None:
        """Validate that DEX price doesn't deviate too much from oracle.

        This protects against:
        - Oracle manipulation
        - Sandwich attacks
        - Low liquidity pools
        - Stale oracle prices

        Args:
            dex_price: Price from DEX quote
            oracle_price: Price from oracle (e.g., Chainlink)
            max_deviation_percent: Max allowed deviation (None = use default)

        Raises:
            PriceDeviationError: If deviation exceeds maximum

        Example:
            >>> calc = SlippageCalculator()
            >>> calc.validate_price_deviation(
            ...     Decimal("3200"),  # DEX: $3200/ETH
            ...     Decimal("3198"),  # Oracle: $3198/ETH
            ... )
            # No error - within 2% tolerance
        """
        max_deviation = (
            max_deviation_percent
            if max_deviation_percent is not None
            else self.max_price_deviation_percent
        )

        # Calculate deviation percentage
        deviation = abs(dex_price - oracle_price) / oracle_price * Decimal(100)

        logger.info(
            f"Price check: DEX={dex_price:.2f}, Oracle={oracle_price:.2f}, "
            f"Deviation={deviation:.4f}%"
        )

        if deviation > max_deviation:
            error_msg = (
                f"Price deviation too high: {deviation:.4f}% "
                f"(max: {max_deviation}%). "
                f"DEX price: {dex_price:.2f}, Oracle price: {oracle_price:.2f}"
            )
            logger.error(error_msg)
            raise PriceDeviationError(error_msg)

        logger.info(f"✅ Price deviation check passed: {deviation:.4f}% < {max_deviation}%")

    def calculate_price_impact(
        self,
        amount_in: Decimal,
        amount_out: Decimal,
        oracle_price: Decimal,
    ) -> Decimal:
        """Calculate price impact of a swap.

        Args:
            amount_in: Input amount
            amount_out: Output amount
            oracle_price: Reference price from oracle

        Returns:
            Price impact as percentage

        Example:
            >>> calc = SlippageCalculator()
            >>> calc.calculate_price_impact(
            ...     Decimal("1"),      # 1 ETH in
            ...     Decimal("3180"),   # 3180 USDC out
            ...     Decimal("3200"),   # Oracle: $3200/ETH
            ... )
            Decimal('0.625')  # 0.625% negative impact
        """
        # Execution price
        execution_price = amount_out / amount_in

        # Price impact = (execution - oracle) / oracle * 100
        impact = (execution_price - oracle_price) / oracle_price * Decimal(100)

        logger.debug(
            f"Price impact: {impact:.4f}% "
            f"(execution: {execution_price:.2f}, oracle: {oracle_price:.2f})"
        )

        return impact

    def calculate_deadline(self, seconds_from_now: int = 600) -> int:
        """Calculate transaction deadline timestamp.

        Args:
            seconds_from_now: Seconds from now (default: 10 minutes)

        Returns:
            Unix timestamp for deadline

        Example:
            >>> calc = SlippageCalculator()
            >>> deadline = calc.calculate_deadline(300)  # 5 minutes
            >>> deadline > int(time.time())
            True
        """
        deadline = int(time.time()) + seconds_from_now

        logger.debug(
            f"Calculated deadline: {deadline} "
            f"(+{seconds_from_now}s from {int(time.time())})"
        )

        return deadline

    def validate_deadline(self, deadline: int) -> None:
        """Validate that deadline is in the future.

        Args:
            deadline: Unix timestamp

        Raises:
            ValueError: If deadline is in the past
        """
        current_time = int(time.time())

        if deadline <= current_time:
            raise ValueError(
                f"Deadline {deadline} is in the past (current: {current_time})"
            )

        time_remaining = deadline - current_time
        logger.debug(f"Deadline valid: {time_remaining}s remaining")

    def format_slippage_bps(self, slippage_bps: int) -> str:
        """Format slippage basis points as human-readable percentage.

        Args:
            slippage_bps: Slippage in basis points

        Returns:
            Formatted string (e.g., "0.5%")

        Example:
            >>> calc = SlippageCalculator()
            >>> calc.format_slippage_bps(50)
            '0.50%'
            >>> calc.format_slippage_bps(100)
            '1.00%'
        """
        percentage = Decimal(slippage_bps) / Decimal(100)
        return f"{percentage:.2f}%"

    def calculate_slippage_from_amounts(
        self,
        expected_amount: Decimal,
        minimum_amount: Decimal,
    ) -> int:
        """Calculate slippage in basis points from amounts.

        Args:
            expected_amount: Expected amount
            minimum_amount: Minimum acceptable amount

        Returns:
            Slippage in basis points

        Example:
            >>> calc = SlippageCalculator()
            >>> calc.calculate_slippage_from_amounts(
            ...     Decimal("100"),
            ...     Decimal("99.5")
            ... )
            50  # 0.5% = 50 bps
        """
        if expected_amount == 0:
            return 0

        # slippage = (expected - minimum) / expected * 10000
        slippage_bps = int(
            (expected_amount - minimum_amount) / expected_amount * Decimal(10000)
        )

        logger.debug(
            f"Calculated slippage: {slippage_bps}bps "
            f"(expected={expected_amount}, min={minimum_amount})"
        )

        return slippage_bps
