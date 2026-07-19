"""Synchronous bridge to async-only SDKs.

The :class:`~src.wallet.base_provider.WalletProvider` interface is synchronous,
but the CDP SDK is async-only. ``WalletManager`` calls providers from inside
``async def`` methods, so a naive bridge deadlocks or raises.

Why not the obvious approaches:

- ``asyncio.run(coro)`` raises ``RuntimeError: asyncio.run() cannot be called
  from a running event loop``.
- ``asyncio.get_event_loop().run_until_complete(coro)`` returns the *running*
  loop when one exists, then raises ``RuntimeError: This event loop is already
  running``.

coinbase-agentkit 0.7.4 uses the second pattern (``cdp_evm_wallet_provider.py``
``_run_async``). On stock asyncio that is simply invalid from an async caller.

It does not currently blow up in this project, but only by accident: the CDP
SDK calls ``nest_asyncio.apply()`` at import time
(``cdp/evm_local_account.py``), globally monkeypatching asyncio so nested
``run_until_complete`` becomes legal. That is action-at-a-distance from a
transitive import -- it applies process-wide, affects unrelated code, and
vanishes silently if the SDK ever drops the call.

This module does not rely on that. It owns a private event loop on a dedicated
daemon thread and submits coroutines with ``run_coroutine_threadsafe``, which
is valid on stock asyncio whether or not the calling thread already has a
running loop -- the loop we block on is never the caller's.
"""

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Awaitable, Optional, TypeVar

from src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Default ceiling for a single CDP round trip. Bounded so a hung network call
# surfaces as a timeout instead of wedging the autonomous loop forever.
DEFAULT_CALL_TIMEOUT_SECONDS = 120.0


class AsyncBridge:
    """Runs coroutines on a dedicated background event loop.

    Thread-safe and reusable. The loop thread is a daemon, so it will not keep
    the interpreter alive if ``close`` is never called.

    Attributes:
        timeout: Default per-call timeout in seconds.
    """

    def __init__(self, timeout: float = DEFAULT_CALL_TIMEOUT_SECONDS) -> None:
        """Start the background loop thread.

        Args:
            timeout: Default per-call timeout in seconds.
        """
        self.timeout = timeout
        self._closed = False
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="mammon-cdp-async-bridge",
            daemon=True,
        )
        self._thread.start()
        # Block until the loop is actually spinning, otherwise an immediate
        # run() could submit to a loop that is not yet running.
        self._ready.wait(timeout=10.0)
        if not self._ready.is_set():
            raise RuntimeError("AsyncBridge event loop failed to start")

    def _run_loop(self) -> None:
        """Thread entrypoint: own and run the private event loop forever."""
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._ready.set)
        self._loop.run_forever()

    def run(self, coro: Awaitable[T], timeout: Optional[float] = None) -> T:
        """Run a coroutine on the background loop and return its result.

        Args:
            coro: The coroutine to execute.
            timeout: Override for the default per-call timeout.

        Returns:
            Whatever the coroutine returns.

        Raises:
            RuntimeError: If the bridge has been closed.
            concurrent.futures.TimeoutError: If the call exceeds the timeout.
            Exception: Any exception raised inside the coroutine is re-raised
                in the calling thread.
        """
        if self._closed:
            raise RuntimeError("AsyncBridge is closed; cannot submit new work")

        future: "Future[T]" = asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[arg-type]
        result: T = future.result(timeout=timeout if timeout is not None else self.timeout)
        return result

    def close(self) -> None:
        """Stop the background loop and join its thread.

        Idempotent. Safe to call from any thread other than the loop thread.
        """
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10.0)
        if self._thread.is_alive():
            logger.warning("AsyncBridge loop thread did not exit within 10s")
            return
        self._loop.close()

    def __enter__(self) -> "AsyncBridge":
        """Context-manager entry."""
        return self

    def __exit__(self, *exc: Any) -> None:
        """Context-manager exit; always closes the bridge."""
        self.close()
