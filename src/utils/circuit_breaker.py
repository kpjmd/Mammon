"""
Circuit breaker for failing protocol operations.

Prevents repeated calls to failing protocols, allowing graceful degradation.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CircuitBreakerState:
    """State tracking for a single circuit."""

    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    is_open: bool = False
    opened_at: Optional[datetime] = None


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for protocol operations.

    Tracks failures per protocol and temporarily stops calling failing protocols
    to prevent cascading failures and allow the system to continue with healthy protocols.

    Args:
        failure_threshold: Number of consecutive failures before opening circuit
        timeout_seconds: How long to keep circuit open before trying again
        reset_timeout_seconds: Time after success before resetting failure count
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        timeout_seconds: int = 300,  # 5 minutes
        reset_timeout_seconds: int = 600,  # 10 minutes
    ):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.reset_timeout_seconds = reset_timeout_seconds
        self.circuits: Dict[str, CircuitBreakerState] = {}

    def _get_circuit(self, protocol: str) -> CircuitBreakerState:
        """Get or create circuit state for a protocol."""
        if protocol not in self.circuits:
            self.circuits[protocol] = CircuitBreakerState()
        return self.circuits[protocol]

    def is_open(self, protocol: str) -> bool:
        """Check if circuit is open (blocking calls) for a protocol."""
        circuit = self._get_circuit(protocol)

        if not circuit.is_open:
            return False

        # Check if timeout has elapsed
        if circuit.opened_at:
            elapsed = datetime.now() - circuit.opened_at
            if elapsed.total_seconds() >= self.timeout_seconds:
                logger.info(
                    f"Circuit breaker for {protocol} timeout elapsed, "
                    f"attempting half-open state"
                )
                circuit.is_open = False
                circuit.opened_at = None
                return False

        return True

    def record_success(self, protocol: str) -> None:
        """Record successful operation for a protocol."""
        circuit = self._get_circuit(protocol)
        circuit.last_success_time = datetime.now()

        # Reset failure count if enough time has passed
        if circuit.last_failure_time:
            elapsed = datetime.now() - circuit.last_failure_time
            if elapsed.total_seconds() >= self.reset_timeout_seconds:
                logger.info(
                    f"Circuit breaker for {protocol} reset after "
                    f"{elapsed.total_seconds():.0f}s without failures"
                )
                circuit.failure_count = 0
                circuit.is_open = False
                circuit.opened_at = None

    def record_failure(self, protocol: str, error: Optional[Exception] = None) -> None:
        """Record failed operation for a protocol."""
        circuit = self._get_circuit(protocol)
        circuit.failure_count += 1
        circuit.last_failure_time = datetime.now()

        error_msg = f" ({type(error).__name__}: {str(error)})" if error else ""
        logger.warning(
            f"Circuit breaker for {protocol}: failure #{circuit.failure_count}{error_msg}"
        )

        # Open circuit if threshold reached
        if circuit.failure_count >= self.failure_threshold and not circuit.is_open:
            circuit.is_open = True
            circuit.opened_at = datetime.now()
            logger.error(
                f"Circuit breaker OPENED for {protocol} after "
                f"{circuit.failure_count} failures. Will retry in "
                f"{self.timeout_seconds}s"
            )

    def call(
        self,
        protocol: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Optional[Any]:
        """
        Execute a function with circuit breaker protection.

        Args:
            protocol: Protocol identifier
            func: Function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Function result if successful, None if circuit is open or function fails
        """
        if self.is_open(protocol):
            logger.debug(f"Circuit breaker for {protocol} is OPEN, skipping call")
            return None

        try:
            result = func(*args, **kwargs)
            self.record_success(protocol)
            return result
        except Exception as e:
            self.record_failure(protocol, e)
            logger.error(
                f"Circuit breaker caught exception from {protocol}: "
                f"{type(e).__name__}: {str(e)}"
            )
            return None

    def get_status(self, protocol: str) -> Dict[str, Any]:
        """Get current status of a protocol's circuit breaker."""
        circuit = self._get_circuit(protocol)
        return {
            "protocol": protocol,
            "is_open": circuit.is_open,
            "failure_count": circuit.failure_count,
            "last_failure": circuit.last_failure_time.isoformat()
            if circuit.last_failure_time
            else None,
            "last_success": circuit.last_success_time.isoformat()
            if circuit.last_success_time
            else None,
            "opened_at": circuit.opened_at.isoformat() if circuit.opened_at else None,
        }

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers."""
        return {protocol: self.get_status(protocol) for protocol in self.circuits}

    def reset(self, protocol: Optional[str] = None) -> None:
        """
        Reset circuit breaker(s).

        Args:
            protocol: Specific protocol to reset, or None to reset all
        """
        if protocol:
            if protocol in self.circuits:
                logger.info(f"Manually resetting circuit breaker for {protocol}")
                self.circuits[protocol] = CircuitBreakerState()
        else:
            logger.info("Manually resetting all circuit breakers")
            self.circuits = {}
