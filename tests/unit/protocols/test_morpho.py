"""Unit tests for Morpho protocol integration.

Phase 3 Sprint 1: Tests for read-only Morpho implementation with mock data.
"""

import pytest
from decimal import Decimal
from src.protocols.morpho import MorphoProtocol, MORPHO_CONTRACTS


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "network": "base-sepolia",
        "use_mock_data": True,
        "read_only": True,
        "dry_run_mode": True,
    }


@pytest.mark.asyncio
async def test_morpho_initialization(mock_config):
    """Test Morpho protocol initialization."""
    morpho = MorphoProtocol(mock_config)

    assert morpho.name == "Morpho"
    assert morpho.chain == "base"
    assert morpho.network == "base-sepolia"
    assert morpho.use_mock_data is True
    assert morpho.read_only is True


@pytest.mark.asyncio
async def test_morpho_initialization_with_correct_contract_address(mock_config):
    """Test Morpho uses correct Base Sepolia contract address."""
    morpho = MorphoProtocol(mock_config)

    expected_address = "0x2DC205F24BCb6B311E5cdf0745B0741648Aebd3d"
    assert morpho.contracts.get("morpho_chainlink_oracle_v2") == expected_address


@pytest.mark.asyncio
async def test_morpho_safety_score(mock_config):
    """Test Morpho protocol safety score calculation."""
    morpho = MorphoProtocol(mock_config)

    # Morpho is well-audited, Coinbase-promoted, should have high score
    assert morpho.safety_score >= 85
    assert morpho.safety_score <= 100


@pytest.mark.asyncio
async def test_get_pools_returns_mock_data(mock_config):
    """Test getting pools returns mock lending market data."""
    morpho = MorphoProtocol(mock_config)

    pools = await morpho.get_pools()

    assert len(pools) > 0
    assert all(hasattr(pool, "pool_id") for pool in pools)
    assert all(hasattr(pool, "apy") for pool in pools)
    assert all(hasattr(pool, "tvl") for pool in pools)
    assert all(hasattr(pool, "tokens") for pool in pools)


@pytest.mark.asyncio
async def test_get_pools_contains_usdc_market(mock_config):
    """Test mock data includes USDC lending market."""
    morpho = MorphoProtocol(mock_config)

    pools = await morpho.get_pools()

    usdc_pools = [p for p in pools if "USDC" in p.tokens]
    assert len(usdc_pools) > 0, "Should have at least one USDC market"


@pytest.mark.asyncio
async def test_get_pools_contains_weth_market(mock_config):
    """Test mock data includes WETH lending market."""
    morpho = MorphoProtocol(mock_config)

    pools = await morpho.get_pools()

    weth_pools = [p for p in pools if "WETH" in p.tokens]
    assert len(weth_pools) > 0, "Should have at least one WETH market"


@pytest.mark.asyncio
async def test_get_pools_realistic_apys(mock_config):
    """Test mock APYs are realistic for lending protocols."""
    morpho = MorphoProtocol(mock_config)

    pools = await morpho.get_pools()

    for pool in pools:
        # Realistic lending APYs: 1-15% typically
        assert pool.apy >= Decimal("1.0"), f"APY too low: {pool.apy}%"
        assert pool.apy <= Decimal("15.0"), f"APY too high: {pool.apy}%"


@pytest.mark.asyncio
async def test_get_pools_has_metadata(mock_config):
    """Test pool metadata includes lending-specific data."""
    morpho = MorphoProtocol(mock_config)

    pools = await morpho.get_pools()
    first_pool = pools[0]

    # Check for lending-specific metadata
    assert "borrow_apy" in first_pool.metadata
    assert "utilization" in first_pool.metadata
    assert "collateral_factor" in first_pool.metadata
    assert "oracle_type" in first_pool.metadata


@pytest.mark.asyncio
async def test_get_pool_apy_existing_market(mock_config):
    """Test getting APY for an existing market."""
    morpho = MorphoProtocol(mock_config)

    # Get pools first to know valid pool ID
    pools = await morpho.get_pools()
    test_pool_id = pools[0].pool_id
    expected_apy = pools[0].apy

    # Get APY for that pool
    apy = await morpho.get_pool_apy(test_pool_id)

    assert apy == expected_apy
    assert apy > 0


@pytest.mark.asyncio
async def test_get_pool_apy_nonexistent_market(mock_config):
    """Test getting APY for non-existent market returns zero."""
    morpho = MorphoProtocol(mock_config)

    apy = await morpho.get_pool_apy("nonexistent-market")

    assert apy == Decimal("0")


@pytest.mark.asyncio
async def test_deposit_read_only_mode(mock_config):
    """Test deposit in read-only mode returns transaction data without executing."""
    morpho = MorphoProtocol(mock_config)

    result = await morpho.deposit(
        pool_id="morpho-usdc-market-1",
        token="USDC",
        amount=Decimal("1000")
    )

    # Should return transaction data as string
    assert isinstance(result, str)
    assert "morpho" in result.lower() or "0x2DC205F24BCb6B311E5cdf0745B0741648Aebd3d" in result


