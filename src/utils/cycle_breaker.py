"""Latching circuit breaker for the autonomous optimization loop.

Distinct from ``src/utils/circuit_breaker.py`` (a per-protocol breaker that
auto-recovers after a timeout). This one LATCHES: once tripped it stays tripped
until an operator explicitly resets it (``scripts/resume_optimizer.py``). It
trips on either N consecutive failed cycles or M failures within 24h.

State is persisted to disk as JSON so it survives the systemd ``Restart=on-
failure`` that would otherwise wipe an in-memory counter, and so an out-of-
process reset is visible to the running loop. Every public method round-trips
through disk, keeping in-memory and on-disk state from diverging.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BreakerState:
    """Serializable circuit-breaker state."""

    consecutive_failures: int = 0
    failure_timestamps: List[str] = field(default_factory=list)  # ISO-8601 UTC
    tripped: bool = False
    trip_reason: Optional[str] = None
    tripped_at: Optional[str] = None
    alerted: bool = False  # whether the trip has already been alerted on

    @classmethod
    def from_dict(cls, data: dict) -> "BreakerState":
        return cls(
            consecutive_failures=int(data.get("consecutive_failures", 0)),
            failure_timestamps=list(data.get("failure_timestamps", [])),
            tripped=bool(data.get("tripped", False)),
            trip_reason=data.get("trip_reason"),
            tripped_at=data.get("tripped_at"),
            alerted=bool(data.get("alerted", False)),
        )


class CycleCircuitBreaker:
    """A latching, disk-persisted circuit breaker for the scan loop.

    Args:
        max_consecutive: Consecutive failures that trip the breaker.
        max_per_24h: Failures within a rolling 24h window that trip the breaker.
        state_file: Path to the JSON state file.
        now_fn: Injectable clock (returns tz-aware UTC datetime) for testing.
    """

    def __init__(
        self,
        max_consecutive: int = 3,
        max_per_24h: int = 10,
        state_file: str | Path = "data/circuit_breaker_state.json",
        now_fn: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.max_consecutive = max_consecutive
        self.max_per_24h = max_per_24h
        self.state_file = Path(state_file)
        self._now = now_fn or (lambda: datetime.now(UTC))

    # -- persistence --------------------------------------------------------
    def _load(self) -> BreakerState:
        try:
            if self.state_file.exists():
                return BreakerState.from_dict(json.loads(self.state_file.read_text()))
        except Exception as e:  # noqa: BLE001 - corrupt state must not crash the loop
            logger.error(f"Failed to read circuit-breaker state, assuming clean: {e}")
        return BreakerState()

    def _save(self, state: BreakerState) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(state), indent=2))
            tmp.replace(self.state_file)
        except Exception as e:  # noqa: BLE001 - persistence failure must not crash
            logger.error(f"Failed to persist circuit-breaker state: {e}")

    def _prune(self, state: BreakerState, now: datetime) -> None:
        cutoff = now - timedelta(hours=24)
        kept: List[str] = []
        for ts in state.failure_timestamps:
            try:
                if datetime.fromisoformat(ts) > cutoff:
                    kept.append(ts)
            except ValueError:
                continue
        state.failure_timestamps = kept

    # -- API ----------------------------------------------------------------
    def record_failure(self, error: str) -> bool:
        """Record a failed cycle. Returns True if THIS failure tripped the breaker."""
        now = self._now()
        state = self._load()
        state.consecutive_failures += 1
        state.failure_timestamps.append(now.isoformat())
        self._prune(state, now)

        newly_tripped = False
        if not state.tripped:
            if state.consecutive_failures >= self.max_consecutive:
                state.tripped = True
                state.trip_reason = (
                    f"{state.consecutive_failures} consecutive cycle failures " f"(last: {error})"
                )
            elif len(state.failure_timestamps) >= self.max_per_24h:
                state.tripped = True
                state.trip_reason = (
                    f"{len(state.failure_timestamps)} cycle failures in 24h " f"(last: {error})"
                )
            if state.tripped:
                state.tripped_at = now.isoformat()
                newly_tripped = True
                logger.critical(f"🛑 Circuit breaker TRIPPED: {state.trip_reason}")

        self._save(state)
        return newly_tripped

    def record_success(self) -> None:
        """Record a successful cycle: reset the consecutive counter (24h window kept)."""
        state = self._load()
        if state.consecutive_failures or not state.failure_timestamps:
            state.consecutive_failures = 0
            self._save(state)

    def is_tripped(self) -> bool:
        """Return True if the breaker is currently latched (fresh read from disk)."""
        return self._load().tripped

    @property
    def trip_reason(self) -> Optional[str]:
        return self._load().trip_reason

    def needs_alert(self) -> bool:
        """True if tripped and not yet alerted; marks it alerted as a side effect."""
        state = self._load()
        if state.tripped and not state.alerted:
            state.alerted = True
            self._save(state)
            return True
        return False

    def reset(self, who: str = "manual") -> BreakerState:
        """Clear the latch (operator resume). Returns the pre-reset state."""
        prior = self._load()
        self._save(BreakerState())
        logger.warning(f"▶️  Circuit breaker reset by {who}")
        return prior

    def snapshot(self) -> BreakerState:
        """Return the current persisted state (read-only)."""
        return self._load()
