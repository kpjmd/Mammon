"""Tests for AsyncBridge.

The bridge exists because coinbase-agentkit's ``_run_async`` cannot be called
from an async context. These tests pin that the replacement works in BOTH
contexts, since the failing one is precisely how WalletManager calls it.
"""

import asyncio

import pytest

from src.wallet.async_bridge import AsyncBridge


@pytest.fixture
def bridge():
    """Provide an AsyncBridge that is always closed after the test."""
    b = AsyncBridge()
    yield b
    b.close()


async def _echo(value, delay=0.0):
    """Trivial coroutine used as bridge payload."""
    if delay:
        await asyncio.sleep(delay)
    return value


def test_run_without_running_loop(bridge):
    """Bridge works when the caller has no event loop."""
    assert bridge.run(_echo("ok")) == "ok"


def test_run_inside_running_loop(bridge):
    """Bridge works when called synchronously from inside a running loop.

    This is the WalletManager case and the exact scenario where AgentKit's
    ``loop.run_until_complete`` raises "This event loop is already running".
    """

    async def caller():
        # Synchronous bridge call from async context -- must not raise.
        return bridge.run(_echo("from-async"))

    assert asyncio.run(caller()) == "from-async"


def test_bridge_does_not_depend_on_nest_asyncio_monkeypatch():
    """Document WHY the bridge exists: it needs no global asyncio patching.

    AgentKit's ``run_until_complete``-from-async pattern is invalid on stock
    asyncio ("This event loop is already running"). It nonetheless works in
    this project only because the CDP SDK calls ``nest_asyncio.apply()`` at
    import time (``cdp/evm_local_account.py``), globally monkeypatching
    asyncio as an import side effect.

    That is a fragile foundation: it is action-at-a-distance from a
    third-party import, and it silently disappears if the SDK drops the call.
    The bridge is correct on stock asyncio, so it does not care either way.

    This test asserts the bridge works while the patch is active; the
    surrounding tests cover the no-loop and inside-loop cases directly.
    """
    import sys

    # The CDP SDK is imported by the provider module; confirm the patch is in
    # play so the rationale above stays accurate as dependencies change.
    import src.wallet.cdp_mpc_provider  # noqa: F401

    assert "nest_asyncio" in sys.modules, (
        "CDP SDK no longer applies nest_asyncio. AgentKit's _run_async would "
        "now genuinely fail from async callers -- update the rationale in "
        "src/wallet/async_bridge.py."
    )

    async def caller():
        with AsyncBridge() as b:
            return b.run(_echo("independent"))

    assert asyncio.run(caller()) == "independent"


def test_exception_propagates_to_caller(bridge):
    """Exceptions raised in the coroutine surface in the calling thread."""

    async def boom():
        raise ValueError("propagated")

    with pytest.raises(ValueError, match="propagated"):
        bridge.run(boom())


def test_sequential_calls_reuse_same_loop(bridge):
    """The bridge is reusable across many calls."""
    assert [bridge.run(_echo(i)) for i in range(5)] == [0, 1, 2, 3, 4]


def test_timeout_raises(bridge):
    """A call exceeding its timeout raises rather than hanging forever."""
    from concurrent.futures import TimeoutError as FuturesTimeoutError

    with pytest.raises(FuturesTimeoutError):
        bridge.run(_echo("slow", delay=5.0), timeout=0.05)


def test_close_is_idempotent():
    """close() may be called repeatedly without error."""
    b = AsyncBridge()
    b.close()
    b.close()


def test_run_after_close_raises():
    """Submitting work to a closed bridge fails fast."""
    b = AsyncBridge()
    b.close()

    coro = _echo("x")
    with pytest.raises(RuntimeError, match="closed"):
        b.run(coro)
    coro.close()


def test_context_manager_closes():
    """The context manager form closes the bridge on exit."""
    with AsyncBridge() as b:
        assert b.run(_echo("ctx")) == "ctx"

    coro = _echo("y")
    with pytest.raises(RuntimeError, match="closed"):
        b.run(coro)
    coro.close()