@pytest.mark.asyncio
async def test_withdraw_read_only_mode(mock_config):
    """Test withdraw in read-only mode returns transaction data without executing."""
    morpho = MorphoProtocol(mock_config)

    result = await morpho.withdraw(
        pool_id="morpho-usdc-market-1",
        token="USDC",
        amount=Decimal("500")
    )

    # Should return transaction data as string
    assert isinstance(result, str)
    assert "morpho" in result.lower() or "0x2DC205F24BCb6B311E5cdf0745B0741648Aebd3d" in result


@pytest.mark.asyncio
async def test_deposit_non_read_only_raises_error():
    """Test deposit with read_only=False raises NotImplementedError."""
    config = {
        "network": "base-sepolia",
        "use_mock_data": True,
        "read_only": False,  # Not read-only
    }
    morpho = MorphoProtocol(config)

    with pytest.raises(NotImplementedError, match="Sprint 3-4"):
        await morpho.deposit(
            pool_id="morpho-usdc-market-1",
            token="USDC",
            amount=Decimal("1000")
        )


@pytest.mark.asyncio
async def test_withdraw_non_read_only_raises_error():
    """Test withdraw with read_only=False raises NotImplementedError."""
    config = {
        "network": "base-sepolia",
        "use_mock_data": True,
        "read_only": False,  # Not read-only
    }
    morpho = MorphoProtocol(config)

    with pytest.raises(NotImplementedError, match="Sprint 3-4"):
        await morpho.withdraw(
            pool_id="morpho-usdc-market-1",
            token="USDC",
            amount=Decimal("500")
        )


@pytest.mark.asyncio
async def test_get_user_balance_mock_mode(mock_config):
    """Test getting user balance in mock mode returns zero."""
    morpho = MorphoProtocol(mock_config)

    balance = await morpho.get_user_balance(
        pool_id="morpho-usdc-market-1",
        user_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
    )

    assert balance == Decimal("0")


@pytest.mark.asyncio
async def test_estimate_gas_deposit(mock_config):
    """Test gas estimation for deposit operation."""
    morpho = MorphoProtocol(mock_config)

    gas = await morpho.estimate_gas("deposit", {"token": "USDC", "amount": "1000"})

    assert gas > 0
    assert gas < 300000  # Should be reasonable gas amount


@pytest.mark.asyncio
async def test_estimate_gas_withdraw(mock_config):
    """Test gas estimation for withdraw operation."""
    morpho = MorphoProtocol(mock_config)

    gas = await morpho.estimate_gas("withdraw", {"token": "USDC", "amount": "500"})

    assert gas > 0
    assert gas < 300000  # Should be reasonable gas amount


@pytest.mark.asyncio
async def test_estimate_gas_different_operations(mock_config):
    """Test different operations have different gas estimates."""
    morpho = MorphoProtocol(mock_config)

    deposit_gas = await morpho.estimate_gas("deposit", {})
    withdraw_gas = await morpho.estimate_gas("withdraw", {})
    borrow_gas = await morpho.estimate_gas("borrow", {})

    # Different operations should have different gas costs
    assert deposit_gas != borrow_gas
    assert withdraw_gas != borrow_gas


@pytest.mark.asyncio
async def test_pools_have_varied_apys(mock_config):
    """Test mock data has varied APYs for different markets."""
    morpho = MorphoProtocol(mock_config)

    pools = await morpho.get_pools()
    apys = [pool.apy for pool in pools]

    # Should have at least 2 different APYs
    unique_apys = set(apys)
    assert len(unique_apys) >= 2, "Should have varied APYs across markets"


@pytest.mark.asyncio
async def test_pools_have_realistic_tvls(mock_config):
    """Test mock TVLs are realistic for lending markets."""
    morpho = MorphoProtocol(mock_config)

    pools = await morpho.get_pools()

    for pool in pools:
        # Realistic lending market TVLs: $100k - $100M
        assert pool.tvl >= Decimal("100000"), f"TVL too low: ${pool.tvl}"
        assert pool.tvl <= Decimal("100000000"), f"TVL too high: ${pool.tvl}"


@pytest.mark.asyncio
async def test_repr_method(mock_config):
    """Test string representation of MorphoProtocol."""
    morpho = MorphoProtocol(mock_config)

    repr_str = repr(morpho)

    assert "MorphoProtocol" in repr_str
    assert "base-sepolia" in repr_str
    assert "read_only=True" in repr_str
    assert "mock_data=True" in repr_str


@pytest.mark.asyncio
async def test_mainnet_contract_addresses():
    """Test mainnet contract addresses are defined."""
    mainnet_contracts = MORPHO_CONTRACTS.get("base-mainnet", {})

    assert "morpho_blue" in mainnet_contracts
    assert "morpho_token" in mainnet_contracts
    assert mainnet_contracts["morpho_blue"] != ""
    assert mainnet_contracts["morpho_token"] != ""


@pytest.mark.asyncio
async def test_pools_metadata_has_risk_tier(mock_config):
    """Test pool metadata includes risk tier assessment."""
    morpho = MorphoProtocol(mock_config)

    pools = await morpho.get_pools()

    for pool in pools:
        assert "risk_tier" in pool.metadata
        assert pool.metadata["risk_tier"] in ["low", "medium", "high"]
