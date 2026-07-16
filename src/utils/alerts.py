"""Outbound alerting for MAMMON.

Provides a minimal, dependency-light alert manager that POSTs JSON to a generic
webhook (Discord- and Slack-compatible). Alerts are the push channel for events
that a human must see quickly: circuit-breaker trips, wallet auto-pause, stranded
funds, loop crashes, and pending approvals.

Design guarantees:
- ``send`` NEVER raises. Alerting sits in exception handlers on the live money
  path; a failed alert must never mask or replace the original error.
- No webhook configured -> no-op (returns False), logged at debug level.
- Duplicate (level, title) pairs are suppressed within a dedupe window.
- A per-hour token bucket rate-limits noise. CRITICAL bypasses the rate limit
  (but not the dedupe window).
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import aiohttp

from src.utils.logger import get_logger

logger = get_logger(__name__)

_HTTP_TIMEOUT_SECONDS = 5


class AlertLevel(Enum):
    """Severity of an outbound alert."""

    WARN = "warn"
    ERROR = "error"
    CRITICAL = "critical"


class AlertManager:
    """Sends rate-limited, deduplicated alerts to a generic webhook.

    Args:
        webhook_url: Destination webhook. If falsy, all sends are no-ops.
        rate_limit_per_hour: Max non-critical alerts per rolling hour.
        dedupe_window_seconds: Suppress identical (level, title) within this window.
    """

    def __init__(
        self,
        webhook_url: Optional[str],
        rate_limit_per_hour: int = 20,
        dedupe_window_seconds: int = 3600,
    ) -> None:
        self.webhook_url = webhook_url
        self.rate_limit_per_hour = rate_limit_per_hour
        self.dedupe_window_seconds = dedupe_window_seconds
        # (level, title) -> last-sent monotonic timestamp
        self._last_sent: Dict[Tuple[str, str], float] = {}
        # Monotonic timestamps of recent non-critical sends (rolling hour).
        self._send_times: list[float] = []

    def _now(self) -> float:
        return time.monotonic()

    def _is_duplicate(self, key: Tuple[str, str], now: float) -> bool:
        last = self._last_sent.get(key)
        return last is not None and (now - last) < self.dedupe_window_seconds

    def _rate_limited(self, now: float) -> bool:
        cutoff = now - 3600
        self._send_times = [t for t in self._send_times if t > cutoff]
        return len(self._send_times) >= self.rate_limit_per_hour

    def _build_payload(
        self, level: AlertLevel, title: str, message: str, metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        text = f"[{level.value.upper()}] MAMMON: {title}\n{message}"
        # ``content`` is read by Discord webhooks; ``text`` by Slack incoming
        # webhooks. Extra keys are ignored by both, so one payload serves both.
        return {
            "content": text,
            "text": text,
            "level": level.value,
            "title": title,
            "message": message,
            "metadata": metadata or {},
        }

    async def send(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send an alert. Returns True if delivered, False if skipped/failed.

        Never raises.
        """
        try:
            if not self.webhook_url:
                logger.debug("Alert suppressed (no webhook configured): %s", title)
                return False

            now = self._now()
            key = (level.value, title)

            if self._is_duplicate(key, now):
                logger.debug("Alert deduplicated: %s", title)
                return False

            # CRITICAL bypasses the rate limit but not the dedupe window above.
            if level is not AlertLevel.CRITICAL and self._rate_limited(now):
                logger.warning("Alert rate-limited, dropping: %s", title)
                return False

            payload = self._build_payload(level, title, message, metadata)
            timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        logger.warning("Alert webhook returned %s: %s", resp.status, body[:200])
                        return False

            self._last_sent[key] = now
            if level is not AlertLevel.CRITICAL:
                self._send_times.append(now)
            return True

        except Exception as e:  # noqa: BLE001 - alerting must never raise
            logger.warning("Alert send failed (%s): %s", title, e)
            return False

    async def warn(self, title: str, message: str, **metadata: Any) -> bool:
        return await self.send(AlertLevel.WARN, title, message, metadata or None)

    async def error(self, title: str, message: str, **metadata: Any) -> bool:
        return await self.send(AlertLevel.ERROR, title, message, metadata or None)

    async def critical(self, title: str, message: str, **metadata: Any) -> bool:
        return await self.send(AlertLevel.CRITICAL, title, message, metadata or None)


_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Return the process-wide AlertManager, built from settings on first use.

    Resilient by design: if settings cannot be loaded (e.g. missing env in a
    partial environment), returns a no-op manager rather than raising, so that
    alert wiring on the live path can never break the caller.
    """
    global _alert_manager
    if _alert_manager is None:
        webhook: Optional[str] = None
        rate_limit = 20
        try:
            from src.utils.config import get_settings

            settings = get_settings()
            webhook = settings.alert_webhook
            rate_limit = getattr(settings, "alert_rate_limit_per_hour", 20)
        except Exception as e:  # noqa: BLE001 - never let config break alerting
            logger.warning("Could not load settings for AlertManager: %s", e)
        _alert_manager = AlertManager(webhook, rate_limit_per_hour=rate_limit)
    return _alert_manager


def reset_alert_manager() -> None:
    """Reset the singleton (test hook)."""
    global _alert_manager
    _alert_manager = None
