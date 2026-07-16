"""Unit tests for the outbound AlertManager.

Verifies the never-raises contract, payload shape (Discord + Slack keys),
dedupe suppression, hourly rate limiting, the CRITICAL rate-limit bypass, and
the no-webhook no-op path. The HTTP layer is mocked so no network is touched.
"""

from contextlib import asynccontextmanager

import pytest

from src.utils.alerts import AlertManager, AlertLevel


class _FakeResponse:
    def __init__(self, status: int = 200, body: str = "ok"):
        self.status = status
        self._body = body

    async def text(self) -> str:
        return self._body


class _FakeSession:
    """Captures POST payloads and returns a configurable response."""

    posts: list = []
    response_status = 200

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None):
        _FakeSession.posts.append({"url": url, "json": json})

        @asynccontextmanager
        async def _cm():
            yield _FakeResponse(status=_FakeSession.response_status)

        return _cm()


@pytest.fixture(autouse=True)
def _patch_session(monkeypatch):
    _FakeSession.posts = []
    _FakeSession.response_status = 200
    monkeypatch.setattr("src.utils.alerts.aiohttp.ClientSession", _FakeSession)
    yield


class TestPayload:
    async def test_payload_has_discord_and_slack_keys(self):
        mgr = AlertManager("https://hook.example/x")
        ok = await mgr.warn("Title here", "Body here", foo="bar")
        assert ok is True
        assert len(_FakeSession.posts) == 1
        payload = _FakeSession.posts[0]["json"]
        assert "content" in payload  # Discord
        assert "text" in payload  # Slack
        assert payload["level"] == "warn"
        assert payload["title"] == "Title here"
        assert payload["metadata"] == {"foo": "bar"}


class TestNeverRaises:
    async def test_http_error_status_returns_false(self):
        _FakeSession.response_status = 500
        mgr = AlertManager("https://hook.example/x")
        assert await mgr.error("t", "m") is False

    async def test_exception_in_send_returns_false(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("network down")

        monkeypatch.setattr("src.utils.alerts.aiohttp.ClientSession", _boom)
        mgr = AlertManager("https://hook.example/x")
        # Must swallow the exception and report failure, not raise.
        assert await mgr.critical("t", "m") is False

    async def test_no_webhook_is_noop(self):
        mgr = AlertManager(None)
        assert await mgr.warn("t", "m") is False
        assert _FakeSession.posts == []


class TestDedupe:
    async def test_identical_alert_suppressed_within_window(self):
        mgr = AlertManager("https://hook.example/x", dedupe_window_seconds=3600)
        assert await mgr.warn("same", "first") is True
        assert await mgr.warn("same", "second") is False  # deduped
        assert len(_FakeSession.posts) == 1

    async def test_different_title_not_deduped(self):
        mgr = AlertManager("https://hook.example/x")
        assert await mgr.warn("a", "m") is True
        assert await mgr.warn("b", "m") is True
        assert len(_FakeSession.posts) == 2


class TestRateLimit:
    async def test_rate_limit_drops_excess_non_critical(self):
        mgr = AlertManager("https://hook.example/x", rate_limit_per_hour=3)
        # Distinct titles to avoid dedupe; 4th should be dropped.
        results = [await mgr.warn(f"t{i}", "m") for i in range(4)]
        assert results == [True, True, True, False]

    async def test_critical_bypasses_rate_limit(self):
        mgr = AlertManager("https://hook.example/x", rate_limit_per_hour=1)
        assert await mgr.warn("t0", "m") is True  # fills the bucket
        assert await mgr.warn("t1", "m") is False  # rate-limited
        assert await mgr.critical("t2", "m") is True  # bypasses limit

    async def test_critical_still_deduped(self):
        mgr = AlertManager("https://hook.example/x", rate_limit_per_hour=100)
        assert await mgr.critical("crit", "m") is True
        assert await mgr.critical("crit", "m") is False  # dedupe still applies
