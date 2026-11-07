"""Disk-persisted latch for the Morpho vault share-price (bad-debt) tripwire.

MetaMorpho v1.0 realizes bad debt by lowering the share price. The tripwire
compares each read against the highest share price ever seen; a drop beyond
the RPC-lag tolerance latches the vault as tripped. The latch and the
high-water mark must survive restarts. Otherwise a restart (a crash, the
monthly duration rollover, or the runbook's stop -> exit -> start) would clear
the trip and adopt the post-loss price as the new baseline, and idle-deploy
could put the just-exited USDC straight back into the damaged vault.

Mirrors src/utils/cycle_breaker.py: JSON state file, atomic write. Unlike the
cycle breaker, an unreadable state file fails CLOSED (every vault reads as
tripped). Only an explicit operator reset (scripts/reset_morpho_vault_guard.py)
clears a trip. The file also records the last reason alerted on, so a guard
failure reaches Discord once per distinct reason rather than every cycle.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_STATE_FILE = "data/morpho_vault_guard.json"

# A lagging RPC replica can serve a block a few seconds old, i.e. a share price
# a hair lower than the last read. Two hours of interest at 5% is ~0.1bp, so a
# 1bp tolerance absorbs lag while still catching any bad-debt event that
# matters.
SHARE_PRICE_DROP_TOLERANCE = Decimal("0.0001")


class VaultGuardError(Exception):
    """The vault's on-chain state no longer matches its pinned allowlist."""


class GuardStateUnreadable(Exception):
    """The guard state file exists but cannot be parsed."""


@dataclass
class VaultGuardRecord:
    """Persisted guard state for one vault (keyed by vault address)."""

    high_water_share_price: Optional[int] = None
    tripped: bool = False
    trip_reason: Optional[str] = None
    tripped_at: Optional[str] = None
    last_alerted_reason: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VaultGuardRecord":
        hw = data.get("high_water_share_price")
        return cls(
            high_water_share_price=int(hw) if hw is not None else None,
            tripped=bool(data.get("tripped", False)),
            trip_reason=data.get("trip_reason"),
            tripped_at=data.get("tripped_at"),
            last_alerted_reason=data.get("last_alerted_reason"),
        )


def default_state_file() -> str:
    """Module default, resolved at call time (tests redirect it to tmp)."""
    return DEFAULT_STATE_FILE


