"""Web3 provider management for multi-network support.

Provides Web3 instances configured for different networks with:
- Premium RPC support with automatic fallback (Sprint 4 Priority 2)
- Circuit breaker pattern for failed endpoints
- Rate limiting and cost tracking
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
from src.utils.rpc_manager import (
    RpcManager,
    RpcEndpoint,
    EndpointPriority,
    AllEndpointsFailedError,
)

# Import PoA middleware for Web3.py v7+
try:
    from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
except ImportError:
    # Fallback for older versions
    from web3.middleware import geth_poa_middleware

logger = get_logger(__name__)

# Global Web3 instance cache to avoid creating multiple connections
_web3_instances: Dict[str, Web3] = {}

# Global RPC manager instance
_rpc_manager: Optional[RpcManager] = None


def _initialize_rpc_manager(config) -> RpcManager:
    """Initialize the global RPC manager with configured endpoints.

    Args:
        config: Settings instance with RPC configuration

    Returns:
        Initialized RpcManager instance
    """
    global _rpc_manager

    if _rpc_manager is not None:
        return _rpc_manager

    logger.info("Initializing RPC manager...")
    manager = RpcManager(config)

    # Build endpoints for each supported network
    networks_to_configure = ["base-mainnet", "arbitrum-sepolia", "base-sepolia", "arbitrum-mainnet"]

    for network_id in networks_to_configure:
        network = get_network(network_id)

        # Add premium Alchemy endpoint if configured
        if config.alchemy_api_key:
            alchemy_url = _build_alchemy_url(network_id, config.alchemy_api_key)
            if alchemy_url:
                endpoint = RpcEndpoint(
                    url=alchemy_url,
                    priority=EndpointPriority.PREMIUM,
                    provider="alchemy",
                    network_id=network_id,
                    rate_limit_per_second=config.alchemy_rate_limit_per_second,
                )
                manager.add_endpoint(endpoint)

        # Add QuickNode backup endpoint if configured
        if config.quicknode_endpoint:
            # Determine which network this QuickNode endpoint is for
            # QuickNode endpoints are network-specific (URL contains network name)
            quicknode_network = _detect_quicknode_network(config.quicknode_endpoint)

            # Only add the endpoint for the network it actually supports
            if quicknode_network == network_id:
                endpoint = RpcEndpoint(
                    url=config.quicknode_endpoint,
                    priority=EndpointPriority.BACKUP,
                    provider="quicknode",
                    network_id=network_id,
                    rate_limit_per_second=config.quicknode_rate_limit_per_second,
                )
                manager.add_endpoint(endpoint)
                logger.info(f"Added QuickNode backup for {network_id}")

        # Always add public RPC as final fallback
        public_endpoint = RpcEndpoint(
            url=network.rpc_url,
            priority=EndpointPriority.PUBLIC,
            provider="public",
            network_id=network_id,
            rate_limit_per_second=config.public_rate_limit_per_second,
        )
        manager.add_endpoint(public_endpoint)

    _rpc_manager = manager
    logger.info("RPC manager initialized successfully")
    return manager


def _build_alchemy_url(network_id: str, api_key: str) -> Optional[str]:
    """Build Alchemy RPC URL for a given network.

    Args:
        network_id: Network identifier
        api_key: Alchemy API key

    Returns:
        Alchemy RPC URL or None if network not supported
    """
    alchemy_networks = {
        "base-mainnet": f"https://base-mainnet.g.alchemy.com/v2/{api_key}",
        "base-sepolia": f"https://base-sepolia.g.alchemy.com/v2/{api_key}",
        "arbitrum-mainnet": f"https://arb-mainnet.g.alchemy.com/v2/{api_key}",
        "arbitrum-sepolia": f"https://arb-sepolia.g.alchemy.com/v2/{api_key}",
    }
    return alchemy_networks.get(network_id)


def _detect_quicknode_network(quicknode_url: str) -> Optional[str]:
    """Detect which network a QuickNode endpoint is for based on URL.

    QuickNode URLs contain the network name in the subdomain.
    Example: https://something.arbitrum-sepolia.quiknode.pro/...

    Args:
        quicknode_url: QuickNode endpoint URL

    Returns:
        Network ID (e.g., "arbitrum-sepolia") or None if not detected
    """
    url_lower = quicknode_url.lower()

    # Check for network identifiers in URL
    if "arbitrum-sepolia" in url_lower:
        return "arbitrum-sepolia"
    elif "arbitrum-mainnet" in url_lower or "arbitrum.quiknode" in url_lower:
        return "arbitrum-mainnet"
    elif "base-mainnet" in url_lower or "base.quiknode" in url_lower:
        return "base-mainnet"
    elif "base-sepolia" in url_lower:
        return "base-sepolia"

    # If we can't detect, log warning and return None
    logger.warning(f"Could not detect network for QuickNode URL: {quicknode_url[:50]}...")
    return None


class Web3Provider:
    """Manages Web3 instances for different networks."""

    @staticmethod
    def get_web3(network_id: str, custom_rpc_url: Optional[str] = None, config=None) -> Web3:
        """Get or create a Web3 instance for the specified network.

        This method now supports premium RPC with automatic fallback (Sprint 4 Priority 2).
        If config is provided and premium RPC is enabled, it will use RpcManager for
        intelligent endpoint selection with circuit breaker pattern.

        Args:
            network_id: Network identifier (e.g., "base-mainnet", "arbitrum-sepolia")
            custom_rpc_url: Optional custom RPC URL to override (disables premium RPC)
            config: Optional Settings instance for premium RPC support

        Returns:
            Configured Web3 instance

        Raises:
            ValueError: If network_id is not supported
            ConnectionError: If unable to connect to any endpoint
        """
        # Get network configuration
        network = get_network(network_id)

        # If custom RPC URL provided, use direct connection (legacy behavior)
        if custom_rpc_url:
            return Web3Provider._create_web3_direct(network_id, custom_rpc_url)

        # If config provided and premium RPC enabled, use RpcManager
        if config and getattr(config, 'premium_rpc_enabled', False):
            return Web3Provider._create_web3_with_manager(network_id, config)

        # Fall back to default public RPC (legacy behavior)
        return Web3Provider._create_web3_direct(network_id, network.rpc_url)

    @staticmethod
    def _create_web3_direct(network_id: str, rpc_url: str) -> Web3:
        """Create Web3 instance with direct RPC URL (no premium features).

        Args:
            network_id: Network identifier
            rpc_url: RPC endpoint URL

        Returns:
            Configured Web3 instance

        Raises:
            ConnectionError: If connection fails
        """
        network = get_network(network_id)

        # Check cache
        cache_key = f"{network_id}:{rpc_url}"
        if cache_key in _web3_instances:
            logger.debug(f"Using cached Web3 instance for {network_id}")
            return _web3_instances[cache_key]

        # Create new Web3 instance
        logger.info(f"Creating Web3 instance for {network_id} (direct connection)")
        provider = HTTPProvider(
            rpc_url,
            request_kwargs={
                "timeout": 60,  # 60 second timeout
            },
        )

        w3 = Web3(provider)

        # Add PoA middleware for networks that need it
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
    def _create_web3_with_manager(network_id: str, config) -> Web3:
        """Create Web3 instance using RpcManager for intelligent endpoint selection.

        This method uses the RpcManager to automatically select the best available
        endpoint (premium -> backup -> public) with circuit breaker protection.

        Args:
            network_id: Network identifier
            config: Settings instance with RPC configuration

        Returns:
            Configured Web3 instance

        Raises:
            ConnectionError: If all endpoints fail
        """
        # Initialize RPC manager if needed
        manager = _initialize_rpc_manager(config)

        # Get healthy endpoints for this network
        healthy_endpoints = manager.get_healthy_endpoints(network_id)

        if not healthy_endpoints:
            logger.warning(f"No healthy endpoints for {network_id}, falling back to public RPC")
            network = get_network(network_id)
            return Web3Provider._create_web3_direct(network_id, network.rpc_url)

        # Try to use premium endpoint based on gradual rollout
        use_premium = manager.should_use_premium()
        endpoints_to_try = []

        if use_premium:
            # Try premium first, then others
            endpoints_to_try = healthy_endpoints
        else:
            # Skip premium, use backup/public only
            endpoints_to_try = [
                ep for ep in healthy_endpoints
                if ep.priority != EndpointPriority.PREMIUM
            ]
            if not endpoints_to_try:
                endpoints_to_try = healthy_endpoints

        # Try each endpoint until one works
        for endpoint in endpoints_to_try:
            cache_key = f"{network_id}:{endpoint.url}"

            # Check cache first
            if cache_key in _web3_instances:
                logger.debug(
                    f"Using cached Web3 instance for {network_id} "
                    f"({endpoint.provider})"
                )
                return _web3_instances[cache_key]

            # Try to create new connection
            try:
                logger.info(
                    f"Creating Web3 instance for {network_id} via {endpoint.provider} "
                    f"({endpoint.priority})"
                )

                provider = HTTPProvider(
                    endpoint.url,
                    request_kwargs={"timeout": 60},
                )

                w3 = Web3(provider)

                # Add PoA middleware if needed
                network = get_network(network_id)
                if network.is_testnet or network_id in ["base-mainnet", "base-sepolia"]:
                    try:
                        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                    except Exception as e:
                        logger.warning(f"Could not inject PoA middleware: {e}")

                # Verify connection
                if Web3Provider._verify_connection(w3, network):
                    # Success! Cache and return
                    _web3_instances[cache_key] = w3
                    endpoint.record_success(0.0)  # Connection time not measured here
                    logger.info(
                        f"✅ Connected to {network_id} via {endpoint.provider} "
                        f"(Chain ID: {network.chain_id})"
                    )
                    return w3
                else:
                    # Connection failed
                    endpoint.record_failure()
                    continue

            except Exception as e:
                logger.warning(
                    f"Failed to connect to {network_id} via {endpoint.provider}: {e}"
                )
                endpoint.record_failure()
                continue

        # All endpoints failed
        raise ConnectionError(
            f"Failed to connect to {network_id} - all endpoints unavailable"
        )

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
                # Verify chain ID matches (also confirms RPC is responsive)
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
def get_web3(network_id: str, custom_rpc_url: Optional[str] = None, config=None) -> Web3:
    """Get a Web3 instance for the specified network.

    Convenience wrapper around Web3Provider.get_web3().

    Sprint 4 Priority 2: Now supports premium RPC with automatic fallback when
    config is provided and premium_rpc_enabled=true.

    Args:
        network_id: Network identifier
        custom_rpc_url: Optional custom RPC URL (disables premium RPC)
        config: Optional Settings instance for premium RPC support

    Returns:
        Configured Web3 instance
    """
    return Web3Provider.get_web3(network_id, custom_rpc_url, config)


def get_rpc_manager(config) -> Optional[RpcManager]:
    """Get the global RPC manager instance.

    Args:
        config: Settings instance with RPC configuration

    Returns:
        RpcManager instance or None if not initialized
    """
    global _rpc_manager

    if _rpc_manager is None:
        _rpc_manager = _initialize_rpc_manager(config)

    return _rpc_manager


def get_rpc_usage_summary(config) -> Optional[dict]:
    """Get RPC usage summary for cost monitoring.

    Args:
        config: Settings instance with RPC configuration

    Returns:
        Usage summary dict or None if RPC manager not initialized
    """
    manager = get_rpc_manager(config)
    if manager and manager.usage_tracker:
        return manager.usage_tracker.get_daily_summary()
    return None


def check_network_health(network_id: str) -> Dict:
    """Check network connection health.

    Convenience wrapper around Web3Provider.check_connection_health().

    Args:
        network_id: Network identifier

    Returns:
        Dict with health status
    """
    return Web3Provider.check_connection_health(network_id)
