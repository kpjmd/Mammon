"""Mock protocol simulator for testing rebalance workflows without real transactions.

This module provides a safe fallback for testing the complete rebalance workflow
when testnet protocols are unavailable or for development/testing purposes.
"""

from typing import Any, Dict
from decimal import Decimal
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MockProtocolSimulator:
    """Simulates protocol transactions for testing workflows.

    This class mimics the interface of ProtocolActionExecutor but doesn't
    execute real transactions. Useful for:
    - Testing workflow logic without blockchain
    - Development when testnet is unavailable
    - Integration tests with predictable results

    All methods return mock transaction receipts with realistic gas estimates.
    """

    def __init__(self) -> None:
        """Initialize mock protocol simulator."""
        logger.info("MockProtocolSimulator initialized (safe testing mode)")

    async def execute_approve(
        self,
        token: str,
        spender: str,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """Simulate ERC20 token approval.

        Args:
            token: Token symbol
            spender: Spender address
            amount: Amount to approve

        Returns:
            Mock transaction receipt
        """
        logger.info(f"[MOCK] Approving {amount} {token} for {spender[:10]}...")

        return {
            "success": True,
            "tx_hash": f"0xmock_approve_{token}_{spender[:6]}",
            "gas_used": 50000,
            "dry_run": False,
            "simulated": True,
        }

    async def execute_withdraw(
        self,
        protocol_name: str,
        token: str,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """Simulate protocol withdrawal.

        Args:
            protocol_name: Protocol name
            token: Token symbol
            amount: Amount to withdraw

        Returns:
            Mock transaction receipt
        """
        logger.info(f"[MOCK] Withdrawing {amount} {token} from {protocol_name}...")

        # Realistic gas estimates for different protocols
        gas_estimates = {
            "Aave V3": 150000,
            "Morpho": 120000,
            "Moonwell": 140000,
            "Aerodrome": 110000,
        }

        gas_used = gas_estimates.get(protocol_name, 130000)

        return {
            "success": True,
            "tx_hash": f"0xmock_withdraw_{protocol_name.replace(' ', '_').lower()}_{token}",
            "gas_used": gas_used,
            "protocol": protocol_name,
            "action": "withdraw",
            "dry_run": False,
            "simulated": True,
        }

    async def execute_deposit(
        self,
        protocol_name: str,
        token: str,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """Simulate protocol deposit.

        Args:
            protocol_name: Protocol name
            token: Token symbol
            amount: Amount to deposit

        Returns:
            Mock transaction receipt
        """
        logger.info(f"[MOCK] Depositing {amount} {token} to {protocol_name}...")

        # Realistic gas estimates for different protocols
        gas_estimates = {
            "Aave V3": 120000,
            "Morpho": 100000,
            "Moonwell": 115000,
            "Aerodrome": 95000,
        }

        gas_used = gas_estimates.get(protocol_name, 110000)

        return {
            "success": True,
            "tx_hash": f"0xmock_deposit_{protocol_name.replace(' ', '_').lower()}_{token}",
            "gas_used": gas_used,
            "protocol": protocol_name,
            "action": "deposit",
            "dry_run": False,
            "simulated": True,
        }

    async def get_token_balance(
        self,
        token: str,
        address: str = None,
    ) -> Decimal:
        """Simulate token balance check.

        Args:
            token: Token symbol
            address: Address to check (unused in mock)

        Returns:
            Mock balance (1000.0 for all tokens)
        """
        # Return a constant balance for testing
        return Decimal("1000.0")
