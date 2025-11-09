"""Unit tests for Aerodrome protocol integration."""

import pytest
from decimal import Decimal
from src.protocols.aerodrome import AerodromeProtocol, AERODROME_CONTRACTS


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "network": "base-sepolia",
        "dry_run_mode": True,
    }


@pytest.mark.asyncio
async def test_aerodrome_initialization(mock_config):
    """Test Aerodrome protocol initialization."""
    aerodrome = AerodromeProtocol(mock_config)

    assert aerodrome.name == "Aerodrome"
    assert aerodrome.chain == "base"
    assert aerodrome.network == "base-sepolia"
    assert aerodrome.dry_run_mode is True


@pytest.mark.asyncio
async def test_get_pools_returns_mock_data(mock_config):
    """Test getting pools returns mock pool data in Phase 1B."""
    aerodrome = AerodromeProtocol(mock_config)

    pools = await aerodrome.get_pools()

    assert len(pools) > 0
    assert all(hasattr(pool, "pool_id") for pool in pools)
    assert all(hasattr(pool, "apy") for pool in pools)
    assert all(hasattr(pool, "tvl") for pool in pools)
    assert all(hasattr(pool, "tokens") for pool in pools)


@pytest.mark.asyncio
async def test_get_pools_mock_data_structure(mock_config):
    """Test mock pool data has expected structure."""
    aerodrome = AerodromeProtocol(mock_config)

    pools = await aerodrome.get_pools()
    first_pool = pools[0]

    assert isinstance(first_pool.pool_id, str)
    assert isinstance(first_pool.name, str)
    assert isinstance(first_pool.apy, Decimal)
    assert isinstance(first_pool.tvl, Decimal)
    assert isinstance(first_pool.tokens, list)
    assert len(first_pool.tokens) > 0


@pytest.mark.asyncio
async def test_get_pool_apy_existing_pool(mock_config):
    """Test getting APY for an existing pool."""
    aerodrome = AerodromeProtocol(mock_config)

    # Get pools first to know valid pool ID
    pools = await aerodrome.get_pools()
    test_pool_id = pools[0].pool_id
    expected_apy = pools[0].apy

    # Get APY for that pool
    apy = await aerodrome.get_pool_apy(test_pool_id)

    assert apy == expected_apy
    assert apy > 0


@pytest.mark.asyncio
async def test_get_pool_apy_nonexistent_pool(mock_config):
    """Test getting APY for non-existent pool returns zero."""
    aerodrome = AerodromeProtocol(mock_config)

    apy = await aerodrome.get_pool_apy("nonexistent-pool")

    assert apy == Decimal("0")


@pytest.mark.asyncio
async def test_deposit_dry_run(mock_config):
    """Test deposit in dry-run mode returns simulated hash."""
    aerodrome = AerodromeProtocol(mock_config)

    tx_hash = await aerodrome.deposit(
        pool_id="test-pool",
        token="USDC",
        amount=Decimal("100")
    )

    assert tx_hash.startswith("dry_run_deposit_")
    assert "test-pool" in tx_hash
    assert "100" in tx_hash


@pytest.mark.asyncio
async def test_deposit_live_mode_raises(mock_config):
    """Test deposit in live mode raises NotImplementedError."""
    mock_config["dry_run_mode"] = False
    aerodrome = AerodromeProtocol(mock_config)

    with pytest.raises(NotImplementedError, match="Live deposits not implemented"):
        await aerodrome.deposit(
            pool_id="test-pool",
            token="USDC",
            amount=Decimal("100")
        )


@pytest.mark.asyncio
async def test_withdraw_dry_run(mock_config):
    """Test withdraw in dry-run mode returns simulated hash."""
    aerodrome = AerodromeProtocol(mock_config)

    tx_hash = await aerodrome.withdraw(
        pool_id="test-pool",
        token="USDC",
        amount=Decimal("50")
    )

    assert tx_hash.startswith("dry_run_withdraw_")
    assert "test-pool" in tx_hash
    assert "50" in tx_hash


@pytest.mark.asyncio
async def test_withdraw_live_mode_raises(mock_config):
    """Test withdraw in live mode raises NotImplementedError."""
    mock_config["dry_run_mode"] = False
    aerodrome = AerodromeProtocol(mock_config)

    with pytest.raises(NotImplementedError, match="Live withdrawals not implemented"):
        await aerodrome.withdraw(
            pool_id="test-pool",
            token="USDC",
            amount=Decimal("50")
        )


