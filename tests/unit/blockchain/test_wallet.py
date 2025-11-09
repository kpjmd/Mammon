"""Unit tests for wallet management module."""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.blockchain.wallet import WalletManager
from src.security.audit import AuditEventType


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "cdp_api_key": "test_api_key",
        "cdp_api_secret": "test_api_secret",
        "network": "base-sepolia",
        "dry_run_mode": True,
        "max_transaction_value_usd": Decimal("1000"),
        "daily_spending_limit_usd": Decimal("5000"),
        "wallet_id": "test-wallet-id-123",
    }


@pytest.fixture
def mock_wallet_provider():
    """Mock CDP wallet provider instance."""
    provider = AsyncMock()
    provider.get_address = AsyncMock(return_value="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb44")
    provider.get_balance = AsyncMock(return_value=Decimal("1.5"))
    provider.export = AsyncMock(return_value={"encrypted": "wallet_data"})
    return provider


@pytest.mark.asyncio
async def test_wallet_initialization_dry_run(mock_config):
    """Test wallet manager initialization in dry-run mode."""
    wallet_manager = WalletManager(mock_config)

    assert wallet_manager.dry_run_mode is True
    assert wallet_manager.network == "base-sepolia"
    assert wallet_manager.wallet_provider is None
    assert wallet_manager.address is None


@pytest.mark.asyncio
async def test_wallet_initialization_live_mode(mock_config):
    """Test wallet manager initialization in live mode."""
    mock_config["dry_run_mode"] = False
    wallet_manager = WalletManager(mock_config)

    assert wallet_manager.dry_run_mode is False


@pytest.mark.asyncio
async def test_initialize_skipped_without_credentials():
    """Test that initialization requires proper config."""
    # Skip initialization tests for now - requires CDP API setup
    # These will be tested in integration tests
    pass


@pytest.mark.asyncio
async def test_get_balance_without_initialization():
    """Test getting balance before wallet initialization raises error."""
    wallet_manager = WalletManager({"dry_run_mode": True})

    with pytest.raises(ValueError, match="Wallet not initialized"):
        await wallet_manager.get_balance("ETH")


@pytest.mark.asyncio
async def test_get_balance_success(mock_config, mock_wallet_provider):
    """Test successfully getting wallet balance."""
    wallet_manager = WalletManager(mock_config)
    wallet_manager.wallet_provider = mock_wallet_provider

    balance = await wallet_manager.get_balance("eth")

    assert balance == Decimal("1.5")
    mock_wallet_provider.get_balance.assert_called_once_with("eth")


@pytest.mark.asyncio
async def test_get_balances_success(mock_config, mock_wallet_provider):
    """Test successfully getting all wallet balances."""
    wallet_manager = WalletManager(mock_config)
    wallet_manager.wallet_provider = mock_wallet_provider

    balances = await wallet_manager.get_balances()

    assert "eth" in balances
    assert balances["eth"] == Decimal("1.5")


@pytest.mark.asyncio
async def test_get_address(mock_config):
    """Test getting wallet address."""
    wallet_manager = WalletManager(mock_config)
    wallet_manager.address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"

    address = await wallet_manager.get_address()

    assert address == "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"


@pytest.mark.asyncio
async def test_get_address_not_initialized():
    """Test getting address before initialization raises error."""
    wallet_manager = WalletManager({"dry_run_mode": True})

    with pytest.raises(ValueError, match="Wallet not initialized"):
        await wallet_manager.get_address()


@pytest.mark.asyncio
async def test_spending_limits_check_pass(mock_config):
    """Test spending limit check passes for valid amount."""
    wallet_manager = WalletManager(mock_config)

    # Amount within limits
    result = await wallet_manager._check_spending_limits(Decimal("500"))

    assert result is True


@pytest.mark.asyncio
async def test_spending_limits_check_fail_transaction_limit(mock_config):
    """Test spending limit check fails when exceeding per-transaction limit."""
    wallet_manager = WalletManager(mock_config)

    # Amount exceeds per-transaction limit
    result = await wallet_manager._check_spending_limits(Decimal("1500"))

    assert result is False


@pytest.mark.asyncio
async def test_convert_to_usd_eth(mock_config):
    """Test converting ETH to USD."""
    wallet_manager = WalletManager(mock_config)

    # 1 ETH ~= $3000 (mock rate)
    usd_value = await wallet_manager._convert_to_usd(Decimal("1.0"), "ETH")

    assert usd_value == Decimal("3000")


@pytest.mark.asyncio
async def test_build_transaction_dry_run(mock_config, mock_wallet_provider):
    """Test building transaction in dry-run mode."""
    wallet_manager = WalletManager(mock_config)
    wallet_manager.wallet_provider = mock_wallet_provider
    wallet_manager.address = "0x123456789012345678901234567890123456789a"

    result = await wallet_manager.build_transaction(
        to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
        amount=Decimal("0.1"),
        token="ETH"
    )

    assert result["dry_run"] is True
    assert result["would_execute"] is False
    assert "transaction" in result
    assert result["transaction"]["to"] == "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"


@pytest.mark.asyncio
async def test_build_transaction_invalid_address(mock_config, mock_wallet_provider):
    """Test building transaction with invalid address raises error."""
    wallet_manager = WalletManager(mock_config)
    wallet_manager.wallet_provider = mock_wallet_provider
    wallet_manager.address = "0x123456789012345678901234567890123456789a"

    with pytest.raises(ValueError, match="Invalid recipient address"):
        await wallet_manager.build_transaction(
            to="invalid_address",
            amount=Decimal("0.1"),
            token="ETH"
        )


@pytest.mark.asyncio
async def test_build_transaction_exceeds_limits(mock_config, mock_wallet_provider):
    """Test building transaction that exceeds spending limits."""
    wallet_manager = WalletManager(mock_config)
    wallet_manager.wallet_provider = mock_wallet_provider
    wallet_manager.address = "0x123456789012345678901234567890123456789a"

    # Try to send 1 ETH = $3000, exceeds $1000 limit
    with pytest.raises(ValueError, match="exceeds spending limits"):
        await wallet_manager.build_transaction(
            to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
            amount=Decimal("1.0"),
            token="ETH"
        )


@pytest.mark.asyncio
async def test_export_wallet_data_dry_run(mock_config, mock_wallet_provider):
    """Test exporting wallet data with confirmation bypass."""
    wallet_manager = WalletManager(mock_config)
    wallet_manager.wallet_provider = mock_wallet_provider
    wallet_manager.address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"

    # Bypass confirmation for testing
    result = await wallet_manager.export_wallet_data(require_confirmation=False)

    assert result["address"] == "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"
    assert "warning" in result
    assert "CRITICAL" in result["warning"]


@pytest.mark.asyncio
async def test_is_connected_true(mock_config, mock_wallet_provider):
    """Test wallet connectivity check returns True when connected."""
    wallet_manager = WalletManager(mock_config)
    wallet_manager.wallet_provider = mock_wallet_provider
    wallet_manager.address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"

    is_connected = await wallet_manager.is_connected()

    assert is_connected is True


@pytest.mark.asyncio
async def test_is_connected_false_no_wallet():
    """Test wallet connectivity check returns False when not initialized."""
    wallet_manager = WalletManager({"dry_run_mode": True})

    is_connected = await wallet_manager.is_connected()

    assert is_connected is False
