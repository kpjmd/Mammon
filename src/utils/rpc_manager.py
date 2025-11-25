"""RPC endpoint management with circuit breaker pattern and rate limiting.

This module provides sophisticated RPC endpoint orchestration for MAMMON:
- Circuit breaker pattern to prevent hammering failed endpoints
- Rate limiting to stay within provider limits
- Automatic failover with health monitoring
- Cost tracking and usage analytics
- Gradual rollout for safe premium RPC adoption
"""

import asyncio
import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class EndpointPriority(str, Enum):
    """Priority levels for RPC endpoints."""
    PREMIUM = "premium"
    BACKUP = "backup"
    PUBLIC = "public"


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failures detected, endpoint disabled
    HALF_OPEN = "half_open"  # Testing if endpoint recovered


@dataclass
class RpcEndpoint:
    """Configuration and state for a single RPC endpoint.

    Attributes:
        url: Full RPC endpoint URL (may contain API key)
        priority: Endpoint priority (premium/backup/public)
        provider: Provider name (alchemy/quicknode/public)
        network_id: Network identifier (e.g., "base-mainnet")
        rate_limit_per_second: Maximum requests per second
        rate_limit_per_minute: Maximum requests per minute

    State tracking:
        last_success: Timestamp of last successful request
        consecutive_failures: Count of consecutive failures
        latency_ms: Average latency in milliseconds
        is_healthy: Health status based on recent failures
        requests_this_second: Request count in current second
        requests_this_minute: Request count in current minute
        last_request_time: Timestamp of last request
    """
    url: str
    priority: EndpointPriority
    provider: str
    network_id: str
    rate_limit_per_second: int = 100
    rate_limit_per_minute: int = 6000

    # Health tracking
    last_success: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    consecutive_failures: int = 0
    latency_ms: float = 0.0
    is_healthy: bool = True

    # Rate limiting
    requests_this_second: int = 0
    requests_this_minute: int = 0
    last_request_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def can_make_request(self) -> bool:
        """Check if endpoint is within rate limits.

        Returns:
            True if request can be made, False if rate limited
        """
        now = datetime.now(timezone.utc)

        # Reset second counter if >= 1 second elapsed
        if (now - self.last_request_time).total_seconds() >= 1.0:
            self.requests_this_second = 0

        # Reset minute counter if >= 60 seconds elapsed
        if (now - self.last_request_time).total_seconds() >= 60.0:
            self.requests_this_minute = 0

        # Check both limits
        if self.requests_this_second >= self.rate_limit_per_second:
            logger.debug(
                f"Rate limit reached for {self.provider}: "
                f"{self.requests_this_second}/{self.rate_limit_per_second} per second"
            )
            return False

        if self.requests_this_minute >= self.rate_limit_per_minute:
            logger.debug(
                f"Rate limit reached for {self.provider}: "
                f"{self.requests_this_minute}/{self.rate_limit_per_minute} per minute"
            )
            return False

        return True

    def record_request(self):
        """Record a request for rate limiting."""
        now = datetime.now(timezone.utc)

        # Reset counters if needed
        if (now - self.last_request_time).total_seconds() >= 1.0:
            self.requests_this_second = 0
        if (now - self.last_request_time).total_seconds() >= 60.0:
            self.requests_this_minute = 0

        # Increment counters
        self.requests_this_second += 1
        self.requests_this_minute += 1
        self.last_request_time = now

    def record_success(self, latency_ms: float):
        """Record a successful request.

        Args:
            latency_ms: Request latency in milliseconds
        """
        self.last_success = datetime.now(timezone.utc)
        self.consecutive_failures = 0
        self.is_healthy = True

        # Exponential moving average for latency
        alpha = 0.3  # Smoothing factor
        if self.latency_ms == 0:
            self.latency_ms = latency_ms
        else:
            self.latency_ms = alpha * latency_ms + (1 - alpha) * self.latency_ms

    def record_failure(self):
        """Record a failed request."""
        self.consecutive_failures += 1

        # Mark unhealthy after 3 consecutive failures
        if self.consecutive_failures >= 3:
            self.is_healthy = False
            logger.warning(
                f"Endpoint {self.provider} marked unhealthy after "
                f"{self.consecutive_failures} failures"
            )

    def get_sanitized_url(self) -> str:
        """Get URL with API key sanitized for logging.

        Returns:
            URL with API key replaced by ***
        """
        # Pattern: /v2/api_key or /api_key at end
        url = self.url

        # Alchemy pattern: /v2/{api_key}
        if '/v2/' in url:
            base, key = url.rsplit('/v2/', 1)
            return f"{base}/v2/***"

        # QuickNode pattern: .pro/{api_key}/
        if '.pro/' in url:
            parts = url.split('.pro/')
            return f"{parts[0]}.pro/***/..."

        # Generic: replace last path segment if it looks like an API key
        parts = url.rsplit('/', 1)
        if len(parts) == 2 and len(parts[1]) > 20:
            return f"{parts[0]}/***"

        return url


