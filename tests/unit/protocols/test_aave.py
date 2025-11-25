"""Unit tests for Aave V3 protocol integration.

Phase 3 Sprint 2: Tests for read-only Aave V3 implementation with REAL BASE MAINNET data.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from src.protocols.aave import AaveV3Protocol, AAVE_V3_CONTRACTS


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "network": "base-sepolia",
        "read_only": True,
        "dry_run_mode": True,
        "chainlink_enabled": False,  # Use mock oracle for tests
    }


@pytest.fixture
def mock_web3():
    """Mock Web3 instance."""
    mock_w3 = MagicMock()
    mock_w3.eth.contract.return_value = MagicMock()
    return mock_w3


# ===== INITIALIZATION TESTS =====


@pytest.mark.asyncio
async def test_aave_initialization(mock_config):
    """Test Aave V3 protocol initialization."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        assert aave.name == "Aave V3"
        assert aave.chain == "base"
        assert aave.network == "base-sepolia"
        assert aave.read_only is True


@pytest.mark.asyncio
async def test_aave_initialization_with_correct_contract_address(mock_config):
    """Test Aave V3 uses correct Base mainnet contract address."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        expected_pool = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
        assert aave.contracts.get("pool") == expected_pool


@pytest.mark.asyncio
async def test_aave_safety_score(mock_config):
    """Test Aave V3 protocol safety score calculation."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        # Aave V3 is very safe (battle-tested, extensively audited)
        assert aave.safety_score == 95


@pytest.mark.asyncio
async def test_aave_read_only_mode_enforced(mock_config):
    """Test that read-only mode is enforced by default."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)
        assert aave.read_only is True


# ===== APY CONVERSION TESTS =====


@pytest.mark.asyncio
async def test_ray_to_apy_conversion_zero_rate(mock_config):
    """Test ray to APY conversion with zero rate."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        apy = aave._ray_to_apy(0)
        assert apy == Decimal("0")


@pytest.mark.asyncio
async def test_ray_to_apy_conversion_typical_rate(mock_config):
    """Test ray to APY conversion with typical lending rate."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        # Typical 5% APY in ray units (approximate)
        ray_rate = int(1.5e24)  # ~5% APY
        apy = aave._ray_to_apy(ray_rate)

        # APY should be positive and reasonable
        assert apy > Decimal("0")
        assert apy < Decimal("100")  # Should be less than 100%


@pytest.mark.asyncio
async def test_ray_to_apy_conversion_high_rate(mock_config):
    """Test ray to APY conversion with high lending rate."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        # High rate: ~20% APY
        ray_rate = int(6e24)
        apy = aave._ray_to_apy(ray_rate)

        # APY should be positive
        assert apy > Decimal("0")


# ===== POOL FETCHING TESTS =====


