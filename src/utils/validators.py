"""Input validation utilities for security and data integrity.

This module provides validators for addresses, amounts, and other
inputs to prevent invalid or malicious data from entering the system.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional


class ValidationError(Exception):
    """Raised when input validation fails."""

    pass


def validate_ethereum_address(address: str) -> str:
    """Validate an Ethereum address format.

    Args:
        address: Address to validate

    Returns:
        Validated address

    Raises:
        ValidationError: If address is invalid
    """
    if not address:
        raise ValidationError("Address cannot be empty")

    # Remove 0x prefix if present
    if address.startswith("0x"):
        address = address[2:]

    # Check if hexadecimal and correct length
    if len(address) != 40:
        raise ValidationError(f"Invalid address length: {len(address)}, expected 40")

    if not re.match(r"^[0-9a-fA-F]{40}$", address):
        raise ValidationError("Address contains invalid characters")

    return f"0x{address}"


def is_valid_ethereum_address(address: str) -> bool:
    """Check if an Ethereum address is valid (helper function).

    Args:
        address: Address to check

    Returns:
        True if valid, False otherwise
    """
    try:
        validate_ethereum_address(address)
        return True
    except ValidationError:
        return False


def validate_transaction_hash(tx_hash: str) -> str:
    """Validate a transaction hash format.

    Args:
        tx_hash: Transaction hash to validate

    Returns:
        Validated transaction hash

    Raises:
        ValidationError: If hash is invalid
    """
    if not tx_hash:
        raise ValidationError("Transaction hash cannot be empty")

    # Remove 0x prefix if present
    if tx_hash.startswith("0x"):
        tx_hash = tx_hash[2:]

    # Check if hexadecimal and correct length
    if len(tx_hash) != 64:
        raise ValidationError(f"Invalid hash length: {len(tx_hash)}, expected 64")

    if not re.match(r"^[0-9a-fA-F]{64}$", tx_hash):
        raise ValidationError("Hash contains invalid characters")

    return f"0x{tx_hash}"


def validate_amount(
    amount: Decimal | str | float,
    min_value: Optional[Decimal] = None,
    max_value: Optional[Decimal] = None,
    decimals: int = 18,
) -> Decimal:
    """Validate a token amount.

    Args:
        amount: Amount to validate
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        decimals: Maximum decimal places

    Returns:
        Validated amount as Decimal

    Raises:
        ValidationError: If amount is invalid
    """
    try:
        # Convert to Decimal
        if isinstance(amount, str):
            decimal_amount = Decimal(amount)
        elif isinstance(amount, float):
            decimal_amount = Decimal(str(amount))
        else:
            decimal_amount = amount

        # Check if positive
        if decimal_amount < 0:
            raise ValidationError("Amount cannot be negative")

        # Check decimal places
        if decimal_amount.as_tuple().exponent < -decimals:
            raise ValidationError(f"Amount has too many decimal places (max {decimals})")

        # Check min value
        if min_value is not None and decimal_amount < min_value:
            raise ValidationError(f"Amount {decimal_amount} is below minimum {min_value}")

        # Check max value
        if max_value is not None and decimal_amount > max_value:
            raise ValidationError(f"Amount {decimal_amount} exceeds maximum {max_value}")

        return decimal_amount

    except (InvalidOperation, ValueError) as e:
        raise ValidationError(f"Invalid amount format: {e}")


def validate_apy(apy: Decimal | str | float) -> Decimal:
    """Validate an APY value.

    Args:
        apy: APY to validate (as decimal, e.g., 0.05 for 5%)

    Returns:
        Validated APY as Decimal

    Raises:
        ValidationError: If APY is invalid
    """
    validated = validate_amount(apy, min_value=Decimal("0"), max_value=Decimal("10"))

    # Warn if APY seems unreasonably high (>100% = 1.0)
    if validated > Decimal("1.0"):
        # Allow it but could log a warning in production
        pass

    return validated


def validate_protocol_name(protocol: str) -> str:
    """Validate a protocol name.

    Args:
        protocol: Protocol name to validate

    Returns:
        Validated protocol name

    Raises:
        ValidationError: If protocol name is invalid
    """
    if not protocol:
        raise ValidationError("Protocol name cannot be empty")

    # Alphanumeric, hyphens, underscores only
    if not re.match(r"^[a-zA-Z0-9_-]+$", protocol):
        raise ValidationError("Protocol name contains invalid characters")

    if len(protocol) > 50:
        raise ValidationError("Protocol name too long (max 50 characters)")

    return protocol


def validate_token_symbol(symbol: str) -> str:
    """Validate a token symbol.

    Args:
        symbol: Token symbol to validate

    Returns:
        Validated token symbol (uppercase)

    Raises:
        ValidationError: If symbol is invalid
    """
    if not symbol:
        raise ValidationError("Token symbol cannot be empty")

    # Alphanumeric only, typically 2-10 characters
    if not re.match(r"^[a-zA-Z0-9]+$", symbol):
        raise ValidationError("Token symbol contains invalid characters")

    if len(symbol) < 2 or len(symbol) > 10:
        raise ValidationError("Token symbol must be 2-10 characters")

    return symbol.upper()


def validate_url(url: str, require_https: bool = True) -> str:
    """Validate a URL.

    Args:
        url: URL to validate
        require_https: Require HTTPS protocol

    Returns:
        Validated URL

    Raises:
        ValidationError: If URL is invalid
    """
    if not url:
        raise ValidationError("URL cannot be empty")

    # Basic URL pattern
    url_pattern = r"^https?://[a-zA-Z0-9.-]+(?:\.[a-zA-Z]{2,})+(?:/.*)?$"
    if not re.match(url_pattern, url):
        raise ValidationError("Invalid URL format")

    if require_https and not url.startswith("https://"):
        raise ValidationError("URL must use HTTPS")

    return url


def sanitize_input(input_str: str, max_length: int = 1000) -> str:
    """Sanitize string input to prevent injection attacks.

    Args:
        input_str: Input string to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string

    Raises:
        ValidationError: If input is invalid
    """
    if not isinstance(input_str, str):
        raise ValidationError("Input must be a string")

    # Check length
    if len(input_str) > max_length:
        raise ValidationError(f"Input too long (max {max_length} characters)")

    # Remove null bytes
    sanitized = input_str.replace("\x00", "")

    # Strip leading/trailing whitespace
    sanitized = sanitized.strip()

    return sanitized
