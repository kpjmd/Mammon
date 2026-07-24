"""The per-day rails in .env must actually reach the runner.

MAX_REBALANCES_PER_DAY / MAX_GAS_PER_DAY_USD are loaded and *validated* by
Settings, but main() used to pass hardcoded CLI defaults (6/day, $10/day gas)
straight through, so those .env values were silently ignored. A systemd unit
that passes neither flag therefore ran with limits the operator never chose --
including a gas backstop 5x looser than configured.

.env is now authoritative; an explicit CLI flag overrides it.
"""

from decimal import Decimal

import pytest

import scripts.run_autonomous_optimizer as runner_module
import src.utils.config as config_module


class _Captured(Exception):
    """Abort main() as soon as the runner is constructed."""

    def __init__(self, kwargs):
        self.kwargs = kwargs


def _capture_runner(monkeypatch):
    """Replace AutonomousRunner so we can inspect the resolved kwargs."""

    def _fake(**kwargs):
        raise _Captured(kwargs)

    monkeypatch.setattr(runner_module, "AutonomousRunner", _fake)


async def _run_main(monkeypatch, argv):
    _capture_runner(monkeypatch)
    monkeypatch.setattr(runner_module.sys, "argv", ["run_autonomous_optimizer.py"] + argv)
    with pytest.raises(_Captured) as exc:
        await runner_module.main()
    return exc.value.kwargs


@pytest.mark.asyncio
async def test_env_values_are_used_when_no_cli_flags(monkeypatch):
    """No flags -> the .env / Settings values win (not the old 6 / $10)."""
    monkeypatch.setenv("MAX_REBALANCES_PER_DAY", "20")
    monkeypatch.setenv("MAX_GAS_PER_DAY_USD", "2.0")
    monkeypatch.setattr(config_module, "_settings", None, raising=False)

    kwargs = await _run_main(monkeypatch, [])

    assert kwargs["max_rebalances_per_day"] == 20
    assert Decimal(str(kwargs["max_gas_per_day_usd"])) == Decimal("2.0")


@pytest.mark.asyncio
async def test_cli_flags_override_env(monkeypatch):
    monkeypatch.setenv("MAX_REBALANCES_PER_DAY", "20")
    monkeypatch.setenv("MAX_GAS_PER_DAY_USD", "2.0")
    monkeypatch.setattr(config_module, "_settings", None, raising=False)

    kwargs = await _run_main(monkeypatch, ["--max-rebalances", "7", "--max-gas", "3.5"])

    assert kwargs["max_rebalances_per_day"] == 7
    assert Decimal(str(kwargs["max_gas_per_day_usd"])) == Decimal("3.5")
