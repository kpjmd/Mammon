"""Pytest configuration and fixtures for MAMMON tests."""

import pytest
from decimal import Decimal
from typing import Dict, Any


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Provide mock configuration for tests.

    Returns:
        Mock configuration dictionary
    """
    return {
        "cdp_api_key": "test_api_key",
        "cdp_api_secret": "test_api_secret",
        "wallet_seed": "test_seed_phrase",
        "base_rpc_url": "https://sepolia.base.org",
        "anthropic_api_key": "test_anthropic_key",
        "max_transaction_value_usd": Decimal("1000"),
        "daily_spending_limit_usd": Decimal("5000"),
        "approval_threshold_usd": Decimal("100"),
        "environment": "test",
        "log_level": "DEBUG",
        "database_url": "sqlite:///:memory:",
    }


@pytest.fixture
def mock_wallet_address() -> str:
    """Provide mock wallet address for tests.

    Returns:
        Mock wallet address
    """
    return "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"


@pytest.fixture
def sample_yield_opportunity() -> Dict[str, Any]:
    """Provide sample yield opportunity for tests.

    Returns:
        Sample yield opportunity data
    """
    return {
        "protocol": "Aerodrome",
        "pool_id": "USDC-ETH",
        "apy": Decimal("0.15"),
        "tvl": Decimal("1000000"),
        "token": "USDC",
    }
