"""Unit tests for input validators."""

import pytest
from decimal import Decimal
from src.utils.validators import (
    validate_ethereum_address,
    validate_amount,
    validate_token_symbol,
    ValidationError,
)


def test_validate_ethereum_address_valid() -> None:
    """Test Ethereum address validation with valid address."""
    address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
    result = validate_ethereum_address(address)
    assert result == address


def test_validate_ethereum_address_invalid_length() -> None:
    """Test Ethereum address validation with invalid length."""
    with pytest.raises(ValidationError):
        validate_ethereum_address("0x123")


def test_validate_amount_positive() -> None:
    """Test amount validation with positive value."""
    amount = validate_amount(Decimal("100.50"))
    assert amount == Decimal("100.50")


def test_validate_amount_negative() -> None:
    """Test amount validation rejects negative values."""
    with pytest.raises(ValidationError):
        validate_amount(Decimal("-10"))


def test_validate_token_symbol_valid() -> None:
    """Test token symbol validation."""
    result = validate_token_symbol("USDC")
    assert result == "USDC"


def test_validate_token_symbol_invalid() -> None:
    """Test token symbol validation rejects invalid symbols."""
    with pytest.raises(ValidationError):
        validate_token_symbol("INVALID_TOKEN_SYMBOL_TOO_LONG")


# Add more tests as needed