class CircuitBreaker:
    """Circuit breaker to prevent hammering failed endpoints.

    States:
        CLOSED: Normal operation, requests allowed
        OPEN: Too many failures, requests blocked
        HALF_OPEN: Testing if endpoint recovered

    Attributes:
        failure_threshold: Failures before opening circuit
        recovery_timeout: Seconds before trying half-open
        state: Current circuit state
        failures: Failure count in current window
        opened_at: Timestamp when circuit opened
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Consecutive failures before opening
            recovery_timeout: Seconds before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at: Optional[datetime] = None

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests).

        Returns:
            True if circuit is open, False otherwise
        """
        if self.state == CircuitState.CLOSED:
            return False

        if self.state == CircuitState.HALF_OPEN:
            return False

        # State is OPEN - check if recovery timeout elapsed
        if self.opened_at:
            elapsed = (datetime.now(timezone.utc) - self.opened_at).total_seconds()
            if elapsed >= self.recovery_timeout:
                # Try half-open state
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker entering HALF_OPEN state")
                return False

        return True

    def record_success(self):
        """Record successful request."""
        if self.state == CircuitState.HALF_OPEN:
            # Recovery successful, close circuit
            self.state = CircuitState.CLOSED
            self.failures = 0
            logger.info("Circuit breaker closed after successful recovery")
        elif self.state == CircuitState.CLOSED:
            # Reset failure counter on success
            self.failures = 0

    def record_failure(self):
        """Record failed request."""
        self.failures += 1

        if self.state == CircuitState.HALF_OPEN:
            # Recovery failed, re-open circuit
            self.state = CircuitState.OPEN
            self.opened_at = datetime.now(timezone.utc)
            logger.warning("Circuit breaker re-opened after recovery failure")

        elif self.state == CircuitState.CLOSED:
            # Check if threshold reached
            if self.failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = datetime.now(timezone.utc)
                logger.warning(
                    f"Circuit breaker opened after {self.failures} failures"
                )

    async def call(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute operation through circuit breaker.

        Args:
            operation: Async or sync callable to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation

        Returns:
            Result from operation

        Raises:
            CircuitOpenError: If circuit is open
            Exception: Any exception from operation
        """
        if self.is_open:
            raise CircuitOpenError("Circuit breaker is open")

        try:
            # Execute operation
            if asyncio.iscoroutinefunction(operation):
                result = await operation(*args, **kwargs)
            else:
                result = operation(*args, **kwargs)

            self.record_success()
            return result

        except Exception as e:
            self.record_failure()
            raise


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class AllEndpointsFailedError(Exception):
    """Raised when all RPC endpoints have failed."""
    pass


class RpcUsageTracker:
    """Tracks RPC usage for cost monitoring and analytics.

    Tracks daily and monthly usage per provider to:
    - Estimate costs and stay within free tiers
    - Generate usage reports
    - Alert when approaching limits
    """

    def __init__(self):
        """Initialize usage tracker."""
        self.daily_usage: Dict[str, int] = defaultdict(int)
        self.monthly_usage: Dict[str, int] = defaultdict(int)
        self.daily_failures: Dict[str, int] = defaultdict(int)
        self.last_reset: datetime = datetime.now(timezone.utc)

    def record_request(self, endpoint: RpcEndpoint, success: bool):
        """Record a request for usage tracking.

        Args:
            endpoint: Endpoint that handled the request
            success: Whether request succeeded
        """
        # Use enum value for consistent key naming
        priority_str = endpoint.priority.value if isinstance(endpoint.priority, EndpointPriority) else str(endpoint.priority)
        key = f"{endpoint.provider}_{priority_str}"

        self.daily_usage[key] += 1
        self.monthly_usage[key] += 1

        if not success:
            self.daily_failures[key] += 1

    def reset_daily_usage(self):
        """Reset daily usage counters."""
        self.daily_usage.clear()
        self.daily_failures.clear()
        self.last_reset = datetime.now(timezone.utc)

    def get_daily_summary(self) -> dict:
        """Generate daily usage summary for audit log.

        Returns:
            Dictionary with usage statistics
        """
        # Calculate usage by provider
        alchemy_requests = self.daily_usage.get("alchemy_premium", 0)
        quicknode_requests = self.daily_usage.get("quicknode_backup", 0)
        public_requests = self.daily_usage.get("public_public", 0)

        # Free tier limits (daily portion of monthly)
        alchemy_free_limit_daily = 300_000_000 / 30  # 10M compute units/day
        quicknode_free_limit_daily = 10_000_000 / 30  # ~333K credits/day

        # Calculate usage percentages
        alchemy_usage_pct = (alchemy_requests / alchemy_free_limit_daily * 100) if alchemy_free_limit_daily else 0
        quicknode_usage_pct = (quicknode_requests / quicknode_free_limit_daily * 100) if quicknode_free_limit_daily else 0

        # Check if approaching limits (>80%)
        approaching_limit = (
            alchemy_usage_pct > 80 or
            quicknode_usage_pct > 80
        )

        return {
            "event_type": "rpc_usage_summary",
            "period": "daily",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "premium_requests": alchemy_requests,
            "backup_requests": quicknode_requests,
            "public_requests": public_requests,
            "total_requests": alchemy_requests + quicknode_requests + public_requests,
            "alchemy_usage_percent": round(alchemy_usage_pct, 2),
            "quicknode_usage_percent": round(quicknode_usage_pct, 2),
            "approaching_limit": approaching_limit,
            "estimated_cost_usd": 0.00,  # We're in free tier
            "in_free_tier": True,
        }


class RpcManager:
    """Manages RPC endpoints with circuit breaker pattern and gradual rollout.

    Features:
    - Automatic endpoint selection based on priority and health
    - Circuit breaker pattern to prevent hammering failed endpoints
    - Rate limiting to stay within provider limits
    - Gradual rollout for safe premium RPC adoption
    - Cost tracking and usage analytics
    - Automatic failover to backup endpoints

    Usage:
        manager = RpcManager(config)
        await manager.initialize()

        # Execute operation with automatic failover
        result = await manager.execute_with_fallback(
            lambda w3: w3.eth.block_number,
            network_id="base-mainnet"
        )
    """

    def __init__(self, config):
        """Initialize RPC manager.

        Args:
            config: Settings instance with RPC configuration
        """
        self.config = config
        self.endpoints: Dict[str, List[RpcEndpoint]] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.usage_tracker = RpcUsageTracker()

        # Gradual rollout settings
        self.premium_enabled = getattr(config, 'premium_rpc_enabled', False)
        self.premium_percentage = getattr(config, 'premium_rpc_percentage', 10)

        logger.info(
            f"RpcManager initialized: premium_enabled={self.premium_enabled}, "
            f"rollout={self.premium_percentage}%"
        )

    def add_endpoint(self, endpoint: RpcEndpoint):
        """Add an RPC endpoint to the manager.

        Args:
            endpoint: RPC endpoint to add
        """
        network_id = endpoint.network_id

        if network_id not in self.endpoints:
            self.endpoints[network_id] = []

        self.endpoints[network_id].append(endpoint)

        # Create circuit breaker for this endpoint
        failure_threshold = getattr(self.config, 'rpc_failure_threshold', 3)
        recovery_timeout = getattr(self.config, 'rpc_recovery_timeout', 60)

        self.circuit_breakers[endpoint.url] = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout
        )

        logger.info(
            f"Added {endpoint.priority} endpoint for {network_id}: "
            f"{endpoint.get_sanitized_url()}"
        )

    def get_healthy_endpoints(self, network_id: str) -> List[RpcEndpoint]:
        """Get list of healthy endpoints for a network, sorted by priority.

        Args:
            network_id: Network identifier

        Returns:
            List of healthy endpoints, premium first
        """
        if network_id not in self.endpoints:
            return []

        # Priority order
        priority_order = [
            EndpointPriority.PREMIUM,
            EndpointPriority.BACKUP,
            EndpointPriority.PUBLIC
        ]

        healthy = []
        for priority in priority_order:
            for endpoint in self.endpoints[network_id]:
                if endpoint.priority != priority:
                    continue

                # Check if healthy and circuit not open
                breaker = self.circuit_breakers.get(endpoint.url)
                if endpoint.is_healthy and breaker and not breaker.is_open:
                    healthy.append(endpoint)

        return healthy

    def should_use_premium(self) -> bool:
        """Determine if request should use premium endpoint (gradual rollout).

        Returns:
            True if should try premium endpoint
        """
        if not self.premium_enabled:
            return False

        # Random selection based on rollout percentage
        return random.random() < (self.premium_percentage / 100.0)

    async def execute_with_fallback(
        self,
        operation: Callable,
        network_id: str,
        operation_name: str = "rpc_call"
    ) -> Any:
        """Execute operation with automatic failover.

        Args:
            operation: Callable that takes Web3 instance
            network_id: Network identifier
            operation_name: Name of operation for logging

        Returns:
            Result from operation

        Raises:
            AllEndpointsFailedError: If all endpoints failed
        """
        healthy_endpoints = self.get_healthy_endpoints(network_id)

        if not healthy_endpoints:
            raise AllEndpointsFailedError(
                f"No healthy endpoints available for {network_id}"
            )

        # Apply gradual rollout logic
        if not self.should_use_premium():
            # Skip premium endpoints, use backup/public
            healthy_endpoints = [
                ep for ep in healthy_endpoints
                if ep.priority != EndpointPriority.PREMIUM
            ]

        last_error = None

        for endpoint in healthy_endpoints:
            # Check rate limits
            if not endpoint.can_make_request():
                logger.debug(
                    f"Skipping {endpoint.provider} due to rate limit"
                )
                continue

            # Check circuit breaker
            breaker = self.circuit_breakers[endpoint.url]
            if breaker.is_open:
                logger.debug(
                    f"Skipping {endpoint.provider} due to open circuit"
                )
                continue

            try:
                # Record request for rate limiting
                endpoint.record_request()

                # Execute operation through circuit breaker
                start = time.time()
                result = await breaker.call(operation, endpoint)
                latency_ms = (time.time() - start) * 1000

                # Record success
                endpoint.record_success(latency_ms)
                self.usage_tracker.record_request(endpoint, success=True)

                logger.debug(
                    f"{operation_name} via {endpoint.provider}: "
                    f"{latency_ms:.1f}ms"
                )

                return result

            except CircuitOpenError:
                # Circuit is open, try next endpoint
                continue

            except Exception as e:
                # Operation failed
                endpoint.record_failure()
                self.usage_tracker.record_request(endpoint, success=False)

                logger.warning(
                    f"{operation_name} failed via {endpoint.provider}: {e}"
                )

                last_error = e
                continue

        # All endpoints failed
        error_msg = f"All endpoints failed for {network_id}"
        if last_error:
            error_msg += f": {last_error}"

        raise AllEndpointsFailedError(error_msg)
