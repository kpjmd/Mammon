"""Transaction building, signing, and submission for Base network.

This module handles the construction and execution of blockchain transactions
with proper error handling and retry logic.
"""

from typing import Any, Dict, Optional
from decimal import Decimal
from enum import Enum
from src.utils.logger import get_logger
from src.utils.web3_provider import get_web3

logger = get_logger(__name__)


class TransactionStatus(Enum):
    """Status of a blockchain transaction."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class Transaction:
    """Represents a blockchain transaction.

    Attributes:
        to_address: Recipient address
        data: Transaction data (encoded function call)
        value: ETH value to send
        gas_limit: Gas limit
        gas_price: Gas price
        nonce: Transaction nonce
        hash: Transaction hash after submission
        status: Current transaction status
    """

    def __init__(
        self,
        to_address: str,
        data: str = "0x",
        value: Decimal = Decimal("0"),
        gas_limit: Optional[int] = None,
        gas_price: Optional[int] = None,
    ) -> None:
        """Initialize a transaction.

        Args:
            to_address: Recipient address
            data: Transaction data
            value: ETH value to send
            gas_limit: Gas limit (estimated if None)
            gas_price: Gas price (current if None)
        """
        self.to_address = to_address
        self.data = data
        self.value = value
        self.gas_limit = gas_limit
        self.gas_price = gas_price
        self.nonce: Optional[int] = None
        self.hash: Optional[str] = None
        self.status = TransactionStatus.PENDING


class TransactionBuilder:
    """Builds and manages blockchain transactions.

    Handles transaction construction, gas estimation, signing,
    and submission with retry logic.

    Attributes:
        wallet: Wallet manager instance
        config: Transaction configuration
        network: Network ID (e.g., "base-sepolia")
        max_slippage_percent: Maximum allowed slippage (default: 1%)
    """

    def __init__(self, wallet: Any, config: Dict[str, Any]) -> None:
        """Initialize the transaction builder.

        Args:
            wallet: WalletManager instance
            config: Transaction configuration
        """
        self.wallet = wallet
        self.config = config
        self.network = config.get("network", "base-sepolia")
        self.max_slippage_percent = config.get("max_slippage_percent", 1.0)

    async def simulate_transaction(
        self,
        to_address: str,
        data: str = "0x",
        value: Decimal = Decimal("0"),
        from_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Simulate transaction execution via eth_call (DRY RUN).

        This executes the transaction against current blockchain state
        WITHOUT sending it. Detects reverts before real execution.

        Args:
            to_address: Recipient address
            data: Transaction data (hex string)
            value: ETH value to send
            from_address: Sender address (defaults to wallet address)

        Returns:
            Dict with simulation results:
                - success: bool
                - return_data: hex string (if success)
                - revert_reason: str (if failed)
                - gas_used: estimated gas consumption

        Raises:
            ValueError: If simulation setup fails
        """
        try:
            w3 = get_web3(self.network)

            # Get sender address
            if not from_address:
                from_address = await self.wallet.get_address()

            # Convert value to wei
            value_wei = w3.to_wei(str(value), "ether") if value > 0 else 0

            # Build transaction params for eth_call
            tx_params = {
                "from": from_address,
                "to": to_address,
                "value": value_wei,
            }

            if data and data != "0x":
                tx_params["data"] = data

            logger.info(f"Simulating transaction to {to_address}...")

            try:
                # Execute eth_call (simulation)
                result = w3.eth.call(tx_params)

                # Estimate gas
                gas_estimate = w3.eth.estimate_gas(tx_params)

                logger.info(f"✅ Simulation successful, estimated gas: {gas_estimate}")

                return {
                    "success": True,
                    "return_data": result.hex() if result else "0x",
                    "revert_reason": None,
                    "gas_used": gas_estimate,
                }

            except Exception as call_error:
                # Transaction would revert
                logger.warning(f"❌ Simulation failed: {call_error}")

                # Try to extract revert reason
                revert_reason = self._extract_revert_reason(call_error)

                return {
                    "success": False,
                    "return_data": None,
                    "revert_reason": revert_reason,
                    "gas_used": 0,
                }

        except Exception as e:
            logger.error(f"Simulation setup failed: {e}")
            raise ValueError(f"Failed to set up transaction simulation: {e}")

    def _extract_revert_reason(self, error: Exception) -> str:
        """Extract revert reason from error message.

        Args:
            error: Exception from eth_call

        Returns:
            Human-readable revert reason
        """
        error_str = str(error)

        # Common revert patterns
        if "execution reverted" in error_str.lower():
            # Try to extract the reason
            if ":" in error_str:
                return error_str.split(":", 1)[1].strip()
            return "Transaction would revert (no reason given)"

        if "insufficient funds" in error_str.lower():
            return "Insufficient funds for transaction"

        if "gas required exceeds allowance" in error_str.lower():
            return "Gas required exceeds allowance"

        return f"Unknown revert: {error_str[:100]}"

    async def detect_revert(
        self,
        to_address: str,
        data: str = "0x",
        value: Decimal = Decimal("0"),
    ) -> tuple[bool, Optional[str]]:
        """Check if a transaction would revert before execution.

        Args:
            to_address: Recipient address
            data: Transaction data
            value: ETH value

        Returns:
            Tuple of (will_revert: bool, reason: Optional[str])
        """
        simulation = await self.simulate_transaction(to_address, data, value)

        if simulation["success"]:
            return (False, None)
        else:
            return (True, simulation["revert_reason"])

    async def validate_slippage(
        self,
        expected_output: Decimal,
        min_output: Decimal,
    ) -> bool:
        """Validate slippage is within acceptable limits.

        Args:
            expected_output: Expected output amount
            min_output: Minimum acceptable output

        Returns:
            True if slippage acceptable, False otherwise
        """
        if expected_output == 0:
            return False

        actual_slippage = ((expected_output - min_output) / expected_output) * 100

        if actual_slippage > self.max_slippage_percent:
            logger.warning(
                f"Slippage too high: {actual_slippage:.2f}% > "
                f"{self.max_slippage_percent}%"
            )
            return False

        logger.info(f"Slippage acceptable: {actual_slippage:.2f}%")
        return True

    async def build_transaction(
        self,
        to_address: str,
        data: str = "0x",
        value: Decimal = Decimal("0"),
    ) -> Transaction:
        """Build a transaction with gas estimation.

        Args:
            to_address: Recipient address
            data: Transaction data
            value: ETH value

        Returns:
            Constructed transaction
        """
        # Estimate gas via wallet manager
        gas_limit = await self.wallet.estimate_gas(
            to_address, value, data, token="ETH"
        )

        # Get current gas price
        w3 = get_web3(self.network)
        latest_block = w3.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas", 0)

        # Calculate EIP-1559 fees
        max_priority_fee = w3.to_wei(1, "gwei")
        max_fee_per_gas = (base_fee * 2) + max_priority_fee

        # Create transaction object
        tx = Transaction(
            to_address=to_address,
            data=data,
            value=value,
            gas_limit=gas_limit,
            gas_price=max_fee_per_gas,
        )

        logger.info(f"Built transaction: to={to_address}, gas={gas_limit}")
        return tx

    async def estimate_gas(self, transaction: Transaction) -> int:
        """Estimate gas required for a transaction.

        Args:
            transaction: Transaction to estimate

        Returns:
            Estimated gas units (with 20% buffer)
        """
        return await self.wallet.estimate_gas(
            transaction.to_address,
            transaction.value,
            transaction.data,
            token="ETH",
        )

    async def sign_transaction(self, transaction: Transaction) -> Transaction:
        """Sign a transaction via wallet manager.

        Args:
            transaction: Transaction to sign

        Returns:
            Signed transaction
        """
        # Build transaction dict
        tx_dict = {
            "to": transaction.to_address,
            "value": str(transaction.value),
            "data": transaction.data,
            "gas": transaction.gas_limit,
        }

        # Sign via wallet
        signed = await self.wallet.sign_transaction(tx_dict)

        # Update transaction status
        transaction.status = TransactionStatus.SUBMITTED
        return transaction

    async def submit_transaction(self, transaction: Transaction) -> str:
        """Submit a signed transaction to the network.

        Args:
            transaction: Signed transaction

        Returns:
            Transaction hash
        """
        # Execute via wallet manager
        result = await self.wallet.execute_transaction(
            transaction.to_address,
            transaction.value,
            transaction.data,
            token="ETH",
        )

        tx_hash = result["tx_hash"]
        transaction.hash = tx_hash
        transaction.status = TransactionStatus.SUBMITTED

        logger.info(f"Transaction submitted: {tx_hash}")
        return tx_hash

    async def wait_for_confirmation(
        self,
        tx_hash: str,
        confirmations: int = 2,
        timeout: int = 300,
    ) -> bool:
        """Wait for transaction confirmation.

        Args:
            tx_hash: Transaction hash
            confirmations: Number of confirmations to wait for (default: 2)
            timeout: Timeout in seconds (default: 300)

        Returns:
            True if confirmed, False if timeout/failed
        """
        from src.blockchain.monitor import ChainMonitor

        monitor = ChainMonitor(self.config, await self.wallet.get_address())
        return await monitor.wait_for_confirmation(tx_hash, confirmations, timeout)

    async def get_transaction_receipt(self, tx_hash: str) -> Dict[str, Any]:
        """Get transaction receipt.

        Args:
            tx_hash: Transaction hash

        Returns:
            Transaction receipt
        """
        w3 = get_web3(self.network)
        receipt = w3.eth.get_transaction_receipt(tx_hash)

        return {
            "transaction_hash": receipt["transactionHash"].hex(),
            "block_number": receipt["blockNumber"],
            "gas_used": receipt["gasUsed"],
            "status": receipt["status"],  # 1 = success, 0 = failure
            "logs": receipt["logs"],
        }
