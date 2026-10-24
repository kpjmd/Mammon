"""Per-protocol CircuitBreaker (src/utils/circuit_breaker.py)."""

import logging
from datetime import datetime, timedelta

from src.utils.circuit_breaker import CircuitBreaker


def test_reset_is_logged_once_not_on_every_later_success(caplog):
    """Regression: last_failure_time was never cleared, so every success after
    the reset window re-logged "reset after Ns" for the life of the process."""
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=600)
    breaker.record_failure("Aerodrome")
    breaker._get_circuit("Aerodrome").last_failure_time = datetime.now() - timedelta(
        seconds=601
    )

    with caplog.at_level(logging.INFO):
        for _ in range(3):
            breaker.record_success("Aerodrome")

    assert caplog.text.count("reset after") == 1
    circuit = breaker._get_circuit("Aerodrome")
    assert circuit.failure_count == 0
    assert circuit.last_failure_time is None


def test_success_within_window_does_not_reset():
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=600)
    breaker.record_failure("Aerodrome")

    breaker.record_success("Aerodrome")

    assert breaker._get_circuit("Aerodrome").failure_count == 1