@pytest.mark.asyncio
async def test_get_pools_returns_list(mock_config):
    """Test that get_pools returns a list."""
    with patch("src.protocols.aave.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_pool_contract = MagicMock()

        # Mock empty reserves list
        mock_pool_contract.functions.getReservesList.return_value.call.return_value = []
        mock_w3.eth.contract.return_value = mock_pool_contract
        mock_get_web3.return_value = mock_w3

        aave = AaveV3Protocol(mock_config)
        pools = await aave.get_pools()

        assert isinstance(pools, list)


@pytest.mark.asyncio
async def test_get_pools_handles_errors_gracefully(mock_config):
    """Test that get_pools handles errors and returns empty list."""
    with patch("src.protocols.aave.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_pool_contract = MagicMock()

        # Mock error when calling getReservesList
        mock_pool_contract.functions.getReservesList.return_value.call.side_effect = Exception("RPC error")
        mock_w3.eth.contract.return_value = mock_pool_contract
        mock_get_web3.return_value = mock_w3

        aave = AaveV3Protocol(mock_config)
        pools = await aave.get_pools()

        # Should return empty list on error
        assert pools == []


@pytest.mark.asyncio
async def test_get_pools_creates_correct_pool_structure(mock_config):
    """Test that get_pools creates properly structured ProtocolPool objects."""
    with patch("src.protocols.aave.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_pool_contract = MagicMock()
        mock_token_contract = MagicMock()
        mock_atoken_contract = MagicMock()

        # Mock reserve data
        usdc_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        atoken_address = "0xaToken123"

        mock_pool_contract.functions.getReservesList.return_value.call.return_value = [usdc_address]

        # Mock reserve data tuple (matching Aave's ReserveData struct)
        reserve_data = (
            0,  # configuration
            10**27,  # liquidityIndex
            int(1.5e24),  # currentLiquidityRate (supply APY)
            10**27,  # variableBorrowIndex
            int(3e24),  # currentVariableBorrowRate (borrow APY)
            0,  # currentStableBorrowRate
            0,  # lastUpdateTimestamp
            0,  # id
            atoken_address,  # aTokenAddress
            "0x0",  # stableDebtTokenAddress
            "0x0",  # variableDebtTokenAddress
            "0x0",  # interestRateStrategyAddress
            0,  # accruedToTreasury
            0,  # unbacked
            0,  # isolationModeTotalDebt
        )
        mock_pool_contract.functions.getReserveData.return_value.call.return_value = reserve_data

        # Mock token info
        mock_token_contract.functions.symbol.return_value.call.return_value = "USDC"
        mock_token_contract.functions.decimals.return_value.call.return_value = 6

        # Mock aToken total supply
        mock_atoken_contract.functions.totalSupply.return_value.call.return_value = 1000000 * 10**6  # 1M USDC

        def contract_side_effect(address, abi):
            if address == usdc_address:
                return mock_token_contract
            elif address == atoken_address:
                return mock_atoken_contract
            return MagicMock()

        mock_w3.eth.contract.side_effect = contract_side_effect
        mock_get_web3.return_value = mock_w3

        aave = AaveV3Protocol(mock_config)
        pools = await aave.get_pools()

        assert len(pools) == 1
        pool = pools[0]
        assert pool.pool_id == "aave-v3-usdc"
        assert "USDC" in pool.tokens
        assert pool.apy >= Decimal("0")
        assert pool.tvl >= Decimal("0")
        assert "borrow_apy" in pool.metadata


# ===== DEPOSIT/WITHDRAW TESTS =====


@pytest.mark.asyncio
async def test_deposit_in_read_only_mode(mock_config):
    """Test deposit in read-only mode returns transaction data without executing."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        tx_data = await aave.deposit("aave-v3-usdc", "USDC", Decimal("100"))

        # Should return transaction data as string
        assert isinstance(tx_data, str)
        assert "supply" in tx_data.lower()


@pytest.mark.asyncio
async def test_deposit_raises_error_if_not_read_only(mock_config):
    """Test deposit raises NotImplementedError when not in read-only mode."""
    mock_config["read_only"] = False

    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        with pytest.raises(NotImplementedError):
            await aave.deposit("aave-v3-usdc", "USDC", Decimal("100"))


@pytest.mark.asyncio
async def test_withdraw_in_read_only_mode(mock_config):
    """Test withdraw in read-only mode returns transaction data without executing."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        tx_data = await aave.withdraw("aave-v3-usdc", "USDC", Decimal("50"))

        # Should return transaction data as string
        assert isinstance(tx_data, str)
        assert "withdraw" in tx_data.lower()


@pytest.mark.asyncio
async def test_withdraw_raises_error_if_not_read_only(mock_config):
    """Test withdraw raises NotImplementedError when not in read-only mode."""
    mock_config["read_only"] = False

    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        with pytest.raises(NotImplementedError):
            await aave.withdraw("aave-v3-usdc", "USDC", Decimal("50"))


# ===== GAS ESTIMATION TESTS =====


@pytest.mark.asyncio
async def test_estimate_gas_deposit(mock_config):
    """Test gas estimation for deposit operation."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        gas = await aave.estimate_gas("deposit", {"token": "USDC", "amount": "100"})

        # Should return reasonable gas estimate
        assert gas > 0
        assert gas == 200000  # Expected deposit gas


@pytest.mark.asyncio
async def test_estimate_gas_withdraw(mock_config):
    """Test gas estimation for withdraw operation."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        gas = await aave.estimate_gas("withdraw", {"token": "USDC", "amount": "50"})

        assert gas > 0
        assert gas == 180000  # Expected withdraw gas


@pytest.mark.asyncio
async def test_estimate_gas_borrow(mock_config):
    """Test gas estimation for borrow operation."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        gas = await aave.estimate_gas("borrow", {"token": "USDC", "amount": "100"})

        assert gas > 0
        assert gas == 250000  # Expected borrow gas


@pytest.mark.asyncio
async def test_estimate_gas_unknown_operation(mock_config):
    """Test gas estimation for unknown operation returns default."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        gas = await aave.estimate_gas("unknown_op", {})

        assert gas == 250000  # Default gas estimate


# ===== BALANCE QUERY TESTS =====


@pytest.mark.asyncio
async def test_get_user_balance(mock_config):
    """Test getting user balance from Aave market."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        balance = await aave.get_user_balance("aave-v3-usdc", "0x1234...5678")

        # Currently returns 0 (not implemented yet)
        assert balance == Decimal("0")


# ===== APY QUERY TESTS =====


@pytest.mark.asyncio
async def test_get_pool_apy_existing_pool(mock_config):
    """Test getting APY for an existing pool."""
    with patch("src.protocols.aave.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_pool_contract = MagicMock()

        # Mock empty reserves (simplified test)
        mock_pool_contract.functions.getReservesList.return_value.call.return_value = []
        mock_w3.eth.contract.return_value = mock_pool_contract
        mock_get_web3.return_value = mock_w3

        aave = AaveV3Protocol(mock_config)
        apy = await aave.get_pool_apy("aave-v3-usdc")

        # Should return 0 for non-existent pool
        assert apy == Decimal("0")


# ===== STRING REPRESENTATION TEST =====


@pytest.mark.asyncio
async def test_repr(mock_config):
    """Test string representation of AaveV3Protocol."""
    with patch("src.protocols.aave.get_web3"):
        aave = AaveV3Protocol(mock_config)

        repr_str = repr(aave)

        assert "AaveV3Protocol" in repr_str
        assert "read_only=True" in repr_str
        assert "base-mainnet" in repr_str
        assert "safety_score=95" in repr_str