class VaultGuardStore:
    """Read-modify-write access to the guard state file.

    Every call round-trips through disk, so a reset made by the operator
    script is seen by the running loop and the exit/executor paths alike.
    """

    def __init__(
        self,
        state_file: Optional[str | Path] = None,
        now_fn: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.state_file = Path(state_file or default_state_file())
        self._now = now_fn or (lambda: datetime.now(UTC))
        # A trip latched in this process stays latched even if persisting it
        # failed (disk full, permissions): never weaker than in-memory.
        self._process_trips: Dict[str, str] = {}

    # -- persistence --------------------------------------------------------
    def _load(self) -> Dict[str, VaultGuardRecord]:
        if not self.state_file.exists():
            return {}
        try:
            raw = json.loads(self.state_file.read_text())
            if not isinstance(raw, dict):
                raise ValueError("top-level JSON is not an object")
            return {k.lower(): VaultGuardRecord.from_dict(v) for k, v in raw.items()}
        except Exception as e:  # noqa: BLE001 - any parse failure fails closed
            raise GuardStateUnreadable(f"{self.state_file}: {e}") from e

    def _save(self, records: Dict[str, VaultGuardRecord]) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({k: asdict(v) for k, v in records.items()}, indent=2))
            tmp.replace(self.state_file)
        except Exception as e:  # noqa: BLE001 - persistence failure must not crash
            logger.error(f"Failed to persist Morpho vault guard state: {e}")

    def _records_or_raise(self) -> Dict[str, VaultGuardRecord]:
        try:
            return self._load()
        except GuardStateUnreadable as e:
            raise VaultGuardError(
                f"Morpho vault guard state unreadable ({e}); treating every vault "
                f"as tripped. Inspect, then reset with "
                f"scripts/reset_morpho_vault_guard.py --confirm"
            ) from e

    # -- API ----------------------------------------------------------------
    def assert_not_tripped(self, vault: str) -> None:
        """Raise VaultGuardError if the vault is latched (or state unreadable)."""
        key = vault.lower()
        if key in self._process_trips:
            raise VaultGuardError(self._process_trips[key])
        record = self._records_or_raise().get(key)
        if record and record.tripped:
            raise VaultGuardError(record.trip_reason or "Morpho vault guard tripped")

    def check_share_price(self, vault: str, label: str, share_price: int) -> None:
        """Advance the high-water mark, or latch a trip on a real drop.

        Raises:
            VaultGuardError: Already tripped, state unreadable, or this read is
                more than SHARE_PRICE_DROP_TOLERANCE below the high-water mark.
        """
        self.assert_not_tripped(vault)
        key = vault.lower()
        records = self._records_or_raise()
        record = records.setdefault(key, VaultGuardRecord())
        high_water = record.high_water_share_price
        if high_water is not None and share_price < high_water:
            drop = Decimal(high_water - share_price) / Decimal(high_water)
            if drop > SHARE_PRICE_DROP_TOLERANCE:
                self._latch(records, key, record, (
                    f"{label}: share price fell {drop:.6%} below its high-water "
                    f"mark ({high_water} -> {share_price}); possible bad debt. "
                    f"Deposits blocked until an operator reset."
                ))
            return  # within tolerance: keep the higher reference
        if high_water is None or share_price > high_water:
            record.high_water_share_price = share_price
            self._save(records)

    def _latch(
        self,
        records: Dict[str, VaultGuardRecord],
        key: str,
        record: VaultGuardRecord,
        reason: str,
    ) -> None:
        record.tripped = True
        record.trip_reason = reason
        record.tripped_at = self._now().isoformat()
        self._process_trips[key] = reason
        self._save(records)
        logger.critical(f"🛑 Morpho vault guard LATCHED: {reason}")
        raise VaultGuardError(reason)

    def latch(self, vault: str, reason: str) -> None:
        """Latch a vault as tripped on operator action (e.g. a manual exit).

        Unlike a share-price trip this does not raise; an unreadable state
        file is replaced, since the operator is deliberately blocking deposits.
        """
        key = vault.lower()
        try:
            records = self._load()
        except GuardStateUnreadable:
            records = {}
        record = records.setdefault(key, VaultGuardRecord())
        record.tripped = True
        record.trip_reason = reason
        record.tripped_at = self._now().isoformat()
        self._process_trips[key] = reason
        self._save(records)

    def should_alert(self, vault: str, failure: Optional[str]) -> bool:
        """True once per distinct guard-failure reason; clears on recovery.

        `failure` is this scan's guard error (None if the guard passed). An
        unreadable state file always alerts (it cannot record the dedupe).
        """
        key = vault.lower()
        try:
            records = self._load()
        except GuardStateUnreadable:
            return failure is not None
        record = records.setdefault(key, VaultGuardRecord())
        if failure is None:
            if record.last_alerted_reason is not None and not record.tripped:
                record.last_alerted_reason = None
                self._save(records)
            return False
        if record.last_alerted_reason == failure:
            return False
        record.last_alerted_reason = failure
        self._save(records)
        return True

    def snapshot(self) -> Dict[str, VaultGuardRecord]:
        """Current records (raises GuardStateUnreadable on a corrupt file)."""
        return self._load()

    def reset(self, vault: Optional[str] = None) -> None:
        """Operator reset: drop one vault's record (or all, or a corrupt file).

        Removing the record also discards the high-water mark, so the next
        scan adopts the current share price as the new baseline. That is the
        point of an explicit reset after investigating the loss.
        """
        try:
            records = self._load()
        except GuardStateUnreadable:
            records = {}
        if vault is None:
            records = {}
        else:
            records.pop(vault.lower(), None)
        self._process_trips.clear()
        self._save(records)
