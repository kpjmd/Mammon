"""Web3 provider management for multi-network support.

Provides Web3 instances configured for different networks with:
- Connection pooling and retry logic
- RPC health monitoring
- Network-specific configuration
"""

from typing import Dict, Optional
from web3 import Web3
from web3.providers import HTTPProvider
import time
from src.utils.logger import get_logger
from src.utils.networks import get_network, NetworkConfig

# Import PoA middleware for Web3.py v7+
try:
    from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
except ImportError:
    # Fallback for older versions
    from web3.middleware import geth_poa_middleware

logger = get_logger(__name__)

# Global Web3 instance cache to avoid creating multiple connections
_web3_instances: Dict[str, Web3] = {}


class Web3Provider:
    """Manages Web3 instances for different networks."""

    @staticmethod
    def get_web3(network_id: str, custom_rpc_url: Optional[str] = None) -> Web3:
        """Get or create a Web3 instance for the specified network.

        Args:
            network_id: Network identifier (e.g., "base-mainnet", "arbitrum-sepolia")
            custom_rpc_url: Optional custom RPC URL to override default

        Returns:
            Configured Web3 instance

        Raises:
            ValueError: If network_id is not supported
        """
        # Get network configuration
        network = get_network(network_id)

        # Determine RPC URL
        rpc_url = custom_rpc_url or network.rpc_url

        # Check cache
        cache_key = f"{network_id}:{rpc_url}"
        if cache_key in _web3_instances:
            logger.debug(f"Using cached Web3 instance for {network_id}")
            return _web3_instances[cache_key]

        # Create new Web3 instance
        logger.info(f"Creating new Web3 instance for {network_id}")
        # TODO Phase 2A: Add support for premium RPC providers (Alchemy, Infura, QuickNode)
        # TODO Phase 2A: Implement request batching to reduce RPC calls
        # TODO Phase 2A: Add RPC endpoint rotation/fallback for reliability
        # TODO Phase 2A: Implement connection pooling for better performance
        provider = HTTPProvider(
            rpc_url,
            request_kwargs={
                "timeout": 60,  # 60 second timeout
            },
        )

        w3 = Web3(provider)

        # Add PoA middleware for networks that need it (some testnets)
        # This handles the extraData field in block headers for PoA chains
        if network.is_testnet or network_id in ["base-mainnet", "base-sepolia"]:
            try:
                w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                logger.debug(f"Injected PoA middleware for {network_id}")
            except Exception as e:
                logger.warning(f"Could not inject PoA middleware: {e}. Continuing without it.")

        # Verify connection
        if not Web3Provider._verify_connection(w3, network):
            raise ConnectionError(f"Failed to connect to {network_id} at {rpc_url}")

        # Cache the instance
        _web3_instances[cache_key] = w3

        logger.info(f"✅ Successfully connected to {network_id} (Chain ID: {network.chain_id})")
        return w3

    @staticmethod
    def _verify_connection(w3: Web3, network: NetworkConfig, max_retries: int = 3) -> bool:
        """Verify Web3 connection to the network.

        Args:
            w3: Web3 instance to verify
            network: Network configuration
            max_retries: Maximum number of connection attempts

        Returns:
            True if connection is successful, False otherwise
        """
        for attempt in range(max_retries):
            try:
                # Check if connected
                if not w3.is_connected():
                    logger.warning(f"Connection attempt {attempt + 1}/{max_retries} failed")
                    # TODO Phase 2A: Use exponential backoff here too (currently fixed 1s delay)
                    time.sleep(1)
                    continue

                # Verify chain ID matches
                chain_id = w3.eth.chain_id
                if chain_id != network.chain_id:
                    logger.error(
                        f"Chain ID mismatch: expected {network.chain_id}, got {chain_id}"
                    )
                    return False

                # Get latest block to ensure RPC is working
                block_number = w3.eth.block_number
                logger.debug(f"Connected to {network.network_id}, latest block: {block_number}")

                return True

            except Exception as e:
                logger.warning(
                    f"Connection verification attempt {attempt + 1}/{max_retries} failed: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff

        return False

    @staticmethod
    def check_connection_health(network_id: str, custom_rpc_url: Optional[str] = None) -> Dict:
        """Check the health of a network connection.

        Args:
            network_id: Network identifier
            custom_rpc_url: Optional custom RPC URL

        Returns:
            Dict with health status information
        """
        try:
            w3 = Web3Provider.get_web3(network_id, custom_rpc_url)
            network = get_network(network_id)

            # Get network stats
            block_number = w3.eth.block_number
            chain_id = w3.eth.chain_id
            gas_price = w3.eth.gas_price

            return {
                "network_id": network_id,
                "connected": True,
                "chain_id": chain_id,
                "chain_id_match": chain_id == network.chain_id,
                "block_number": block_number,
                "gas_price_gwei": float(w3.from_wei(gas_price, "gwei")),
                "rpc_url": custom_rpc_url or network.rpc_url,
            }

        except Exception as e:
            logger.error(f"Health check failed for {network_id}: {e}")
            return {
                "network_id": network_id,
                "connected": False,
                "error": str(e),
            }

    @staticmethod
    def clear_cache(network_id: Optional[str] = None) -> None:
        """Clear cached Web3 instances.

        Args:
            network_id: Optional specific network to clear, or None to clear all
        """
        global _web3_instances

        if network_id is None:
            _web3_instances.clear()
            logger.info("Cleared all cached Web3 instances")
        else:
            # Clear all instances for this network
            keys_to_remove = [key for key in _web3_instances if key.startswith(f"{network_id}:")]
            for key in keys_to_remove:
                del _web3_instances[key]
            logger.info(f"Cleared cached Web3 instances for {network_id}")


# Convenience functions
def get_web3(network_id: str, custom_rpc_url: Optional[str] = None) -> Web3:
    """Get a Web3 instance for the specified network.

    Convenience wrapper around Web3Provider.get_web3().

    Args:
        network_id: Network identifier
        custom_rpc_url: Optional custom RPC URL

    Returns:
        Configured Web3 instance
    """
    return Web3Provider.get_web3(network_id, custom_rpc_url)


def check_network_health(network_id: str) -> Dict:
    """Check network connection health.

    Convenience wrapper around Web3Provider.check_connection_health().

    Args:
        network_id: Network identifier

    Returns:
        Dict with health status
    """
    return Web3Provider.check_connection_health(network_id)
