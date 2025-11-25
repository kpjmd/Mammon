"""Thread-safe nonce management for wallet transactions.

Prevents nonce collisions in concurrent transaction scenarios by managing
pending nonces in-memory with chain synchronization.
"""

import threading
from typing import Optional
from web3 import Web3
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NonceTracker:
    """Thread-safe nonce tracker with chain synchronization.

    Manages transaction nonces to prevent collisions in concurrent operations.
    Syncs with on-chain state to handle restarts and failed transactions.

    Attributes:
        _web3: Web3 instance for chain queries
        _address: Wallet address to track nonces for
        _lock: Threading lock for atomic operations
        _pending_nonce: Next nonce to use (None = not initialized)
    """

    def __init__(self, web3: Web3, address: str):
        """Initialize nonce tracker.

        Args:
            web3: Web3 instance connected to network
            address: Wallet address (checksummed)
        """
        self._web3 = web3
        self._address = address
        self._lock = threading.Lock()
        self._pending_nonce: Optional[int] = None

        logger.debug(f"NonceTracker initialized for {address}")

    def get_next_nonce(self) -> int:
        """Get the next available nonce in a thread-safe manner.

        This method:
        1. Acquires lock for thread safety
        2. Queries chain for latest confirmed nonce
        3. Returns max(pending_nonce, chain_nonce)
        4. Increments pending counter

        Returns:
            Next nonce to use for transaction

        Example:
            nonce = tracker.get_next_nonce()
            tx = {'nonce': nonce, ...}
        """
        with self._lock:
            # Get latest confirmed nonce from chain
            chain_nonce = self._web3.eth.get_transaction_count(
                self._address,
                block_identifier='pending'  # Include pending transactions
            )

            # Initialize or sync with chain if needed
            if self._pending_nonce is None or self._pending_nonce < chain_nonce:
                logger.debug(
                    f"Syncing nonce: pending={self._pending_nonce}, "
                    f"chain={chain_nonce}"
                )
                self._pending_nonce = chain_nonce

            # Get current nonce and increment for next call
            current_nonce = self._pending_nonce
            self._pending_nonce += 1

            logger.debug(f"Allocated nonce {current_nonce} to transaction")
            return current_nonce

    def reset(self) -> None:
        """Reset nonce tracking to sync with chain state.

        Call this when:
        - A transaction fails before being sent
        - You detect a nonce gap
        - Recovery from error state is needed

        The next call to get_next_nonce() will re-sync with chain.
        """
        with self._lock:
            old_nonce = self._pending_nonce
            self._pending_nonce = None
            logger.info(
                f"Nonce tracker reset (was: {old_nonce}, "
                f"will re-sync with chain on next call)"
            )

    def get_current_chain_nonce(self) -> int:
        """Get the current nonce from the chain (for debugging/monitoring).

        Returns:
            Current transaction count on chain
        """
        return self._web3.eth.get_transaction_count(
            self._address,
            block_identifier='pending'
        )

    @property
    def pending_nonce(self) -> Optional[int]:
        """Get the current pending nonce value (thread-safe read).

        Returns:
            Pending nonce or None if not initialized
        """
        with self._lock:
            return self._pending_nonce
