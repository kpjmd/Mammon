"""Abstract base interface for DeFi protocol integrations.

This module defines the abstract interface that all protocol integrations
must implement, ensuring consistent interaction patterns across protocols.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from decimal import Decimal


class ProtocolPool:
    """Represents a liquidity pool or vault in a DeFi protocol.

    Attributes:
        pool_id: Unique identifier for the pool
        name: Human-readable pool name
        tokens: List of token symbols in the pool
        apy: Current annual percentage yield
        tvl: Total value locked in USD
        metadata: Additional protocol-specific metadata
    """

    def __init__(
        self,
        pool_id: str,
        name: str,
        tokens: List[str],
        apy: Decimal,
        tvl: Decimal,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize a protocol pool.

        Args:
            pool_id: Unique pool identifier
            name: Pool name
            tokens: Token symbols
            apy: Annual percentage yield
            tvl: Total value locked
            metadata: Additional metadata
        """
        self.pool_id = pool_id
        self.name = name
        self.tokens = tokens
        self.apy = apy
        self.tvl = tvl
        self.metadata = metadata or {}


class BaseProtocol(ABC):
    """Abstract base class for DeFi protocol integrations.

    All protocol integrations (Aerodrome, Morpho, etc.) must inherit
    from this class and implement all abstract methods.

    Attributes:
        name: Protocol name
        chain: Blockchain network
        config: Protocol-specific configuration
    """

    def __init__(self, name: str, chain: str, config: Dict[str, Any]) -> None:
        """Initialize the protocol integration.

        Args:
            name: Protocol name
            chain: Blockchain network (e.g., 'base')
            config: Configuration dictionary
        """
        self.name = name
        self.chain = chain
        self.config = config

    @abstractmethod
    async def get_pools(self) -> List[ProtocolPool]:
        """Fetch all available pools/vaults from the protocol.

        Returns:
            List of protocol pools
        """
        pass

    @abstractmethod
    async def get_pool_apy(self, pool_id: str) -> Decimal:
        """Get current APY for a specific pool.

        Args:
            pool_id: Pool identifier

        Returns:
            Current APY as decimal (e.g., 0.05 for 5%)
        """
        pass

    @abstractmethod
    async def deposit(
        self,
        pool_id: str,
        token: str,
        amount: Decimal,
    ) -> str:
        """Deposit tokens into a protocol pool.

        Args:
            pool_id: Target pool identifier
            token: Token symbol to deposit
            amount: Amount to deposit

        Returns:
            Transaction hash
        """
        pass

    @abstractmethod
    async def withdraw(
        self,
        pool_id: str,
        token: str,
        amount: Decimal,
    ) -> str:
        """Withdraw tokens from a protocol pool.

        Args:
            pool_id: Source pool identifier
            token: Token symbol to withdraw
            amount: Amount to withdraw

        Returns:
            Transaction hash
        """
        pass

    @abstractmethod
    async def get_user_balance(self, pool_id: str, user_address: str) -> Decimal:
        """Get user's balance in a specific pool.

        Args:
            pool_id: Pool identifier
            user_address: User's wallet address

        Returns:
            User's balance in pool tokens
        """
        pass

    @abstractmethod
    async def estimate_gas(self, operation: str, params: Dict[str, Any]) -> int:
        """Estimate gas cost for an operation.

        Args:
            operation: Operation type (deposit/withdraw)
            params: Operation parameters

        Returns:
            Estimated gas units
        """
        pass

    async def health_check(self) -> bool:
        """Check if protocol API/contract is accessible.

        Returns:
            True if protocol is accessible, False otherwise
        """
        raise NotImplementedError("Health check not yet implemented")
