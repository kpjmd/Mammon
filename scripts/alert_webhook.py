"""Stdlib webhook POST shared by the droplet's standalone ops scripts.

Used by ``heartbeat_check.py`` and ``backup_db.py`` (and, through it,
``replicate_backups.py``). STDLIB-ONLY like its callers, so it runs without the
app or its virtualenv.

Discord's Cloudflare front end rejects urllib's default ``Python-urllib/x.y``
User-Agent with ``403 error code: 1010``, so every request sets an explicit one.
Before this module existed, no heartbeat or backup alert could ever be delivered.
"""

import json
import urllib.request

USER_AGENT = "MAMMON-alerts/1.0 (+https://github.com/kpjmd/Mammon)"
TIMEOUT_S = 5


def post_webhook(url: str, payload: dict[str, object]) -> None:
    """POST ``payload`` as JSON to ``url``.

    Raises on any failure, including HTTP >= 400, so callers can log it rather
    than lose the alert silently.
    """
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S):
        pass
