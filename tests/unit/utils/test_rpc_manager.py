"""Unit tests for RPC Manager components.

Tests circuit breaker, rate limiting, endpoint health tracking,
and URL sanitization for production readiness.
"""

import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

import pytest

from src.utils.rpc_manager import (
    CircuitBreaker,
    CircuitState,
    RpcEndpoint,
    EndpointPriority,
    RpcManager,
    RpcUsageTracker,
    CircuitOpenError,
)


class TestCircuitBreaker:
    """Test circuit breaker pattern implementation."""

    def test_initial_state_is_closed(self):
        """Verify circuit breaker starts in CLOSED state."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        assert breaker.state == CircuitState.CLOSED
        assert not breaker.is_open
        assert breaker.failures == 0

    def test_opens_after_threshold_failures(self):
        """Verify circuit opens after failure threshold reached."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        # Record 2 failures - should stay closed
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED
        assert not breaker.is_open

        # 3rd failure should open circuit
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open

    def test_records_opened_timestamp(self):
        """Verify circuit records when it opened."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        before = datetime.now(timezone.utc)

        # Trigger circuit open
        for _ in range(3):
            breaker.record_failure()

        after = datetime.now(timezone.utc)

        assert breaker.opened_at is not None
        assert before <= breaker.opened_at <= after

    def test_transitions_to_half_open_after_timeout(self):
        """Verify automatic recovery to HALF_OPEN after timeout."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)

        # Open the circuit
        for _ in range(3):
            breaker.record_failure()

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(1.1)

        # Check should transition to HALF_OPEN
        is_open = breaker.is_open  # Property checks timeout

        assert breaker.state == CircuitState.HALF_OPEN
        assert not is_open

    def test_closes_on_success_in_half_open(self):
        """Verify circuit closes after successful recovery."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)

        # Open the circuit
        for _ in range(3):
            breaker.record_failure()

        # Wait and transition to HALF_OPEN
        time.sleep(1.1)
        _ = breaker.is_open  # Trigger transition

        assert breaker.state == CircuitState.HALF_OPEN

        # Success should close circuit
        breaker.record_success()

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failures == 0

    def test_reopens_on_failure_in_half_open(self):
        """Verify circuit reopens if recovery fails."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)

        # Open the circuit
        for _ in range(3):
            breaker.record_failure()

        # Wait and transition to HALF_OPEN
        time.sleep(1.1)
        _ = breaker.is_open

        assert breaker.state == CircuitState.HALF_OPEN

        # Failure should reopen circuit
        breaker.record_failure()

        assert breaker.state == CircuitState.OPEN

    def test_success_resets_failures_when_closed(self):
        """Verify successful requests reset failure counter."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        # Record some failures
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failures == 2

        # Success should reset counter
        breaker.record_success()
        assert breaker.failures == 0
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_call_raises_when_open(self):
        """Verify circuit breaker blocks calls when open."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        # Open the circuit
        for _ in range(3):
            breaker.record_failure()

        # Attempt to call should raise
        async def dummy_operation():
            return "success"

        with pytest.raises(CircuitOpenError):
            await breaker.call(dummy_operation)

    @pytest.mark.asyncio
    async def test_call_executes_when_closed(self):
        """Verify circuit breaker allows calls when closed."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        async def dummy_operation():
            return "success"

        result = await breaker.call(dummy_operation)
        assert result == "success"
        assert breaker.failures == 0


class TestRpcEndpoint:
    """Test RPC endpoint configuration and state tracking."""

    def test_endpoint_initialization(self):
        """Verify endpoint initializes with correct defaults."""
        endpoint = RpcEndpoint(
            url="https://mainnet.base.org",
            priority=EndpointPriority.PUBLIC,
            provider="public",
            network_id="base-mainnet",
            rate_limit_per_second=10,
        )

        assert endpoint.url == "https://mainnet.base.org"
        assert endpoint.priority == EndpointPriority.PUBLIC
        assert endpoint.provider == "public"
        assert endpoint.is_healthy
        assert endpoint.consecutive_failures == 0
        assert endpoint.latency_ms == 0.0

    def test_rate_limit_per_second(self):
        """Verify per-second rate limiting works."""
        endpoint = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PUBLIC,
            provider="test",
            network_id="test-network",
            rate_limit_per_second=3,
        )

        # Should allow 3 requests
        for _ in range(3):
            assert endpoint.can_make_request()
            endpoint.record_request()

        # 4th request should be blocked
        assert not endpoint.can_make_request()

    def test_rate_limit_resets_after_second(self):
        """Verify rate limit counter resets after 1 second."""
        endpoint = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PUBLIC,
            provider="test",
            network_id="test-network",
            rate_limit_per_second=3,
        )

        # Use up all requests
        for _ in range(3):
            endpoint.record_request()

        assert not endpoint.can_make_request()

        # Wait for reset
        time.sleep(1.1)

        # Should allow requests again
        assert endpoint.can_make_request()

    def test_health_tracking(self):
        """Verify endpoint health tracking."""
        endpoint = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PUBLIC,
            provider="test",
            network_id="test-network",
        )

        # Start healthy
        assert endpoint.is_healthy

        # Record some failures
        endpoint.record_failure()
        assert endpoint.consecutive_failures == 1
        assert endpoint.is_healthy  # Still healthy

        endpoint.record_failure()
        assert endpoint.consecutive_failures == 2
        assert endpoint.is_healthy  # Still healthy

        # 3rd failure marks unhealthy
        endpoint.record_failure()
        assert endpoint.consecutive_failures == 3
        assert not endpoint.is_healthy

    def test_success_resets_health(self):
        """Verify success resets health tracking."""
        endpoint = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PUBLIC,
            provider="test",
            network_id="test-network",
        )

        # Mark unhealthy
        for _ in range(3):
            endpoint.record_failure()

        assert not endpoint.is_healthy
        assert endpoint.consecutive_failures == 3

        # Success should restore health
        endpoint.record_success(latency_ms=50.0)

        assert endpoint.is_healthy
        assert endpoint.consecutive_failures == 0
        assert endpoint.latency_ms == 50.0

    def test_latency_tracking_exponential_moving_average(self):
        """Verify latency uses exponential moving average."""
        endpoint = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PUBLIC,
            provider="test",
            network_id="test-network",
        )

        # First success sets initial latency
        endpoint.record_success(latency_ms=100.0)
        assert endpoint.latency_ms == 100.0

        # Second success applies EMA (alpha=0.3)
        endpoint.record_success(latency_ms=200.0)
        expected = 0.3 * 200.0 + 0.7 * 100.0
        assert abs(endpoint.latency_ms - expected) < 0.01

    def test_url_sanitization_alchemy(self):
        """Verify Alchemy URL sanitization."""
        endpoint = RpcEndpoint(
            url="https://base-mainnet.g.alchemy.com/v2/abc123def456",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        sanitized = endpoint.get_sanitized_url()

        assert "abc123def456" not in sanitized
        assert "***" in sanitized
        assert sanitized == "https://base-mainnet.g.alchemy.com/v2/***"

    def test_url_sanitization_quicknode(self):
        """Verify QuickNode URL sanitization."""
        endpoint = RpcEndpoint(
            url="https://some-endpoint.quiknode.pro/secret_key_123/",
            priority=EndpointPriority.BACKUP,
            provider="quicknode",
            network_id="base-mainnet",
        )

        sanitized = endpoint.get_sanitized_url()

        assert "secret_key_123" not in sanitized
        assert "***" in sanitized

    def test_url_sanitization_generic(self):
        """Verify generic URL sanitization for long keys."""
        endpoint = RpcEndpoint(
            url="https://rpc.example.com/very_long_api_key_that_should_be_hidden",
            priority=EndpointPriority.PUBLIC,
            provider="custom",
            network_id="test-network",
        )

        sanitized = endpoint.get_sanitized_url()

        assert "very_long_api_key_that_should_be_hidden" not in sanitized
        assert "***" in sanitized


class TestRpcUsageTracker:
    """Test RPC usage tracking for cost monitoring."""

    def test_initialization(self):
        """Verify usage tracker initializes correctly."""
        tracker = RpcUsageTracker()

        assert len(tracker.daily_usage) == 0
        assert len(tracker.monthly_usage) == 0
        assert len(tracker.daily_failures) == 0

    def test_records_requests_by_provider(self):
        """Verify requests are tracked per provider."""
        tracker = RpcUsageTracker()

        endpoint_alchemy = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        endpoint_public = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PUBLIC,
            provider="public",
            network_id="base-mainnet",
        )

        # Record requests
        tracker.record_request(endpoint_alchemy, success=True)
        tracker.record_request(endpoint_alchemy, success=True)
        tracker.record_request(endpoint_public, success=True)

        assert tracker.daily_usage["alchemy_premium"] == 2
        assert tracker.daily_usage["public_public"] == 1

    def test_records_failures_separately(self):
        """Verify failures are tracked separately."""
        tracker = RpcUsageTracker()

        endpoint = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        tracker.record_request(endpoint, success=True)
        tracker.record_request(endpoint, success=False)
        tracker.record_request(endpoint, success=False)

        assert tracker.daily_usage["alchemy_premium"] == 3
        assert tracker.daily_failures["alchemy_premium"] == 2

    def test_daily_summary_format(self):
        """Verify daily summary has correct format."""
        tracker = RpcUsageTracker()

        endpoint_alchemy = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        # Record some requests
        for _ in range(100):
            tracker.record_request(endpoint_alchemy, success=True)

        summary = tracker.get_daily_summary()

        assert summary["event_type"] == "rpc_usage_summary"
        assert summary["period"] == "daily"
        assert summary["premium_requests"] == 100
        assert summary["total_requests"] == 100
        assert "alchemy_usage_percent" in summary
        assert "approaching_limit" in summary
        assert summary["in_free_tier"] is True

    def test_approaching_limit_detection(self):
        """Verify detection of approaching rate limits."""
        tracker = RpcUsageTracker()

        endpoint = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        # Simulate high usage (85% of daily limit)
        # Alchemy free tier: 300M/month = 10M/day
        daily_limit = 10_000_000
        high_usage = int(daily_limit * 0.85)

        for _ in range(high_usage):
            tracker.daily_usage["alchemy_premium"] += 1

        summary = tracker.get_daily_summary()

        # Should detect approaching limit (>80%)
        assert summary["approaching_limit"] is True
        assert summary["alchemy_usage_percent"] > 80

    def test_reset_daily_usage(self):
        """Verify daily usage can be reset."""
        tracker = RpcUsageTracker()

        endpoint = RpcEndpoint(
            url="https://test.com",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        # Add some usage
        for _ in range(100):
            tracker.record_request(endpoint, success=True)

        assert tracker.daily_usage["alchemy_premium"] == 100

        # Reset
        tracker.reset_daily_usage()

        assert len(tracker.daily_usage) == 0
        assert len(tracker.daily_failures) == 0


class TestRpcManager:
    """Test RPC manager orchestration."""

    def test_initialization(self):
        """Verify RPC manager initializes correctly."""
        mock_config = Mock()
        mock_config.premium_rpc_enabled = False
        mock_config.premium_rpc_percentage = 10
        mock_config.rpc_failure_threshold = 3
        mock_config.rpc_recovery_timeout = 60

        manager = RpcManager(mock_config)

        assert manager.config == mock_config
        assert manager.premium_enabled is False
        assert manager.premium_percentage == 10
        assert isinstance(manager.usage_tracker, RpcUsageTracker)

    def test_adds_endpoints(self):
        """Verify endpoints can be added to manager."""
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

        assert "base-mainnet" in manager.endpoints
        assert len(manager.endpoints["base-mainnet"]) == 1
        assert endpoint.url in manager.circuit_breakers

    def test_get_healthy_endpoints_prioritization(self):
        """Verify endpoints are returned in priority order."""
        mock_config = Mock()
        mock_config.rpc_failure_threshold = 3
        mock_config.rpc_recovery_timeout = 60

        manager = RpcManager(mock_config)

        # Add endpoints in random order
        public_ep = RpcEndpoint(
            url="https://public.com",
            priority=EndpointPriority.PUBLIC,
            provider="public",
            network_id="base-mainnet",
        )

        premium_ep = RpcEndpoint(
            url="https://premium.com",
            priority=EndpointPriority.PREMIUM,
            provider="alchemy",
            network_id="base-mainnet",
        )

        backup_ep = RpcEndpoint(
            url="https://backup.com",
            priority=EndpointPriority.BACKUP,
            provider="quicknode",
            network_id="base-mainnet",
        )

        manager.add_endpoint(public_ep)
        manager.add_endpoint(premium_ep)
        manager.add_endpoint(backup_ep)

        healthy = manager.get_healthy_endpoints("base-mainnet")

        # Should be in priority order: premium, backup, public
        assert len(healthy) == 3
        assert healthy[0].priority == EndpointPriority.PREMIUM
        assert healthy[1].priority == EndpointPriority.BACKUP
        assert healthy[2].priority == EndpointPriority.PUBLIC

    def test_filters_unhealthy_endpoints(self):
        """Verify unhealthy endpoints are filtered out."""
        mock_config = Mock()
        mock_config.rpc_failure_threshold = 3
        mock_config.rpc_recovery_timeout = 60

        manager = RpcManager(mock_config)

        endpoint1 = RpcEndpoint(
            url="https://test1.com",
            priority=EndpointPriority.PUBLIC,
            provider="test1",
            network_id="base-mainnet",
        )

        endpoint2 = RpcEndpoint(
            url="https://test2.com",
            priority=EndpointPriority.PUBLIC,
            provider="test2",
            network_id="base-mainnet",
        )

        manager.add_endpoint(endpoint1)
        manager.add_endpoint(endpoint2)

        # Mark endpoint1 as unhealthy
        endpoint1.is_healthy = False

        healthy = manager.get_healthy_endpoints("base-mainnet")

        assert len(healthy) == 1
        assert healthy[0].url == "https://test2.com"

    def test_gradual_rollout_logic(self):
        """Verify gradual rollout percentage works statistically."""
        mock_config = Mock()
        mock_config.premium_rpc_enabled = True
        mock_config.premium_rpc_percentage = 30

        manager = RpcManager(mock_config)

        # Run 1000 times and check distribution
        premium_count = 0
        for _ in range(1000):
            if manager.should_use_premium():
                premium_count += 1

        # Should be approximately 30% (allow 5% variance)
        percentage = (premium_count / 1000) * 100
        assert 25 <= percentage <= 35

    def test_disabled_premium_never_uses_premium(self):
        """Verify premium RPC is never used when disabled."""
        mock_config = Mock()
        mock_config.premium_rpc_enabled = False
        mock_config.premium_rpc_percentage = 100

        manager = RpcManager(mock_config)

        # Even with 100% rollout, should never use premium when disabled
        for _ in range(100):
            assert not manager.should_use_premium()
