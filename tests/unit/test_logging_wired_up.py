"""The entrypoint must configure logging, or every logger.info is dropped.

get_logger() only calls logging.getLogger(); it never attaches a handler, and
setup_logging() was never invoked anywhere. Python's lastResort handler then
applies -- WARNING+ to stderr, INFO/DEBUG discarded entirely. Under systemd the
whole INFO operational trail was missing from the journal (bare print() output
still showed, which made it look like logging worked).
"""

import logging

import pytest

import scripts.run_autonomous_optimizer as runner_module
import src.utils.config as config_module


class _Captured(Exception):
    def __init__(self, kwargs):
        self.kwargs = kwargs


@pytest.mark.asyncio
async def test_main_configures_logging(monkeypatch):
    def _fake(**kwargs):
        raise _Captured(kwargs)

    monkeypatch.setattr(runner_module, "AutonomousRunner", _fake)
    monkeypatch.setattr(
        runner_module.sys, "argv", ["run_autonomous_optimizer.py"]
    )
    monkeypatch.setattr(config_module, "_settings", None, raising=False)

    mammon_logger = logging.getLogger("mammon")
    mammon_logger.handlers = []  # simulate an unconfigured process

    with pytest.raises(_Captured):
        await runner_module.main()

    assert mammon_logger.handlers, "main() must attach a handler to 'mammon'"
    # INFO must actually be emitted, not filtered out.
    assert mammon_logger.isEnabledFor(logging.INFO)


def test_get_logger_alone_does_not_configure_handlers():
    """Documents why the entrypoint call is required (regression context)."""
    logging.getLogger("mammon").handlers = []
    from src.utils.logger import get_logger

    get_logger("some.module")
    assert not logging.getLogger("mammon").handlers