@pytest.mark.asyncio
async def test_get_user_balance_returns_mock(mock_config):
    """Test getting user balance returns mock data."""
    aerodrome = AerodromeProtocol(mock_config)

    balance = await aerodrome.get_user_balance(
        pool_id="test-pool",
        user_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"
    )

    assert isinstance(balance, Decimal)
    assert balance >= 0


@pytest.mark.asyncio
async def test_estimate_gas_deposit(mock_config):
    """Test gas estimation for deposit operation."""
    aerodrome = AerodromeProtocol(mock_config)

    gas = await aerodrome.estimate_gas("deposit", {})

    assert gas == 250000


@pytest.mark.asyncio
async def test_estimate_gas_withdraw(mock_config):
    """Test gas estimation for withdraw operation."""
    aerodrome = AerodromeProtocol(mock_config)

    gas = await aerodrome.estimate_gas("withdraw", {})

    assert gas == 200000


@pytest.mark.asyncio
async def test_estimate_gas_swap(mock_config):
    """Test gas estimation for swap operation."""
    aerodrome = AerodromeProtocol(mock_config)

    gas = await aerodrome.estimate_gas("swap", {})

    assert gas == 180000


@pytest.mark.asyncio
async def test_estimate_gas_unknown_operation(mock_config):
    """Test gas estimation for unknown operation returns default."""
    aerodrome = AerodromeProtocol(mock_config)

    gas = await aerodrome.estimate_gas("unknown", {})

    assert gas == 150000


@pytest.mark.asyncio
async def test_build_swap_transaction_dry_run(mock_config):
    """Test building swap transaction in dry-run mode."""
    aerodrome = AerodromeProtocol(mock_config)

    result = await aerodrome.build_swap_transaction(
        token_in="USDC",
        token_out="WETH",
        amount_in=Decimal("1000"),
        slippage=Decimal("0.5")
    )

    assert result["dry_run"] is True
    assert result["would_execute"] is False
    assert "swap_details" in result
    assert result["swap_details"]["token_in"] == "USDC"
    assert result["swap_details"]["token_out"] == "WETH"


@pytest.mark.asyncio
async def test_build_swap_transaction_slippage_calculation(mock_config):
    """Test swap transaction calculates minimum output correctly."""
    aerodrome = AerodromeProtocol(mock_config)

    result = await aerodrome.build_swap_transaction(
        token_in="USDC",
        token_out="WETH",
        amount_in=Decimal("1000"),
        slippage=Decimal("0.5")  # 0.5%
    )

    swap_details = result["swap_details"]
    amount_in = Decimal(swap_details["amount_in"])
    min_amount_out = Decimal(swap_details["min_amount_out"])

    # Min output should be amount_in * (1 - 0.005)
    expected_min = amount_in * Decimal("0.995")
    assert min_amount_out == expected_min


@pytest.mark.asyncio
async def test_build_swap_transaction_live_mode(mock_config):
    """Test building swap transaction in live mode."""
    mock_config["dry_run_mode"] = False
    aerodrome = AerodromeProtocol(mock_config)

    result = await aerodrome.build_swap_transaction(
        token_in="USDC",
        token_out="WETH",
        amount_in=Decimal("1000"),
        slippage=Decimal("0.5")
    )

    # In live mode, should return transaction object (not wrapped in dry_run dict)
    assert "token_in" in result
    assert "token_out" in result
    assert result["token_in"] == "USDC"


@pytest.mark.asyncio
async def test_contract_addresses_base_mainnet():
    """Test Aerodrome contract addresses for base-mainnet."""
    contracts = AERODROME_CONTRACTS["base-mainnet"]

    assert "router" in contracts
    assert "aero_token" in contracts
    assert contracts["router"] == "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"
    assert contracts["aero_token"] == "0x940181a94A35A4569E4529A3CDfB74e38FD98631"


@pytest.mark.asyncio
async def test_contract_addresses_base_sepolia():
    """Test Aerodrome contract addresses for base-sepolia."""
    contracts = AERODROME_CONTRACTS["base-sepolia"]

    assert "router" in contracts
    assert "factory" in contracts
    # Sepolia uses mock addresses for Phase 1B
    assert contracts["router"] is not None
