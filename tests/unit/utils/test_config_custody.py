"""Tests for custody-mode configuration (WS7).

The load-bearing property: CDP MPC custody must NOT require a local seed.
Requiring one unconditionally would force key material onto the machine,
defeating the point of TEE custody -- and it is precisely the plaintext-seed
exposure that caused the 2025-12-02 wallet drain.
"""

import pytest

from src.utils.config import Settings

VALID_SEED = "test test test test test test test test test test test junk"

BASE_KWARGS = dict(
    cdp_api_key="test-key",
    cdp_api_secret="test-secret",
    cdp_wallet_secret="test-wallet-secret",
    anthropic_api_key="test-anthropic-key",
    _env_file=None,  # ignore any real .env on the machine running the tests
)


def _settings(**overrides) -> Settings:
    """Build Settings with test defaults, bypassing .env."""
    kwargs = dict(BASE_KWARGS)
    kwargs.update(overrides)
    return Settings(**kwargs)


class TestCdpCustodyNeedsNoSeed:
    """CDP MPC mode must work with no local key material at all."""

    def test_cdp_mode_without_seed_is_valid(self):
        """The core WS7 guarantee."""
        settings = _settings(use_local_wallet=False, wallet_seed=None)

        assert settings.use_local_wallet is False
        assert settings.wallet_seed is None

    def test_cdp_mode_defaults_account_name(self):
        """A default persistence handle exists so custody is never ephemeral."""
        settings = _settings(use_local_wallet=False, wallet_seed=None)

        assert settings.cdp_account_name == "mammon-hot"

    def test_expected_address_defaults_to_none(self):
        """The address guard is opt-in."""
        settings = _settings(use_local_wallet=False, wallet_seed=None)

        assert settings.cdp_expected_address is None


class TestLocalCustodyRequiresSeed:
    """Local mode still needs a seed, and says so clearly."""

    def test_local_mode_without_seed_raises(self):
        """Refuse to start local custody with no key material."""
        with pytest.raises(ValueError, match="wallet_seed is required"):
            _settings(use_local_wallet=True, wallet_seed=None)

    def test_local_mode_error_mentions_the_cdp_alternative(self):
        """The error should point at the better option, not just complain."""
        with pytest.raises(ValueError, match="USE_LOCAL_WALLET=false"):
            _settings(use_local_wallet=True, wallet_seed=None)

    def test_local_mode_with_seed_is_valid(self):
        """The existing happy path still works."""
        settings = _settings(use_local_wallet=True, wallet_seed=VALID_SEED)

        assert settings.wallet_seed == VALID_SEED

    def test_malformed_seed_still_rejected(self):
        """Seed validation is relaxed for absence, not for garbage."""
        with pytest.raises(ValueError, match="Invalid BIP39 seed phrase"):
            _settings(use_local_wallet=True, wallet_seed="only three words")

    def test_placeholder_seed_still_rejected(self):
        """The .env.example placeholder must not pass as a real seed."""
        with pytest.raises(ValueError, match="placeholder"):
            _settings(use_local_wallet=True, wallet_seed="your_wallet_seed_phrase_here")


class TestDefaults:
    """Cutover safety: the default must not silently change custody."""

    def test_local_wallet_remains_the_default(self):
        """WS7 ships the CDP path but does not flip the default."""
        settings = _settings(wallet_seed=VALID_SEED)

        assert settings.use_local_wallet is True
