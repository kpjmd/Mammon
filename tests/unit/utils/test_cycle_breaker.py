"""Unit tests for the latching CycleCircuitBreaker (WS3).

Covers tripping on consecutive failures and on the 24h window, that success
resets only the consecutive counter, disk persistence across instances (the
systemd-restart case), one-shot alerting, and that a reset clears the latch
with no time-based auto-recovery.
"""

from datetime import datetime, UTC, timedelta

import pytest

from src.utils.cycle_breaker import CycleCircuitBreaker


class _Clock:
    def __init__(self, start: datetime):
        self.t = start

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **kw):
        self.t = self.t + timedelta(**kw)


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "breaker.json"


def _breaker(state_file, clock=None, **kw):
    return CycleCircuitBreaker(
        max_consecutive=kw.get("max_consecutive", 3),
        max_per_24h=kw.get("max_per_24h", 10),
        state_file=state_file,
        now_fn=clock,
    )


class TestConsecutiveTrip:
    def test_trips_at_threshold(self, state_file):
        b = _breaker(state_file, max_consecutive=3)
        assert b.record_failure("e1") is False
        assert b.record_failure("e2") is False
        assert b.record_failure("e3") is True  # third trips
        assert b.is_tripped()

    def test_success_resets_consecutive(self, state_file):
        b = _breaker(state_file, max_consecutive=3)
        b.record_failure("e1")
        b.record_failure("e2")
        b.record_success()
        assert b.record_failure("e3") is False  # counter was reset
        assert not b.is_tripped()


class TestWindowTrip:
    def test_trips_on_24h_count(self, state_file):
        clock = _Clock(datetime(2026, 7, 15, tzinfo=UTC))
        b = _breaker(state_file, max_consecutive=100, max_per_24h=5, clock=clock)
        tripped = False
        for i in range(5):
            clock.advance(minutes=1)
            tripped = b.record_failure(f"e{i}")
        assert tripped is True
        assert b.is_tripped()

    def test_old_failures_pruned_from_window(self, state_file):
        clock = _Clock(datetime(2026, 7, 15, tzinfo=UTC))
        b = _breaker(state_file, max_consecutive=100, max_per_24h=3, clock=clock)
        b.record_failure("old1")
        clock.advance(hours=25)  # first failure ages out of the 24h window
        b.record_failure("new1")
        b.record_success()  # keep consecutive from tripping
        b.record_failure("new2")
        assert not b.is_tripped()  # only 2 within window, threshold 3


class TestPersistence:
    def test_state_survives_new_instance(self, state_file):
        b1 = _breaker(state_file, max_consecutive=2)
        b1.record_failure("e1")
        b1.record_failure("e2")
        assert b1.is_tripped()
        # Simulate a process restart: a fresh instance reads persisted state.
        b2 = _breaker(state_file, max_consecutive=2)
        assert b2.is_tripped()
        assert b2.trip_reason is not None


class TestAlertingAndReset:
    def test_needs_alert_is_one_shot(self, state_file):
        b = _breaker(state_file, max_consecutive=1)
        b.record_failure("e1")
        assert b.needs_alert() is True
        assert b.needs_alert() is False  # already alerted

    def test_reset_clears_latch(self, state_file):
        b = _breaker(state_file, max_consecutive=1)
        b.record_failure("e1")
        assert b.is_tripped()
        prior = b.reset(who="test")
        assert prior.tripped is True
        assert not b.is_tripped()
        assert b.trip_reason is None

    def test_no_auto_recovery_over_time(self, state_file):
        clock = _Clock(datetime(2026, 7, 15, tzinfo=UTC))
        b = _breaker(state_file, max_consecutive=1, clock=clock)
        b.record_failure("e1")
        clock.advance(days=3)
        assert b.is_tripped()  # still latched days later — no timeout recovery


class TestCorruptState:
    def test_corrupt_state_file_is_treated_as_clean(self, state_file):
        state_file.write_text("{ not valid json")
        b = _breaker(state_file)
        assert not b.is_tripped()
