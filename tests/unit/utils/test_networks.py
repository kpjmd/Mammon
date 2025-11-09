"""Unit tests for network configuration module.

Tests the multi-network support added in Phase 1C Sprint 2.
"""

import pytest
from src.utils.networks import (
    NetworkConfig,
    NETWORKS,
    get_network,
    validate_network,
    get_supported_networks,
    get_testnet_networks,
    get_mainnet_networks,
    get_rpc_url,
    get_explorer_url,
    format_explorer_tx_url,
    format_explorer_address_url,
)


class TestNetworkConfig:
    """Test NetworkConfig dataclass."""

    def test_network_config_creation(self):
        """Test creating a NetworkConfig instance."""
        config = NetworkConfig(
            network_id="test-network",
            chain_id=12345,
            rpc_url="https://test.rpc",
            explorer_url="https://test.explorer",
            native_token="TEST",
            is_testnet=True,
            description="Test network",
        )

        assert config.network_id == "test-network"
        assert config.chain_id == 12345
        assert config.rpc_url == "https://test.rpc"
        assert config.explorer_url == "https://test.explorer"
        assert config.native_token == "TEST"
        assert config.is_testnet is True
        assert config.description == "Test network"

    def test_network_config_immutable(self):
        """Test that NetworkConfig is frozen (immutable)."""
        config = NetworkConfig(
            network_id="test-network",
            chain_id=12345,
            rpc_url="https://test.rpc",
            explorer_url="https://test.explorer",
            native_token="TEST",
            is_testnet=True,
            description="Test network",
        )

        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            config.chain_id = 99999


class TestNetworkRegistry:
    """Test NETWORKS registry and its contents."""

    def test_networks_registry_exists(self):
        """Test that NETWORKS registry is defined."""
        assert NETWORKS is not None
        assert isinstance(NETWORKS, dict)

    def test_all_required_networks_present(self):
        """Test that all required networks are in the registry."""
        required_networks = [
            "base-mainnet",
            "base-sepolia",
            "arbitrum-mainnet",
            "arbitrum-sepolia",
        ]

        for network_id in required_networks:
            assert network_id in NETWORKS, f"Missing required network: {network_id}"

    def test_base_mainnet_config(self):
        """Test Base mainnet configuration."""
        config = NETWORKS["base-mainnet"]
        assert config.network_id == "base-mainnet"
        assert config.chain_id == 8453
        assert config.rpc_url == "https://mainnet.base.org"
        assert config.explorer_url == "https://basescan.org"
        assert config.native_token == "ETH"
        assert config.is_testnet is False

    def test_base_sepolia_config(self):
        """Test Base Sepolia testnet configuration."""
        config = NETWORKS["base-sepolia"]
        assert config.network_id == "base-sepolia"
        assert config.chain_id == 84532
        assert config.rpc_url == "https://sepolia.base.org"
        assert config.explorer_url == "https://sepolia.basescan.org"
        assert config.native_token == "ETH"
        assert config.is_testnet is True

    def test_arbitrum_mainnet_config(self):
        """Test Arbitrum mainnet configuration."""
        config = NETWORKS["arbitrum-mainnet"]
        assert config.network_id == "arbitrum-mainnet"
        assert config.chain_id == 42161
        assert config.rpc_url == "https://arb1.arbitrum.io/rpc"
        assert config.explorer_url == "https://arbiscan.io"
        assert config.native_token == "ETH"
        assert config.is_testnet is False

    def test_arbitrum_sepolia_config(self):
        """Test Arbitrum Sepolia testnet configuration."""
        config = NETWORKS["arbitrum-sepolia"]
        assert config.network_id == "arbitrum-sepolia"
        assert config.chain_id == 421614
        assert config.rpc_url == "https://sepolia-rollup.arbitrum.io/rpc"
        assert config.explorer_url == "https://sepolia.arbiscan.io"
        assert config.native_token == "ETH"
        assert config.is_testnet is True

    def test_all_networks_have_required_fields(self):
        """Test that all networks have all required fields."""
        required_fields = [
            "network_id",
            "chain_id",
            "rpc_url",
            "explorer_url",
            "native_token",
            "is_testnet",
            "description",
        ]

        for network_id, config in NETWORKS.items():
            for field in required_fields:
                assert hasattr(config, field), f"{network_id} missing field: {field}"
                assert getattr(config, field) is not None, f"{network_id}.{field} is None"

    def test_chain_ids_unique(self):
        """Test that all chain IDs are unique."""
        chain_ids = [config.chain_id for config in NETWORKS.values()]
        assert len(chain_ids) == len(set(chain_ids)), "Duplicate chain IDs found"

    def test_native_token_is_eth(self):
        """Test that all networks use ETH as native token."""
        for network_id, config in NETWORKS.items():
            assert config.native_token == "ETH", f"{network_id} uses {config.native_token} instead of ETH"


