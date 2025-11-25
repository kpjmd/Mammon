"""Chain monitoring for Base network state and events.

This module monitors blockchain state, events, and provides
real-time updates on positions and transactions.
"""

from typing import Any, Callable, Dict, List, Optional
from decimal import Decimal
import asyncio
import time
from src.utils.logger import get_logger
from src.utils.web3_provider import get_web3

logger = get_logger(__name__)


class ChainEvent:
    """Represents a blockchain event.

    Attributes:
        event_type: Type of event (Transfer, Deposit, etc.)
        contract_address: Contract that emitted the event
        block_number: Block number
        transaction_hash: Transaction hash
        data: Event data
    """

    def __init__(
        self,
        event_type: str,
        contract_address: str,
        block_number: int,
        transaction_hash: str,
        data: Dict[str, Any],
    ) -> None:
        """Initialize a chain event.

        Args:
            event_type: Event type
            contract_address: Emitting contract address
            block_number: Block number
            transaction_hash: Transaction hash
            data: Event data
        """
        self.event_type = event_type
        self.contract_address = contract_address
        self.block_number = block_number
        self.transaction_hash = transaction_hash
        self.data = data


class ChainMonitor:
    """Monitors Base network state and events.

    Watches for relevant events, monitors gas prices, and tracks
    wallet positions across protocols.

    Attributes:
        config: Monitoring configuration
        wallet_address: Address to monitor
        network: Network ID (e.g., "base-sepolia")
        listeners: Event listeners
        monitoring_active: Whether monitoring is active
    """

    def __init__(self, config: Dict[str, Any], wallet_address: str) -> None:
        """Initialize the chain monitor.

        Args:
            config: Monitoring configuration
            wallet_address: Wallet address to monitor
        """
        self.config = config
        self.wallet_address = wallet_address
        self.network = config.get("network", "base-sepolia")
        self.listeners: List[Callable[[ChainEvent], None]] = []
        self.monitoring_active = False

    async def start_monitoring(self) -> None:
        """Start monitoring the blockchain."""
        self.monitoring_active = True
        logger.info(f"Started monitoring {self.network} for {self.wallet_address}")

    async def stop_monitoring(self) -> None:
        """Stop monitoring the blockchain."""
        self.monitoring_active = False
        logger.info(f"Stopped monitoring {self.network}")

    async def get_current_gas_price(self) -> int:
        """Get current gas price on Base (EIP-1559).

        Returns:
            Current max fee per gas in wei
        """
        try:
            w3 = get_web3(self.network)
            latest_block = w3.eth.get_block("latest")
            base_fee = latest_block.get("baseFeePerGas", 0)

            # Add 1 gwei priority fee for fast confirmation
            max_priority_fee = w3.to_wei(1, "gwei")
            max_fee_per_gas = (base_fee * 2) + max_priority_fee

            logger.debug(
                f"Current gas price: base={base_fee}, max={max_fee_per_gas}"
            )
            return max_fee_per_gas

        except Exception as e:
            logger.error(f"Failed to get gas price: {e}")
            # Return reasonable default (50 gwei)
            return 50_000_000_000

    async def get_block_number(self) -> int:
        """Get current block number.

        Returns:
            Current block number
        """
        try:
            w3 = get_web3(self.network)
            block_number = w3.eth.block_number
            logger.debug(f"Current block number: {block_number}")
            return block_number

        except Exception as e:
            logger.error(f"Failed to get block number: {e}")
            raise

    async def wait_for_confirmation(
        self,
        tx_hash: str,
        confirmations: int = 2,
        timeout: int = 300,
    ) -> bool:
        """Wait for transaction confirmation.

        Polls the network for transaction receipt and waits for
        specified number of block confirmations.

        Args:
            tx_hash: Transaction hash
            confirmations: Number of confirmations to wait for
            timeout: Timeout in seconds

        Returns:
            True if confirmed, False if timeout or failed
        """
        try:
            w3 = get_web3(self.network)
            start_time = time.time()
            poll_interval = 2  # seconds

            logger.info(
                f"Waiting for {confirmations} confirmations of {tx_hash}..."
            )

            while (time.time() - start_time) < timeout:
                try:
                    # Get transaction receipt
                    receipt = w3.eth.get_transaction_receipt(tx_hash)

                    if receipt is None:
                        # Transaction not yet mined
                        logger.debug(f"Transaction {tx_hash} not yet mined")
                        await asyncio.sleep(poll_interval)
                        continue

                    # Check if transaction failed
                    if receipt["status"] == 0:
                        logger.error(f"Transaction {tx_hash} failed (reverted)")
                        return False

                    # Calculate confirmations
                    tx_block = receipt["blockNumber"]
                    current_block = w3.eth.block_number
                    current_confirmations = current_block - tx_block + 1

                    logger.debug(
                        f"Transaction {tx_hash}: {current_confirmations}/{confirmations} confirmations"
                    )

                    if current_confirmations >= confirmations:
                        logger.info(
                            f"✅ Transaction {tx_hash} confirmed with {current_confirmations} confirmations"
                        )
                        return True

                    # Wait before next poll
                    await asyncio.sleep(poll_interval)

                except Exception as poll_error:
                    # Transaction might not be mined yet
                    logger.debug(f"Poll error: {poll_error}")
                    await asyncio.sleep(poll_interval)

            # Timeout
            logger.warning(
                f"Timeout waiting for confirmation of {tx_hash} after {timeout}s"
            )
            return False

        except Exception as e:
            logger.error(f"Error waiting for confirmation: {e}")
            return False

    async def get_transaction_receipt(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get transaction receipt.

        Args:
            tx_hash: Transaction hash

        Returns:
            Transaction receipt dict or None if not found
        """
        try:
            w3 = get_web3(self.network)
            receipt = w3.eth.get_transaction_receipt(tx_hash)

            if receipt is None:
                return None

            return {
                "transaction_hash": receipt["transactionHash"].hex(),
                "block_number": receipt["blockNumber"],
                "block_hash": receipt["blockHash"].hex(),
                "gas_used": receipt["gasUsed"],
                "effective_gas_price": receipt.get("effectiveGasPrice", 0),
                "status": receipt["status"],  # 1 = success, 0 = failure
                "from": receipt["from"],
                "to": receipt.get("to"),
                "logs": len(receipt["logs"]),
            }

        except Exception as e:
            logger.error(f"Failed to get transaction receipt: {e}")
            return None

    async def handle_revert(self, tx_hash: str) -> Optional[str]:
        """Extract revert reason from failed transaction.

        Args:
            tx_hash: Failed transaction hash

        Returns:
            Revert reason string or None
        """
        try:
            w3 = get_web3(self.network)

            # Get transaction
            tx = w3.eth.get_transaction(tx_hash)
            if not tx:
                return None

            # Try to replay transaction to get revert reason
            try:
                w3.eth.call(
                    {
                        "from": tx["from"],
                        "to": tx["to"],
                        "value": tx.get("value", 0),
                        "data": tx.get("input", "0x"),
                    },
                    tx["blockNumber"] - 1,
                )
            except Exception as revert_error:
                error_str = str(revert_error)
                if "execution reverted" in error_str.lower():
                    if ":" in error_str:
                        return error_str.split(":", 1)[1].strip()
                    return "Transaction reverted (no reason)"
                return error_str[:200]

            return "Unknown revert reason"

        except Exception as e:
            logger.error(f"Failed to extract revert reason: {e}")
            return None

    async def watch_contract_events(
        self,
        contract_address: str,
        event_types: List[str],
        callback: Callable[[ChainEvent], None],
    ) -> None:
        """Watch for specific contract events.

        Args:
            contract_address: Contract to watch
            event_types: List of event types to watch for
            callback: Callback function for events
        """
        # TODO Phase 2B: Implement event watching with web3.eth.filter
        logger.warning("Event watching not yet implemented (Phase 2B)")
        raise NotImplementedError("Event watching deferred to Phase 2B")

    async def get_position_value(
        self,
        protocol: str,
        pool_id: str,
    ) -> Decimal:
        """Get current value of a position in USD.

        Args:
            protocol: Protocol name
            pool_id: Pool identifier

        Returns:
            Position value in USD
        """
        # TODO Phase 2B: Implement position valuation
        logger.warning("Position valuation not yet implemented (Phase 2B)")
        raise NotImplementedError("Position valuation deferred to Phase 2B")

    async def get_all_positions(self) -> Dict[str, Dict[str, Decimal]]:
        """Get all active positions across protocols.

        Returns:
            Dict mapping protocol -> pool_id -> value
        """
        # TODO Phase 2B: Implement position tracking
        logger.warning("Position tracking not yet implemented (Phase 2B)")
        raise NotImplementedError("Position tracking deferred to Phase 2B")
