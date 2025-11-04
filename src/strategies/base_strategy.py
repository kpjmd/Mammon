"""Abstract base class for yield optimization strategies.

This module defines the interface that all yield strategies must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
from decimal import Decimal


class RebalanceRecommendation:
    """Represents a rebalancing recommendation.

    Attributes:
        from_protocol: Source protocol (None for new allocation)
        to_protocol: Target protocol
        token: Token to rebalance
        amount: Amount to move
        expected_apy: Expected APY in target
        reason: Human-readable explanation
        confidence: Confidence score (0-100)
    """

    def __init__(
        self,
        from_protocol: str | None,
        to_protocol: str,
        token: str,
        amount: Decimal,
        expected_apy: Decimal,
        reason: str,
        confidence: int,
    ) -> None:
        """Initialize a rebalance recommendation.

        Args:
            from_protocol: Source protocol or None
            to_protocol: Target protocol
            token: Token symbol
            amount: Amount to rebalance
            expected_apy: Expected APY
            reason: Explanation
            confidence: Confidence (0-100)
        """
        self.from_protocol = from_protocol
        self.to_protocol = to_protocol
        self.token = token
        self.amount = amount
        self.expected_apy = expected_apy
        self.reason = reason
        self.confidence = confidence


class BaseStrategy(ABC):
    """Abstract base class for yield optimization strategies.

    All strategies must inherit from this class and implement
    the abstract methods for consistent behavior.

    Attributes:
        name: Strategy name
        config: Strategy configuration
    """

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        """Initialize the strategy.

        Args:
            name: Strategy name
            config: Strategy configuration
        """
        self.name = name
        self.config = config

    @abstractmethod
    async def analyze_opportunities(
        self,
        current_positions: Dict[str, Decimal],
        available_yields: Dict[str, Decimal],
    ) -> List[RebalanceRecommendation]:
        """Analyze yield opportunities and generate recommendations.

        Args:
            current_positions: Current positions (protocol->amount)
            available_yields: Available yields (protocol->apy)

        Returns:
            List of rebalance recommendations
        """
        pass

    @abstractmethod
    def calculate_optimal_allocation(
        self,
        total_capital: Decimal,
        opportunities: Dict[str, Decimal],
    ) -> Dict[str, Decimal]:
        """Calculate optimal capital allocation across opportunities.

        Args:
            total_capital: Total capital to allocate
            opportunities: Available opportunities (protocol->apy)

        Returns:
            Dict mapping protocol to allocation amount
        """
        pass

    @abstractmethod
    def should_rebalance(
        self,
        current_apy: Decimal,
        target_apy: Decimal,
        gas_cost: Decimal,
        amount: Decimal,
    ) -> bool:
        """Determine if rebalancing is worthwhile.

        Args:
            current_apy: Current position APY
            target_apy: Target position APY
            gas_cost: Estimated gas cost in USD
            amount: Amount to rebalance

        Returns:
            True if rebalancing is recommended
        """
        pass
