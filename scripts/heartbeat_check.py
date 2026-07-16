#!/usr/bin/env python3
"""Dead-man switch: alert if the autonomous loop's heartbeat goes stale.

Run this from cron / a systemd timer on the droplet. It is deliberately
STDLIB-ONLY and does NOT import the app (src.utils.config hard-fails without a
full secret set) — the checker must be the one thing that cannot itself break.

    */15 * * * * cd /root/mammon && /usr/bin/python3 scripts/heartbeat_check.py \
        >> /var/log/mammon-heartbeat.log 2>&1

Exit 0 = fresh, exit 1 = stale/missing (and a CRITICAL alert was POSTed if a
webhook is configured). A marker file prevents re-alerting every run while
stale; it clears automatically once the heartbeat recovers.
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HEARTBEAT = "data/heartbeat.json"
DEFAULT_MAX_AGE = 10800  # 3h (1.5x a 2h scan interval)
MARKER_SUFFIX = ".stale_alerted"


def _read_env(key: str) -> str:
    """Read a key from the process env or a local .env file (no deps)."""
    if key in os.environ:
        return os.environ[key]
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                # strip inline comments and quotes
                return v.split("#", 1)[0].strip().strip('"').strip("'")
    return ""


def _post_alert(webhook: str, title: str, message: str) -> None:
    if not webhook:
        return
    text = f"[CRITICAL] MAMMON: {title}\n{message}"
    payload = json.dumps(
        {"content": text, "text": text, "level": "critical", "title": title}
    ).encode()
    req = urllib.request.Request(
        webhook, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:  # noqa: BLE001 - alerting is best-effort
        print(f"Alert POST failed: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="MAMMON heartbeat dead-man check")
    parser.add_argument("--file", default=_read_env("HEARTBEAT_FILE") or DEFAULT_HEARTBEAT)
    parser.add_argument(
        "--max-age",
        type=int,
        default=int(_read_env("HEARTBEAT_MAX_AGE_SECONDS") or DEFAULT_MAX_AGE),
    )
    args = parser.parse_args()

    webhook = _read_env("ALERT_WEBHOOK")
    hb_path = Path(args.file)
    marker = Path(str(hb_path) + MARKER_SUFFIX)
    now = datetime.now(timezone.utc)

    def _fail(reason: str) -> int:
        print(f"STALE: {reason}")
        if not marker.exists():  # one-shot alert until recovery
            _post_alert(webhook, "MAMMON heartbeat stale", reason)
            try:
                marker.write_text(now.isoformat())
            except Exception:  # noqa: BLE001
                pass
        return 1

    if not hb_path.exists():
        return _fail(f"heartbeat file missing: {hb_path}")

    try:
        data = json.loads(hb_path.read_text())
        ts = datetime.fromisoformat(data["timestamp"])
    except Exception as e:  # noqa: BLE001
        return _fail(f"unreadable heartbeat ({e})")

    age = (now - ts).total_seconds()
    if age > args.max_age:
        return _fail(f"heartbeat {age:.0f}s old (> {args.max_age}s); pid={data.get('pid')}")

    # Fresh: clear any stale marker so the next failure re-alerts.
    if marker.exists():
        try:
            marker.unlink()
        except Exception:  # noqa: BLE001
            pass
    print(f"OK: heartbeat {age:.0f}s old, scans={data.get('total_scans')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
