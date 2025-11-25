"""Local wallet provider using BIP-39 seed phrase.

Provides full control over wallet operations with guaranteed persistence.
Uses standard BIP-44 derivation path (m/44'/60'/0'/0/0) compatible with
MetaMask and hardware wallets.
"""

from decimal import Decimal
from typing import Dict, Any, Optional
from web3 import Web3
from web3.types import TxParams, Wei, HexBytes
from eth_account import Account
from eth_account.hdaccount import ETHEREUM_DEFAULT_PATH
from src.wallet.base_provider import WalletProvider
from src.wallet.nonce_tracker import NonceTracker
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LocalWalletProvider(WalletProvider):
    """Local wallet provider using BIP-39 seed phrase.

    Derivation Path: m/44'/60'/0'/0/0
    - 44' = BIP-44 (multi-coin hierarchy)
    - 60' = Ethereum coin type
    - 0'  = Account 0 (hardened)
    - 0   = External chain (non-hardened)
    - 0   = Address index 0

    This is the standard MetaMask/Ledger path for Ethereum account 1.

    Security:
    - Private key derived from seed phrase, never stored
    - Seed phrase loaded from environment variable
    - Transaction signing happens in-memory
    - All operations respect security manager limits

    Attributes:
        web3: Web3 instance for network interaction
        account: eth_account.Account for signing
        address: Checksummed Ethereum address
        nonce_tracker: Thread-safe nonce management
        config: Configuration with gas limits and caps
    """

    def __init__(
        self,
        seed_phrase: str,
        web3: Web3,
        config: Dict[str, Any],
    ):
        """Initialize local wallet from seed phrase.

        Args:
            seed_phrase: BIP-39 mnemonic (12 or 24 words)
            web3: Web3 instance connected to network
            config: Configuration dict with gas limits

        Raises:
            ValueError: If seed phrase is invalid
        """
        # Enable HD wallet features
        Account.enable_unaudited_hdwallet_features()

        # Derive account from seed phrase
        try:
            self.account = Account.from_mnemonic(
                seed_phrase,
                account_path=ETHEREUM_DEFAULT_PATH
            )
        except Exception as e:
            logger.error(f"Failed to derive account from seed phrase: {e}")
            raise ValueError(f"Invalid seed phrase: {e}")

        self.web3 = web3
        self.address = self.account.address
        self.config = config

        # Initialize thread-safe nonce tracker
        self.nonce_tracker = NonceTracker(web3, self.address)

        logger.info(f"✅ LocalWalletProvider initialized: {self.address}")
        logger.debug(f"   Derivation path: {ETHEREUM_DEFAULT_PATH}")

    def get_address(self) -> str:
        """Get wallet address.

        Returns:
            Checksummed Ethereum address
        """
        return self.address

    def get_balance(self, token: str = "eth") -> Decimal:
        """Get token balance.

        Args:
            token: Token symbol (default: "eth")

        Returns:
            Balance as Decimal

        Note:
            Currently only supports ETH. ERC-20 support in Phase 2.
        """
        if token.lower() != "eth":
            raise NotImplementedError(
                f"Token {token} not yet supported. "
                f"Only ETH is supported in current version."
            )

        try:
            balance_wei = self.web3.eth.get_balance(self.address)
            balance_eth = Decimal(balance_wei) / Decimal(10**18)
            logger.debug(f"Balance for {self.address}: {balance_eth} ETH")
            return balance_eth
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return Decimal("0")

    def get_nonce(self) -> int:
        """Get next available nonce.

        Returns:
            Next nonce for transaction
        """
        return self.nonce_tracker.get_next_nonce()

    def reset_nonce(self) -> None:
        """Reset nonce tracker to sync with chain."""
        self.nonce_tracker.reset()

    def sign_transaction(self, transaction: TxParams) -> bytes:
        """Sign transaction without sending.

        Args:
            transaction: Transaction parameters

        Returns:
            Raw signed transaction bytes
        """
        signed = self.account.sign_transaction(transaction)
        return signed.raw_transaction

    def send_transaction(self, transaction: TxParams) -> HexBytes:
        """Sign and send transaction.

        This method:
        1. Validates transaction parameters
        2. Adds nonce if not present
        3. Estimates gas with safety buffer
        4. Signs transaction locally
        5. Sends to network
        6. Resets nonce on failure

        Args:
            transaction: Transaction parameters

        Returns:
            Transaction hash

        Raises:
            ValueError: If transaction validation fails
            ConnectionError: If unable to send transaction
        """
        try:
            # Build complete transaction with nonce and gas
            tx = self._build_transaction(transaction)

            # Validate transaction
            self._validate_transaction(tx)

            # CRITICAL SECURITY: Simulate transaction before sending
            # This catches transactions that would revert on-chain
            logger.debug("🧪 Simulating transaction...")
            try:
                self.web3.eth.call(tx, block_identifier='pending')
                logger.debug("✅ Simulation passed")
            except Exception as sim_error:
                logger.error(f"❌ Transaction simulation failed: {sim_error}")
                self.nonce_tracker.reset()  # Don't waste nonce on failed simulation
                raise ValueError(
                    f"Transaction would fail on-chain: {sim_error}. "
                    f"Transaction aborted before sending."
                )

            # Sign transaction
            signed = self.account.sign_transaction(tx)

            logger.info(f"🔐 Transaction signed, sending to network...")
            logger.debug(f"   Nonce: {tx['nonce']}")
            logger.debug(f"   Gas limit: {tx['gas']}")
            logger.debug(f"   Max fee: {tx['maxFeePerGas'] / 1e9:.2f} gwei")

            # Send signed transaction
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)

            logger.info(f"✅ Transaction sent: {tx_hash.hex()}")
            return tx_hash

        except Exception as e:
            # Reset nonce on failure to prevent nonce gaps
            logger.error(f"Transaction failed: {e}")
            self.nonce_tracker.reset()
            raise

    def _build_transaction(self, tx: TxParams) -> TxParams:
        """Build complete transaction with nonce and gas parameters.

        Args:
            tx: Base transaction parameters

        Returns:
            Complete transaction ready to sign
        """
        # Add nonce if not present
        if 'nonce' not in tx:
            tx['nonce'] = self.get_nonce()

        # Add chain ID
        if 'chainId' not in tx:
            tx['chainId'] = self.web3.eth.chain_id

        # Estimate gas if not provided
        if 'gas' not in tx:
            gas_params = self._estimate_gas_with_buffer(tx)
            tx.update(gas_params)

        return tx

    def _estimate_gas_with_buffer(self, tx: TxParams) -> Dict[str, int]:
        """Estimate gas with tiered safety buffers and caps.

        Buffer tiers:
        - < 50k gas: +50% buffer (simple operations)
        - 50k-200k gas: +30% buffer (moderate complexity)
        - > 200k gas: +20% buffer (complex operations)

        Args:
            tx: Transaction to estimate gas for

        Returns:
            Dict with gas, maxFeePerGas, maxPriorityFeePerGas
        """
        # Estimate base gas
        try:
            estimated_gas = self.web3.eth.estimate_gas(tx)
        except Exception as e:
            logger.warning(f"Gas estimation failed: {e}, using default")
            estimated_gas = 21000  # Default for simple transfer

        # Apply tiered buffer
        if estimated_gas < 50_000:
            buffer = self.config.get("gas_buffer_simple", 1.5)
        elif estimated_gas < 200_000:
            buffer = self.config.get("gas_buffer_moderate", 1.3)
        else:
            buffer = self.config.get("gas_buffer_complex", 1.2)

        gas_limit = int(estimated_gas * buffer)

        # Get EIP-1559 fee parameters
        latest_block = self.web3.eth.get_block('latest')
        base_fee = latest_block.get('baseFeePerGas', 0)

        try:
            max_priority = self.web3.eth.max_priority_fee
        except Exception:
            max_priority = self.web3.to_wei(2, 'gwei')  # Default 2 gwei

        # Calculate max fee (base fee * 2 + priority for next block)
        max_fee = (base_fee * 2) + max_priority

        # Apply caps from config
        max_gas_price = self.config.get(
            "max_gas_price_gwei",
            100
        ) * 10**9  # Convert gwei to wei

        max_priority_cap = self.config.get(
            "max_priority_fee_gwei",
            2
        ) * 10**9

        max_fee = min(max_fee, max_gas_price)
        max_priority = min(max_priority, max_priority_cap)

        logger.debug(
            f"Gas estimation: limit={gas_limit}, "
            f"maxFee={max_fee/1e9:.2f} gwei, "
            f"priority={max_priority/1e9:.2f} gwei"
        )

        return {
            'gas': gas_limit,
            'maxFeePerGas': max_fee,
            'maxPriorityFeePerGas': max_priority,
        }

    def _validate_transaction(self, tx: TxParams) -> None:
        """Validate transaction parameters before sending.

        Args:
            tx: Transaction to validate

        Raises:
            ValueError: If transaction is invalid
        """
        # Check required fields
        required = ['to', 'nonce', 'gas', 'chainId']
        missing = [f for f in required if f not in tx]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # Validate addresses
        if not self.web3.is_address(tx['to']):
            raise ValueError(f"Invalid 'to' address: {tx['to']}")

        # Check balance for value transfer
        value = tx.get('value', 0)
        if value > 0:
            balance = self.web3.eth.get_balance(self.address)
            total_cost = value + (tx['gas'] * tx['maxFeePerGas'])
            if balance < total_cost:
                raise ValueError(
                    f"Insufficient balance: have {balance} wei, "
                    f"need {total_cost} wei"
                )

        logger.debug("Transaction validation passed")
