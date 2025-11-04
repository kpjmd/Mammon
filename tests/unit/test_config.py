"""Unit tests for configuration management."""

import pytest
from src.utils.config import Settings
from pydantic import ValidationError


def test_settings_validation() -> None:
    """Test that settings validation works correctly."""
    # This will fail with placeholder values - that's expected
    with pytest.raises(ValidationError):
        Settings(
            cdp_api_key="your_key_here",
            cdp_api_secret="test_secret",
            anthropic_api_key="test_key",
        )


def test_environment_validation() -> None:
    """Test environment validation."""
    with pytest.raises(ValidationError):
        Settings(
            cdp_api_key="real_key",
            cdp_api_secret="real_secret",
            anthropic_api_key="real_key",
            wallet_seed="abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
            environment="invalid_env",
        )


def test_wallet_seed_validation_required() -> None:
    """Test wallet_seed is required (cannot be None)."""
    with pytest.raises(ValidationError, match="wallet_seed"):
        Settings(
            cdp_api_key="valid_key",
            cdp_api_secret="valid_secret",
            anthropic_api_key="valid_key",
            # wallet_seed not provided - should fail
        )


def test_wallet_seed_validation_empty() -> None:
    """Test wallet_seed rejects empty strings."""
    with pytest.raises(ValidationError, match="wallet_seed is required"):
        Settings(
            cdp_api_key="valid_key",
            cdp_api_secret="valid_secret",
            anthropic_api_key="valid_key",
            wallet_seed="",  # Empty string should fail
        )


def test_wallet_seed_validation_whitespace() -> None:
    """Test wallet_seed rejects whitespace-only strings."""
    with pytest.raises(ValidationError, match="wallet_seed is required"):
        Settings(
            cdp_api_key="valid_key",
            cdp_api_secret="valid_secret",
            anthropic_api_key="valid_key",
            wallet_seed="   ",  # Whitespace only should fail
        )


def test_wallet_seed_validation_placeholder() -> None:
    """Test wallet_seed rejects placeholders."""
    with pytest.raises(ValidationError, match="placeholder"):
        Settings(
            cdp_api_key="valid_key",
            cdp_api_secret="valid_secret",
            anthropic_api_key="valid_key",
            wallet_seed="your_wallet_seed_here",  # Placeholder should fail
        )


def test_wallet_seed_validation_invalid_bip39() -> None:
    """Test wallet_seed rejects invalid BIP39 phrases."""
    with pytest.raises(ValidationError, match="Invalid BIP39"):
        Settings(
            cdp_api_key="valid_key",
            cdp_api_secret="valid_secret",
            anthropic_api_key="valid_key",
            wallet_seed="this is not a valid bip39 seed phrase",  # Invalid words
        )


def test_wallet_seed_validation_wrong_word_count() -> None:
    """Test wallet_seed rejects phrases with wrong word count."""
    with pytest.raises(ValidationError, match="Invalid BIP39"):
        Settings(
            cdp_api_key="valid_key",
            cdp_api_secret="valid_secret",
            anthropic_api_key="valid_key",
            wallet_seed="abandon abandon abandon",  # Only 3 words, invalid
        )


def test_wallet_seed_validation_valid_12_words() -> None:
    """Test wallet_seed accepts valid 12-word BIP39 phrase."""
    # Standard test mnemonic (NEVER use in production!)
    test_mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"

    settings = Settings(
        cdp_api_key="valid_key",
        cdp_api_secret="valid_secret",
        anthropic_api_key="valid_key",
        wallet_seed=test_mnemonic,
    )
    assert settings.wallet_seed == test_mnemonic


def test_wallet_seed_validation_valid_24_words() -> None:
    """Test wallet_seed accepts valid 24-word BIP39 phrase."""
    # Standard test mnemonic (NEVER use in production!)
    test_mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon art"

    settings = Settings(
        cdp_api_key="valid_key",
        cdp_api_secret="valid_secret",
        anthropic_api_key="valid_key",
        wallet_seed=test_mnemonic,
    )
    assert settings.wallet_seed == test_mnemonic


def test_wallet_seed_strips_whitespace() -> None:
    """Test wallet_seed strips leading/trailing whitespace."""
    test_mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"

    settings = Settings(
        cdp_api_key="valid_key",
        cdp_api_secret="valid_secret",
        anthropic_api_key="valid_key",
        wallet_seed=f"  {test_mnemonic}  ",  # Extra whitespace
    )
    # Should be stripped
    assert settings.wallet_seed == test_mnemonic
