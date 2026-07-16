"""Liveness heartbeat for the autonomous loop.

The loop writes a small JSON heartbeat each cycle (and during long sleeps) so an
independent, out-of-process checker (``scripts/heartbeat_check.py``) can alert
if the loop has silently died or hung — a dead-man switch.

Writes are atomic (temp file + ``os.replace``) so a reader never sees a
half-written file, and never raise: a heartbeat failure must not crash the loop.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


def write_heartbeat(
    path: str | Path,
    *,
    last_cycle_ok: bool,
    total_scans: int,
    breaker_tripped: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Atomically write the heartbeat file. Never raises."""
    payload: Dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "last_cycle_ok": last_cycle_ok,
        "total_scans": total_scans,
        "breaker_tripped": breaker_tripped,
        "pid": os.getpid(),
    }
    if extra:
        payload.update(extra)

    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, p)
    except Exception as e:  # noqa: BLE001 - heartbeat must never crash the loop
        logger.error(f"Failed to write heartbeat to {path}: {e}")
