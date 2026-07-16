#!/usr/bin/env python3
"""Reset the autonomous optimizer's circuit breaker (operator resume).

The circuit breaker latches after repeated cycle failures and stays tripped
until a human clears it. This script is that manual, deliberate resume. It can
run while the loop process is live (state is file-based) or while it's stopped.

Usage:
    python scripts/resume_optimizer.py            # show state, do nothing
    python scripts/resume_optimizer.py --confirm  # actually reset the breaker
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.cycle_breaker import CycleCircuitBreaker  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the optimizer circuit breaker")
    parser.add_argument(
        "--state-file",
        default="data/circuit_breaker_state.json",
        help="Path to the circuit-breaker state file",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually perform the reset (otherwise just prints current state)",
    )
    args = parser.parse_args()

    breaker = CycleCircuitBreaker(state_file=args.state_file)
    state = breaker.snapshot()

    print("Circuit breaker state:")
    print(f"  tripped:              {state.tripped}")
    print(f"  trip_reason:          {state.trip_reason}")
    print(f"  tripped_at:           {state.tripped_at}")
    print(f"  consecutive_failures: {state.consecutive_failures}")
    print(f"  failures (24h):       {len(state.failure_timestamps)}")

    if not state.tripped:
        print("\nBreaker is not tripped — nothing to reset.")
        return 0

    if not args.confirm:
        print("\nDry run. Re-run with --confirm to reset and resume the optimizer.")
        return 0

    breaker.reset(who="resume_optimizer.py")
    print("\n✅ Circuit breaker reset. The optimizer will resume on its next cycle.")

    # Best-effort audit trail (skipped if config/env unavailable).
    try:
        import asyncio

        from src.security.audit import AuditLogger, AuditEventType, AuditSeverity

        async def _audit() -> None:
            await AuditLogger().log_event(
                AuditEventType.CIRCUIT_BREAKER_RESET,
                AuditSeverity.WARNING,
                "Circuit breaker manually reset via resume_optimizer.py",
                metadata={"prior_reason": state.trip_reason},
            )

        asyncio.run(_audit())
    except Exception as e:  # noqa: BLE001 - audit is best-effort
        print(f"(Note: could not write audit event: {e})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
