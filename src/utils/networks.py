"""Network configuration registry for multi-chain support.

This module provides network configurations for all supported chains,
enabling MAMMON to operate on Base, Arbitrum, and other EVM networks.
"""

from dataclasses import dataclass
from typing import Dict, Optional
from decimal import Decimal


class NetworkNotFoundError(ValueError):
    """Raised when requested network is not found in registry."""
    pass


@dataclass(frozen=True)
class NetworkConfig:
    """Configuration for a blockchain network.

    Attributes:
        network_id: Unique identifier (e.g., "base-sepolia")
        chain_id: EVM chain ID for transaction signing
        rpc_url: Default RPC endpoint URL
        explorer_url: Block explorer base URL
        native_token: Native token symbol (e.g., "ETH")
        is_testnet: Whether this is a testnet
        description: Human-readable description
    """
    network_id: str
    chain_id: int
    rpc_url: str
    explorer_url: str
    native_token: str
    is_testnet: bool
    description: str


# Network registry - all supported networks
NETWORKS: Dict[str, NetworkConfig] = {
    # Base Networks (Coinbase L2)
    "base-mainnet": NetworkConfig(
        network_id="base-mainnet",
        chain_id=8453,
        rpc_url="https://mainnet.base.org",
        explorer_url="https://basescan.org",
        native_token="ETH",
        is_testnet=False,
        description="Base Mainnet (Coinbase L2)",
    ),
    "base-sepolia": NetworkConfig(
        network_id="base-sepolia",
        chain_id=84532,
        rpc_url="https://sepolia.base.org",
        explorer_url="https://sepolia.basescan.org",
        native_token="ETH",
        is_testnet=True,
        description="Base Sepolia Testnet",
    ),

    # Arbitrum Networks (Offchain Labs L2)
    "arbitrum-mainnet": NetworkConfig(
        network_id="arbitrum-mainnet",
        chain_id=42161,
        rpc_url="https://arb1.arbitrum.io/rpc",
        explorer_url="https://arbiscan.io",
        native_token="ETH",
        is_testnet=False,
        description="Arbitrum One Mainnet",
    ),
    "arbitrum-sepolia": NetworkConfig(
        network_id="arbitrum-sepolia",
        chain_id=421614,
        rpc_url="https://sepolia-rollup.arbitrum.io/rpc",
        explorer_url="https://sepolia.arbiscan.io",
        native_token="ETH",
        is_testnet=True,
        description="Arbitrum Sepolia Testnet",
    ),
}


def get_network(network_id: str) -> NetworkConfig:
    """Get network configuration by ID.

    Args:
        network_id: Network identifier (e.g., "base-sepolia")

    Returns:
        NetworkConfig for the specified network

    Raises:
        NetworkNotFoundError: If network_id is not supported
    """
    if network_id not in NETWORKS:
        supported = ", ".join(NETWORKS.keys())
        raise NetworkNotFoundError(
            f"Unsupported network: {network_id}. "
            f"Supported networks: {supported}"
        )
    return NETWORKS[network_id]


def validate_network(network_id: str) -> bool:
    """Check if a network ID is valid.

    Args:
        network_id: Network identifier to validate

    Returns:
        True if network is supported, False otherwise
    """
    return network_id in NETWORKS


def get_supported_networks() -> list[str]:
    """Get list of all supported network IDs.

    Returns:
        List of network identifiers
    """
    return list(NETWORKS.keys())


def get_testnet_networks() -> list[str]:
    """Get list of testnet network IDs.

    Returns:
        List of testnet network identifiers
    """
    return [
        net_id for net_id, config in NETWORKS.items()
        if config.is_testnet
    ]


def get_mainnet_networks() -> list[str]:
    """Get list of mainnet network IDs.

    Returns:
        List of mainnet network identifiers
    """
    return [
        net_id for net_id, config in NETWORKS.items()
        if not config.is_testnet
    ]


def get_rpc_url(network_id: str, custom_rpc: Optional[str] = None) -> str:
    """Get RPC URL for a network, with optional override.

    Args:
        network_id: Network identifier
        custom_rpc: Optional custom RPC URL to use instead of default

    Returns:
        RPC URL to use for this network

    Raises:
        ValueError: If network_id is not supported
    """
    if custom_rpc:
        return custom_rpc

    network = get_network(network_id)
    return network.rpc_url


def get_explorer_url(network_id: str) -> str:
    """Get block explorer URL for a network.

    Args:
        network_id: Network identifier

    Returns:
        Block explorer base URL

    Raises:
        ValueError: If network_id is not supported
    """
    network = get_network(network_id)
    return network.explorer_url


def format_explorer_tx_url(network_id: str, tx_hash: str) -> str:
    """Format a transaction URL for the block explorer.

    Args:
        network_id: Network identifier
        tx_hash: Transaction hash (with or without 0x prefix)

    Returns:
        Full URL to view transaction on explorer
    """
    explorer = get_explorer_url(network_id)
    # Ensure tx_hash has 0x prefix
    if not tx_hash.startswith("0x"):
        tx_hash = f"0x{tx_hash}"
    return f"{explorer}/tx/{tx_hash}"


def format_explorer_address_url(network_id: str, address: str) -> str:
    """Format an address URL for the block explorer.

    Args:
        network_id: Network identifier
        address: Ethereum address (with or without 0x prefix)

    Returns:
        Full URL to view address on explorer
    """
    explorer = get_explorer_url(network_id)
    # Ensure address has 0x prefix
    if not address.startswith("0x"):
        address = f"0x{address}"
    return f"{explorer}/address/{address}"
