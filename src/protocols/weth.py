"""WETH (Wrapped Ether) protocol integration.

Provides ETH wrapping/unwrapping functionality for testing transaction execution.
This is the simplest DeFi operation - perfect for validating security layers.
"""

from decimal import Decimal
from typing import Dict, Any, Optional
from web3 import Web3
from web3.contract import Contract

from src.utils.logger import get_logger

logger = get_logger(__name__)

# WETH9 ABI (deposit, withdraw, balanceOf)
WETH_ABI = [
    {
        "constant": False,
        "inputs": [],
        "name": "deposit",
        "outputs": [],
        "payable": True,
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "wad", "type": "uint256"}],
        "name": "withdraw",
        "outputs": [],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
]

# WETH addresses by network
WETH_ADDRESSES = {
    "arbitrum-sepolia": "0x980B62Da83eFf3D4576C647993b0c1D7faf17c73",
    "base-sepolia": "0x4200000000000000000000000000000000000006",
    "base-mainnet": "0x4200000000000000000000000000000000000006",
}


class WETHProtocol:
    """WETH protocol integration for wrapping/unwrapping ETH."""

    def __init__(self, w3: Web3, network: str):
        """Initialize WETH protocol.

        Args:
            w3: Web3 instance
            network: Network ID (e.g., "arbitrum-sepolia")
        """
        self.w3 = w3
        self.network = network

        # Get WETH address
        if network not in WETH_ADDRESSES:
            raise ValueError(f"WETH not supported on {network}")

        self.weth_address = WETH_ADDRESSES[network]
        self.weth_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.weth_address),
            abi=WETH_ABI,
        )

        logger.info(
            f"Initialized WETH protocol on {network}",
            extra={"weth_address": self.weth_address},
        )

    def get_weth_balance(self, account: str) -> Decimal:
        """Get WETH balance for an account.

        Args:
            account: Account address

        Returns:
            WETH balance in ETH units
        """
        balance_wei = self.weth_contract.functions.balanceOf(
            self.w3.to_checksum_address(account)
        ).call()

        balance_eth = Decimal(balance_wei) / Decimal(10**18)

        logger.debug(
            f"WETH balance for {account}: {balance_eth}",
            extra={"account": account, "balance_wei": balance_wei},
        )

        return balance_eth

    def build_wrap_transaction(
        self, from_address: str, amount_eth: Decimal
    ) -> Dict[str, Any]:
        """Build a transaction to wrap ETH into WETH.

        Args:
            from_address: Address wrapping ETH
            amount_eth: Amount of ETH to wrap

        Returns:
            Transaction dict ready for signing
        """
        amount_wei = int(amount_eth * Decimal(10**18))

        # Build deposit transaction (payable function)
        tx = self.weth_contract.functions.deposit().build_transaction(
            {
                "from": self.w3.to_checksum_address(from_address),
                "value": amount_wei,
                "gas": 50000,  # Standard WETH deposit gas limit
                "gasPrice": self.w3.eth.gas_price,
                "nonce": self.w3.eth.get_transaction_count(
                    self.w3.to_checksum_address(from_address)
                ),
            }
        )

        logger.info(
            f"Built wrap transaction: {amount_eth} ETH → WETH",
            extra={
                "from": from_address,
                "amount_eth": str(amount_eth),
                "amount_wei": amount_wei,
                "gas": tx["gas"],
                "gas_price": tx["gasPrice"],
            },
        )

        return tx

    def build_unwrap_transaction(
        self, from_address: str, amount_eth: Decimal
    ) -> Dict[str, Any]:
        """Build a transaction to unwrap WETH into ETH.

        Args:
            from_address: Address unwrapping WETH
            amount_eth: Amount of WETH to unwrap

        Returns:
            Transaction dict ready for signing
        """
        amount_wei = int(amount_eth * Decimal(10**18))

        # Build withdraw transaction
        tx = self.weth_contract.functions.withdraw(amount_wei).build_transaction(
            {
                "from": self.w3.to_checksum_address(from_address),
                "gas": 50000,  # Standard WETH withdraw gas limit
                "gasPrice": self.w3.eth.gas_price,
                "nonce": self.w3.eth.get_transaction_count(
                    self.w3.to_checksum_address(from_address)
                ),
            }
        )

        logger.info(
            f"Built unwrap transaction: {amount_eth} WETH → ETH",
            extra={
                "from": from_address,
                "amount_eth": str(amount_eth),
                "amount_wei": amount_wei,
                "gas": tx["gas"],
                "gas_price": tx["gasPrice"],
            },
        )

        return tx

    def estimate_wrap_gas(self, from_address: str, amount_eth: Decimal) -> int:
        """Estimate gas for wrapping ETH.

        Args:
            from_address: Address wrapping ETH
            amount_eth: Amount to wrap

        Returns:
            Estimated gas units
        """
        amount_wei = int(amount_eth * Decimal(10**18))

        gas_estimate = self.weth_contract.functions.deposit().estimate_gas(
            {
                "from": self.w3.to_checksum_address(from_address),
                "value": amount_wei,
            }
        )

        logger.debug(
            f"Estimated wrap gas: {gas_estimate}",
            extra={"amount_eth": str(amount_eth), "gas": gas_estimate},
        )

        return gas_estimate

    def estimate_unwrap_gas(self, from_address: str, amount_eth: Decimal) -> int:
        """Estimate gas for unwrapping WETH.

        Args:
            from_address: Address unwrapping WETH
            amount_eth: Amount to unwrap

        Returns:
            Estimated gas units
        """
        amount_wei = int(amount_eth * Decimal(10**18))

        gas_estimate = self.weth_contract.functions.withdraw(amount_wei).estimate_gas(
            {"from": self.w3.to_checksum_address(from_address)}
        )

        logger.debug(
            f"Estimated unwrap gas: {gas_estimate}",
            extra={"amount_eth": str(amount_eth), "gas": gas_estimate},
        )

        return gas_estimate