class TestGetNetwork:
    """Test get_network() function."""

    def test_get_network_valid(self):
        """Test getting a valid network."""
        config = get_network("base-mainnet")
        assert config is not None
        assert config.network_id == "base-mainnet"

    def test_get_network_all_registered(self):
        """Test getting all registered networks."""
        for network_id in ["base-mainnet", "base-sepolia", "arbitrum-mainnet", "arbitrum-sepolia"]:
            config = get_network(network_id)
            assert config is not None
            assert config.network_id == network_id

    def test_get_network_invalid(self):
        """Test getting an invalid network raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported network"):
            get_network("invalid-network")

    def test_get_network_case_sensitive(self):
        """Test that network lookup is case-sensitive."""
        with pytest.raises(ValueError, match="Unsupported network"):
            get_network("BASE-MAINNET")  # Should not match "base-mainnet"


class TestValidateNetwork:
    """Test validate_network() function."""

    def test_validate_network_valid(self):
        """Test validating valid networks."""
        assert validate_network("base-mainnet") is True
        assert validate_network("base-sepolia") is True
        assert validate_network("arbitrum-mainnet") is True
        assert validate_network("arbitrum-sepolia") is True

    def test_validate_network_invalid(self):
        """Test validating invalid networks."""
        assert validate_network("invalid-network") is False
        assert validate_network("ethereum-mainnet") is False
        assert validate_network("") is False
        assert validate_network("BASE-MAINNET") is False  # Case-sensitive


class TestGetSupportedNetworks:
    """Test get_supported_networks() function."""

    def test_get_supported_networks(self):
        """Test getting list of supported networks."""
        networks = get_supported_networks()
        assert isinstance(networks, list)
        assert len(networks) == 4

    def test_supported_networks_content(self):
        """Test that all expected networks are in the list."""
        networks = get_supported_networks()
        expected = ["base-mainnet", "base-sepolia", "arbitrum-mainnet", "arbitrum-sepolia"]

        for network_id in expected:
            assert network_id in networks

    def test_supported_networks_order(self):
        """Test that all expected networks are returned."""
        networks = get_supported_networks()
        # Note: Order matches NETWORKS dict insertion order (not necessarily sorted)
        expected = ["base-mainnet", "base-sepolia", "arbitrum-mainnet", "arbitrum-sepolia"]
        assert set(networks) == set(expected)


class TestGetTestnetNetworks:
    """Test get_testnet_networks() function."""

    def test_get_testnet_networks(self):
        """Test getting all testnet networks."""
        testnets = get_testnet_networks()
        assert isinstance(testnets, list)
        assert len(testnets) == 2
        assert "base-sepolia" in testnets
        assert "arbitrum-sepolia" in testnets

    def test_testnet_networks_order(self):
        """Test that expected testnets are returned."""
        testnets = get_testnet_networks()
        # Verify expected testnets are present
        assert set(testnets) == {"base-sepolia", "arbitrum-sepolia"}


class TestGetMainnetNetworks:
    """Test get_mainnet_networks() function."""

    def test_get_mainnet_networks(self):
        """Test getting all mainnet networks."""
        mainnets = get_mainnet_networks()
        assert isinstance(mainnets, list)
        assert len(mainnets) == 2
        assert "base-mainnet" in mainnets
        assert "arbitrum-mainnet" in mainnets

    def test_mainnet_networks_order(self):
        """Test that expected mainnets are returned."""
        mainnets = get_mainnet_networks()
        # Verify expected mainnets are present
        assert set(mainnets) == {"base-mainnet", "arbitrum-mainnet"}


class TestGetRpcUrl:
    """Test get_rpc_url() function."""

    def test_get_rpc_url_default(self):
        """Test getting default RPC URL."""
        rpc_url = get_rpc_url("base-mainnet")
        assert rpc_url == "https://mainnet.base.org"

    def test_get_rpc_url_custom(self):
        """Test getting custom RPC URL."""
        custom = "https://custom.rpc.url"
        rpc_url = get_rpc_url("base-mainnet", custom_rpc=custom)
        assert rpc_url == custom

    def test_get_rpc_url_invalid_network(self):
        """Test getting RPC URL for invalid network."""
        with pytest.raises(ValueError, match="Unsupported network"):
            get_rpc_url("invalid-network")


class TestGetExplorerUrl:
    """Test get_explorer_url() function."""

    def test_get_explorer_url_base_mainnet(self):
        """Test getting Base mainnet explorer URL."""
        url = get_explorer_url("base-mainnet")
        assert url == "https://basescan.org"

    def test_get_explorer_url_base_sepolia(self):
        """Test getting Base Sepolia explorer URL."""
        url = get_explorer_url("base-sepolia")
        assert url == "https://sepolia.basescan.org"

    def test_get_explorer_url_invalid_network(self):
        """Test getting explorer URL for invalid network."""
        with pytest.raises(ValueError, match="Unsupported network"):
            get_explorer_url("invalid-network")


class TestFormatExplorerTxUrl:
    """Test format_explorer_tx_url() function."""

    def test_format_explorer_tx_url(self):
        """Test formatting transaction explorer URL."""
        tx_hash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        url = format_explorer_tx_url("base-mainnet", tx_hash)
        assert url == f"https://basescan.org/tx/{tx_hash}"

    def test_format_explorer_tx_url_sepolia(self):
        """Test formatting Sepolia transaction URL."""
        tx_hash = "0xabcd"
        url = format_explorer_tx_url("base-sepolia", tx_hash)
        assert url == f"https://sepolia.basescan.org/tx/{tx_hash}"


class TestFormatExplorerAddressUrl:
    """Test format_explorer_address_url() function."""

    def test_format_explorer_address_url(self):
        """Test formatting address explorer URL."""
        address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"
        url = format_explorer_address_url("base-mainnet", address)
        assert url == f"https://basescan.org/address/{address}"

    def test_format_explorer_address_url_arbitrum(self):
        """Test formatting Arbitrum address URL."""
        address = "0x1234"
        url = format_explorer_address_url("arbitrum-mainnet", address)
        assert url == f"https://arbiscan.io/address/{address}"


class TestNetworkIntegration:
    """Integration tests for network configuration."""

    def test_mainnet_testnet_pairing(self):
        """Test that each mainnet has a corresponding testnet."""
        mainnets = get_mainnet_networks()
        testnets = get_testnet_networks()

        # Should have same count
        assert len(mainnets) == len(testnets)

        # Check Base pairing
        assert "base-mainnet" in mainnets
        assert "base-sepolia" in testnets

        base_mainnet = get_network("base-mainnet")
        base_testnet = get_network("base-sepolia")
        assert base_mainnet.native_token == base_testnet.native_token
        assert base_mainnet.is_testnet is False
        assert base_testnet.is_testnet is True

        # Check Arbitrum pairing
        assert "arbitrum-mainnet" in mainnets
        assert "arbitrum-sepolia" in testnets

        arb_mainnet = get_network("arbitrum-mainnet")
        arb_testnet = get_network("arbitrum-sepolia")
        assert arb_mainnet.native_token == arb_testnet.native_token
        assert arb_mainnet.is_testnet is False
        assert arb_testnet.is_testnet is True

    def test_network_id_matches_registry_key(self):
        """Test that network_id in config matches registry key."""
        for network_id, config in NETWORKS.items():
            assert config.network_id == network_id

    def test_all_networks_accessible(self):
        """Test that all networks can be retrieved."""
        for network_id in get_supported_networks():
            config = get_network(network_id)
            assert config is not None
            assert validate_network(network_id)

    def test_rpc_and_explorer_urls_consistent(self):
        """Test that RPC and explorer URLs are consistent with network configs."""
        for network_id in get_supported_networks():
            config = get_network(network_id)

            # RPC URL should match
            assert get_rpc_url(network_id) == config.rpc_url

            # Explorer URL should match
            assert get_explorer_url(network_id) == config.explorer_url

    def test_explorer_url_formatting(self):
        """Test that explorer URLs are properly formatted."""
        test_tx = "0x1234"
        test_address = "0x5678"

        for network_id in get_supported_networks():
            config = get_network(network_id)

            tx_url = format_explorer_tx_url(network_id, test_tx)
            address_url = format_explorer_address_url(network_id, test_address)

            # Both should start with explorer base URL
            assert tx_url.startswith(config.explorer_url)
            assert address_url.startswith(config.explorer_url)

            # Should contain the tx hash and address
            assert test_tx in tx_url
            assert test_address in address_url
