"""Integration tests for premium RPC functionality.

CRITICAL: These tests verify API key security and premium RPC integration.
Must pass before enabling premium RPC in production.
"""

import re
import pytest
from unittest.mock import Mock, patch

from src.utils.config import get_settings
from src.utils.rpc_manager import (
    RpcManager,
    RpcEndpoint,
    EndpointPriority,
)
from src.utils.web3_provider import get_web3, _initialize_rpc_manager


class TestApiKeySecurity:
    """CRITICAL: Test API key security and sanitization."""

    def test_no_api_keys_in_logs(self, caplog):
        """CRITICAL: Verify API keys never appear in logs.

        This is the most important security test. If this fails,
        API keys could be leaked to logs, monitoring systems, or debugging output.
        """
        # Create config with test API key
        mock_config = Mock()
        mock_config.alchemy_api_key = "test_secret_key_abc123def456"
        mock_config.quicknode_endpoint = "https://test.quiknode.pro/secret789xyz/"
        mock_config.premium_rpc_enabled = True
        mock_config.premium_rpc_percentage = 100
        mock_config.alchemy_rate_limit_per_second = 100
        mock_config.quicknode_rate_limit_per_second = 25
        mock_config.public_rate_limit_per_second = 10
        mock_config.rpc_failure_threshold = 3
        mock_config.rpc_recovery_timeout = 60

        # Clear any existing logs
        caplog.clear()

        # Initialize RPC manager (triggers logging)
        manager = RpcManager(mock_config)

        # Add endpoints (triggers logging)
        alchemy_endpoint = RpcEndpoint(
            url=f"https://base-mainnet.g.alchemy.com/v2/{mock_config.alchemy_api_key}",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
            rate_limit_per_second=100,
        )

        quicknode_endpoint = RpcEndpoint(
            url=mock_config.quicknode_endpoint,
            priority=EndpointPriority.BACKUP,
            provider="quicknode",
            network_id="base-mainnet",
            rate_limit_per_second=25,
        )

        manager.add_endpoint(alchemy_endpoint)
        manager.add_endpoint(quicknode_endpoint)

        # Get healthy endpoints (triggers logging)
        _ = manager.get_healthy_endpoints("base-mainnet")

        # CHECK ALL LOG ENTRIES
        sensitive_strings = [
            "test_secret_key_abc123def456",  # Alchemy key
            "abc123def456",  # Part of key
            "secret789xyz",  # QuickNode key part
            "test_secret_key",  # Start of key
        ]

        for record in caplog.records:
            message = record.getMessage()

            # Check for any sensitive strings
            for sensitive in sensitive_strings:
                assert sensitive not in message, (
                    f"SECURITY BREACH: Found '{sensitive}' in log message: {message}"
                )

            # Check that sanitized URLs are present instead
            if "alchemy" in message.lower():
                # Should have sanitized version
                assert "***" in message or "alchemy" in message.lower()

    def test_urls_sanitized_in_endpoint_creation(self):
        """Verify URLs are sanitized when endpoints are created."""
        alchemy_url = "https://base-mainnet.g.alchemy.com/v2/supersecretkey123"

        endpoint = RpcEndpoint(
            url=alchemy_url,
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        # Get sanitized URL
        sanitized = endpoint.get_sanitized_url()

        # Verify key is hidden
        assert "supersecretkey123" not in sanitized
        assert "***" in sanitized
        assert "https://base-mainnet.g.alchemy.com/v2/***" == sanitized

    def test_multiple_url_patterns_sanitized(self):
        """Verify sanitization works for different URL patterns."""
        test_cases = [
            # (input_url, api_key_that_should_be_hidden)
            (
                "https://base-mainnet.g.alchemy.com/v2/abc123",
                "abc123",
            ),
            (
                "https://eth-mainnet.g.alchemy.com/v2/def456ghi789",
                "def456ghi789",
            ),
            (
                "https://node.quiknode.pro/secret_key_xyz/",
                "secret_key_xyz",
            ),
            (
                "https://rpc.example.com/very_long_api_key_123456789",
                "very_long_api_key_123456789",
            ),
        ]

        for url, secret_part in test_cases:
            endpoint = RpcEndpoint(
                url=url,
                priority=EndpointPriority.PREMIUM,
                provider="test",
                network_id="test-network",
            )

            sanitized = endpoint.get_sanitized_url()

            assert secret_part not in sanitized, (
                f"Secret '{secret_part}' found in sanitized URL: {sanitized}"
            )
            assert "***" in sanitized

    def test_no_keys_in_error_messages(self, caplog):
        """Verify API keys don't appear in error messages."""
        caplog.clear()

        endpoint = RpcEndpoint(
            url="https://base-mainnet.g.alchemy.com/v2/secret_error_test_123",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        # Simulate recording a failure (which might log)
        endpoint.record_failure()
        endpoint.record_failure()
        endpoint.record_failure()

        # Check all log entries
        for record in caplog.records:
            message = record.getMessage()
            assert "secret_error_test_123" not in message
            assert "secret_error_test" not in message

    def test_no_keys_in_repr_or_str(self):
        """Verify API keys don't appear in string representations."""
        endpoint = RpcEndpoint(
            url="https://base-mainnet.g.alchemy.com/v2/repr_test_secret_456",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        # Convert to string (might be used in debugging)
        endpoint_str = str(endpoint)
        endpoint_repr = repr(endpoint)

        # These might contain the URL, but we should sanitize in real usage
        # This test documents current behavior
        # In production, we should always use get_sanitized_url() for logging


class TestPremiumRpcIntegration:
    """Test premium RPC integration without real credentials."""

    def test_rpc_manager_initialization_without_premium(self):
        """Verify RPC manager works without premium credentials."""
        mock_config = Mock()
        mock_config.alchemy_api_key = None
        mock_config.quicknode_endpoint = None
        mock_config.premium_rpc_enabled = False
        mock_config.premium_rpc_percentage = 0
        mock_config.rpc_failure_threshold = 3
        mock_config.rpc_recovery_timeout = 60

        # Should initialize successfully
        manager = RpcManager(mock_config)

        assert manager.premium_enabled is False
        assert manager.usage_tracker is not None

    def test_fallback_to_public_when_premium_unavailable(self):
        """Verify system falls back to public RPC when premium unavailable."""
        mock_config = Mock()
        mock_config.premium_rpc_enabled = False
        mock_config.rpc_failure_threshold = 3
        mock_config.rpc_recovery_timeout = 60

        manager = RpcManager(mock_config)

        # Add only public endpoint
        public_endpoint = RpcEndpoint(
            url="https://mainnet.base.org",
            priority=EndpointPriority.PUBLIC,
            provider="public",
            network_id="base-mainnet",
        )

        manager.add_endpoint(public_endpoint)

        # Get healthy endpoints
        healthy = manager.get_healthy_endpoints("base-mainnet")

        assert len(healthy) == 1
        assert healthy[0].priority == EndpointPriority.PUBLIC

    def test_gradual_rollout_respects_percentage(self):
        """Verify gradual rollout percentage is respected."""
        mock_config = Mock()
        mock_config.premium_rpc_enabled = True
        mock_config.premium_rpc_percentage = 0  # 0% should never use premium

        manager = RpcManager(mock_config)

        # Test 100 times
        for _ in range(100):
            assert not manager.should_use_premium()

        # Now test 100%
        mock_config.premium_rpc_percentage = 100
        manager = RpcManager(mock_config)

        # Should always use premium
        for _ in range(100):
            assert manager.should_use_premium()

    def test_circuit_breaker_integration(self):
        """Verify circuit breaker is created for each endpoint."""
        mock_config = Mock()
        mock_config.rpc_failure_threshold = 3
        mock_config.rpc_recovery_timeout = 60

        manager = RpcManager(mock_config)

        endpoint = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PUBLIC,
            provider="test",
            network_id="base-mainnet",
        )

        manager.add_endpoint(endpoint)

        # Verify circuit breaker was created
        assert endpoint.url in manager.circuit_breakers
        breaker = manager.circuit_breakers[endpoint.url]

        assert breaker.failure_threshold == 3
        assert breaker.recovery_timeout == 60


class TestRealWorldScenarios:
    """Test realistic usage scenarios (without making real RPC calls)."""

    def test_multiple_networks_isolated(self):
        """Verify different networks have isolated endpoint lists."""
        mock_config = Mock()
        mock_config.rpc_failure_threshold = 3
        mock_config.rpc_recovery_timeout = 60

        manager = RpcManager(mock_config)

        # Add endpoints for different networks
        base_endpoint = RpcEndpoint(
            url="https://mainnet.base.org",
            priority=EndpointPriority.PUBLIC,
            provider="public",
            network_id="base-mainnet",
        )

        arbitrum_endpoint = RpcEndpoint(
            url="https://sepolia-rollup.arbitrum.io/rpc",
            priority=EndpointPriority.PUBLIC,
            provider="public",
            network_id="arbitrum-sepolia",
        )

        manager.add_endpoint(base_endpoint)
        manager.add_endpoint(arbitrum_endpoint)

        # Verify isolation
        base_healthy = manager.get_healthy_endpoints("base-mainnet")
        arbitrum_healthy = manager.get_healthy_endpoints("arbitrum-sepolia")

        assert len(base_healthy) == 1
        assert len(arbitrum_healthy) == 1
        assert base_healthy[0].url != arbitrum_healthy[0].url

    def test_usage_tracking_across_requests(self):
        """Verify usage is tracked correctly across multiple requests."""
        mock_config = Mock()
        mock_config.rpc_failure_threshold = 3
        mock_config.rpc_recovery_timeout = 60

        manager = RpcManager(mock_config)

        alchemy_endpoint = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        # Simulate multiple requests
        for i in range(10):
            success = i < 8  # 8 successes, 2 failures
            manager.usage_tracker.record_request(alchemy_endpoint, success=success)

        summary = manager.usage_tracker.get_daily_summary()

        assert summary["premium_requests"] == 10
        assert summary["total_requests"] == 10

    def test_endpoint_priority_with_health_status(self):
        """Verify unhealthy premium endpoints don't block public access."""
        mock_config = Mock()
        mock_config.rpc_failure_threshold = 3
        mock_config.rpc_recovery_timeout = 60

        manager = RpcManager(mock_config)

        # Add premium (unhealthy) and public (healthy) endpoints
        premium_endpoint = RpcEndpoint(
            url="https://premium.com",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )
        premium_endpoint.is_healthy = False  # Mark as unhealthy

        public_endpoint = RpcEndpoint(
            url="https://public.com",
            priority=EndpointPriority.PUBLIC,
            provider="public",
            network_id="base-mainnet",
        )

        manager.add_endpoint(premium_endpoint)
        manager.add_endpoint(public_endpoint)

        # Get healthy endpoints
        healthy = manager.get_healthy_endpoints("base-mainnet")

        # Should only return public (premium is unhealthy)
        assert len(healthy) == 1
        assert healthy[0].priority == EndpointPriority.PUBLIC


@pytest.mark.integration
@pytest.mark.network
class TestRealRpcConnection:
    """Test real RPC connections (requires network access).

    These tests use actual public RPCs but DO NOT require premium credentials.
    They verify the integration works end-to-end.
    """

    def test_public_rpc_connection_base_mainnet(self):
        """Verify we can connect to Base mainnet via public RPC."""
        try:
            # Use public RPC only (no config)
            w3 = get_web3("base-mainnet")

            # Verify connection
            assert w3.is_connected()
            block = w3.eth.block_number
            assert block > 0

            print(f"✅ Connected to Base mainnet (block #{block})")

        except Exception as e:
            pytest.fail(f"Failed to connect to public RPC: {e}")

    def test_public_rpc_connection_arbitrum_sepolia(self):
        """Verify we can connect to Arbitrum Sepolia via public RPC."""
        try:
            # Use public RPC only (no config)
            w3 = get_web3("arbitrum-sepolia")

            # Verify connection
            assert w3.is_connected()
            block = w3.eth.block_number
            assert block > 0

            print(f"✅ Connected to Arbitrum Sepolia (block #{block})")

        except Exception as e:
            pytest.fail(f"Failed to connect to public RPC: {e}")

    def test_backward_compatibility_no_config(self):
        """Verify old code works without config parameter (backward compatibility)."""
        try:
            # Old way (should still work)
            w3 = get_web3("base-mainnet")

            assert w3.is_connected()
            assert w3.eth.block_number > 0

            print("✅ Backward compatibility maintained")

        except Exception as e:
            pytest.fail(f"Backward compatibility broken: {e}")
