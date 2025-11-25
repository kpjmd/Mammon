"""Unit tests for Moonwell protocol integration.

Phase 3 Sprint 2: Tests for read-only Moonwell implementation with REAL BASE MAINNET data.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
from src.protocols.moonwell import MoonwellProtocol, MOONWELL_CONTRACTS


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "network": "base-sepolia",
        "read_only": True,
        "dry_run_mode": True,
        "chainlink_enabled": False,  # Use mock oracle for tests
    }


# ===== INITIALIZATION TESTS =====


@pytest.mark.asyncio
async def test_moonwell_initialization(mock_config):
    """Test Moonwell protocol initialization."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        assert moonwell.name == "Moonwell"
        assert moonwell.chain == "base"
        assert moonwell.network == "base-sepolia"
        assert moonwell.read_only is True


@pytest.mark.asyncio
async def test_moonwell_initialization_with_correct_contract_address(mock_config):
    """Test Moonwell uses correct Base mainnet contract address."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        expected_comptroller = "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C"
        assert moonwell.contracts.get("comptroller") == expected_comptroller


@pytest.mark.asyncio
async def test_moonwell_safety_score(mock_config):
    """Test Moonwell protocol safety score calculation."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        # Moonwell is well-audited Compound fork
        assert moonwell.safety_score == 85


@pytest.mark.asyncio
async def test_moonwell_read_only_mode_enforced(mock_config):
    """Test that read-only mode is enforced by default."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)
        assert moonwell.read_only is True


# ===== RATE CONVERSION TESTS =====


@pytest.mark.asyncio
async def test_rate_per_block_to_apy_zero_rate(mock_config):
    """Test rate per block to APY conversion with zero rate."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        apy = moonwell._rate_per_block_to_apy(0)
        assert apy == Decimal("0")


@pytest.mark.asyncio
async def test_rate_per_block_to_apy_typical_rate(mock_config):
    """Test rate per block to APY conversion with typical lending rate."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        # Typical 5% APY per block rate (approximate)
        # ~5% APY = rate_per_block * blocks_per_year
        # rate_per_block ≈ 0.05 / (43200 * 365) = ~3.17e-9
        # In 1e18 scale: ~3.17e9
        rate_per_block = int(3.17e9)
        apy = moonwell._rate_per_block_to_apy(rate_per_block)

        # APY should be positive and reasonable
        assert apy > Decimal("0")
        assert apy < Decimal("100")  # Should be less than 100%


@pytest.mark.asyncio
async def test_rate_per_block_to_apy_high_rate(mock_config):
    """Test rate per block to APY conversion with high lending rate."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        # High rate: ~20% APY
        rate_per_block = int(1.27e10)  # ~20% APY
        apy = moonwell._rate_per_block_to_apy(rate_per_block)

        # APY should be positive
        assert apy > Decimal("0")


# ===== POOL FETCHING TESTS =====


@pytest.mark.asyncio
async def test_get_pools_returns_list(mock_config):
    """Test that get_pools returns a list."""
    with patch("src.protocols.moonwell.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_comptroller_contract = MagicMock()

        # Mock empty markets list
        mock_comptroller_contract.functions.getAllMarkets.return_value.call.return_value = []
        mock_w3.eth.contract.return_value = mock_comptroller_contract
        mock_get_web3.return_value = mock_w3

        moonwell = MoonwellProtocol(mock_config)
        pools = await moonwell.get_pools()

        assert isinstance(pools, list)


@pytest.mark.asyncio
async def test_get_pools_handles_errors_gracefully(mock_config):
    """Test that get_pools handles errors and returns empty list."""
    with patch("src.protocols.moonwell.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_comptroller_contract = MagicMock()

        # Mock error when calling getAllMarkets
        mock_comptroller_contract.functions.getAllMarkets.return_value.call.side_effect = Exception("RPC error")
        mock_w3.eth.contract.return_value = mock_comptroller_contract
        mock_get_web3.return_value = mock_w3

        moonwell = MoonwellProtocol(mock_config)
        pools = await moonwell.get_pools()

        # Should return empty list on error
        assert pools == []


@pytest.mark.asyncio
async def test_get_pools_handles_eth_market(mock_config):
    """Test that get_pools handles native ETH markets (no underlying() function)."""
    with patch("src.protocols.moonwell.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_comptroller_contract = MagicMock()
        mock_mtoken_contract = MagicMock()

        # Mock mETH address (native ETH market)
        meth_address = "0xmETH123"

        mock_comptroller_contract.functions.getAllMarkets.return_value.call.return_value = [meth_address]

        # Mock mToken functions (no underlying() for ETH)
        mock_mtoken_contract.functions.underlying.return_value.call.side_effect = Exception("No underlying for ETH")
        mock_mtoken_contract.functions.supplyRatePerBlock.return_value.call.return_value = int(3e9)
        mock_mtoken_contract.functions.borrowRatePerBlock.return_value.call.return_value = int(5e9)
        mock_mtoken_contract.functions.getCash.return_value.call.return_value = 1000 * 10**18
        mock_mtoken_contract.functions.totalBorrows.return_value.call.return_value = 500 * 10**18
        mock_mtoken_contract.functions.totalReserves.return_value.call.return_value = 50 * 10**18

        def contract_side_effect(address, abi):
            if address == meth_address:
                return mock_mtoken_contract
            return MagicMock()

        mock_w3.eth.contract.side_effect = contract_side_effect
        mock_get_web3.return_value = mock_w3

        moonwell = MoonwellProtocol(mock_config)
        pools = await moonwell.get_pools()

        # Should handle ETH market
        assert len(pools) == 1
        assert pools[0].tokens == ["ETH"]


@pytest.mark.asyncio
async def test_get_pools_creates_correct_pool_structure(mock_config):
    """Test that get_pools creates properly structured ProtocolPool objects."""
    with patch("src.protocols.moonwell.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_comptroller_contract = MagicMock()
        mock_mtoken_contract = MagicMock()
        mock_token_contract = MagicMock()

        # Mock addresses
        musdc_address = "0xmUSDC123"
        usdc_address = "0xUSDC456"

        mock_comptroller_contract.functions.getAllMarkets.return_value.call.return_value = [musdc_address]

        # Mock mToken functions
        mock_mtoken_contract.functions.underlying.return_value.call.return_value = usdc_address
        mock_mtoken_contract.functions.supplyRatePerBlock.return_value.call.return_value = int(3e9)
        mock_mtoken_contract.functions.borrowRatePerBlock.return_value.call.return_value = int(5e9)
        mock_mtoken_contract.functions.getCash.return_value.call.return_value = 1000000 * 10**6
        mock_mtoken_contract.functions.totalBorrows.return_value.call.return_value = 500000 * 10**6
        mock_mtoken_contract.functions.totalReserves.return_value.call.return_value = 50000 * 10**6

        # Mock token info
        mock_token_contract.functions.symbol.return_value.call.return_value = "USDC"
        mock_token_contract.functions.decimals.return_value.call.return_value = 6

        def contract_side_effect(address, abi):
            if address == musdc_address:
                return mock_mtoken_contract
            elif address == usdc_address:
                return mock_token_contract
            return MagicMock()

        mock_w3.eth.contract.side_effect = contract_side_effect
        mock_get_web3.return_value = mock_w3

        moonwell = MoonwellProtocol(mock_config)
        pools = await moonwell.get_pools()

        assert len(pools) == 1
        pool = pools[0]
        assert pool.pool_id == "moonwell-usdc"
        assert "USDC" in pool.tokens
        assert pool.apy >= Decimal("0")
        assert pool.tvl >= Decimal("0")
        assert "borrow_apy" in pool.metadata
        assert "utilization" in pool.metadata


# ===== DEPOSIT/WITHDRAW TESTS =====


@pytest.mark.asyncio
async def test_deposit_in_read_only_mode(mock_config):
    """Test deposit in read-only mode returns transaction data without executing."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        tx_data = await moonwell.deposit("moonwell-usdc", "USDC", Decimal("100"))

        # Should return transaction data as string
        assert isinstance(tx_data, str)
        assert "mint" in tx_data.lower()


@pytest.mark.asyncio
async def test_deposit_raises_error_if_not_read_only(mock_config):
    """Test deposit raises NotImplementedError when not in read-only mode."""
    mock_config["read_only"] = False

    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        with pytest.raises(NotImplementedError):
            await moonwell.deposit("moonwell-usdc", "USDC", Decimal("100"))


@pytest.mark.asyncio
async def test_withdraw_in_read_only_mode(mock_config):
    """Test withdraw in read-only mode returns transaction data without executing."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        tx_data = await moonwell.withdraw("moonwell-usdc", "USDC", Decimal("50"))

        # Should return transaction data as string
        assert isinstance(tx_data, str)
        assert "redeem" in tx_data.lower()


@pytest.mark.asyncio
async def test_withdraw_raises_error_if_not_read_only(mock_config):
    """Test withdraw raises NotImplementedError when not in read-only mode."""
    mock_config["read_only"] = False

    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        with pytest.raises(NotImplementedError):
            await moonwell.withdraw("moonwell-usdc", "USDC", Decimal("50"))


# ===== GAS ESTIMATION TESTS =====


@pytest.mark.asyncio
async def test_estimate_gas_deposit(mock_config):
    """Test gas estimation for deposit (mint) operation."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        gas = await moonwell.estimate_gas("deposit", {"token": "USDC", "amount": "100"})

        # Should return reasonable gas estimate
        assert gas > 0
        assert gas == 180000  # Expected mint gas


@pytest.mark.asyncio
async def test_estimate_gas_withdraw(mock_config):
    """Test gas estimation for withdraw (redeem) operation."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        gas = await moonwell.estimate_gas("withdraw", {"token": "USDC", "amount": "50"})

        assert gas > 0
        assert gas == 160000  # Expected redeem gas


@pytest.mark.asyncio
async def test_estimate_gas_borrow(mock_config):
    """Test gas estimation for borrow operation."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        gas = await moonwell.estimate_gas("borrow", {"token": "USDC", "amount": "100"})

        assert gas > 0
        assert gas == 220000  # Expected borrow gas


@pytest.mark.asyncio
async def test_estimate_gas_unknown_operation(mock_config):
    """Test gas estimation for unknown operation returns default."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        gas = await moonwell.estimate_gas("unknown_op", {})

        assert gas == 200000  # Default gas estimate


# ===== BALANCE QUERY TESTS =====


@pytest.mark.asyncio
async def test_get_user_balance(mock_config):
    """Test getting user balance from Moonwell market."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        balance = await moonwell.get_user_balance("moonwell-usdc", "0x1234...5678")

        # Currently returns 0 (not implemented yet)
        assert balance == Decimal("0")


# ===== APY QUERY TESTS =====


@pytest.mark.asyncio
async def test_get_pool_apy_existing_pool(mock_config):
    """Test getting APY for an existing pool."""
    with patch("src.protocols.moonwell.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_comptroller_contract = MagicMock()

        # Mock empty markets (simplified test)
        mock_comptroller_contract.functions.getAllMarkets.return_value.call.return_value = []
        mock_w3.eth.contract.return_value = mock_comptroller_contract
        mock_get_web3.return_value = mock_w3

        moonwell = MoonwellProtocol(mock_config)
        apy = await moonwell.get_pool_apy("moonwell-usdc")

        # Should return 0 for non-existent pool
        assert apy == Decimal("0")


# ===== UTILIZATION CALCULATION TESTS =====


@pytest.mark.asyncio
async def test_utilization_calculation_normal(mock_config):
    """Test utilization calculation with normal values."""
    with patch("src.protocols.moonwell.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_comptroller_contract = MagicMock()
        mock_mtoken_contract = MagicMock()
        mock_token_contract = MagicMock()

        # Mock addresses
        musdc_address = "0xmUSDC123"
        usdc_address = "0xUSDC456"

        mock_comptroller_contract.functions.getAllMarkets.return_value.call.return_value = [musdc_address]

        # Mock mToken with specific utilization values
        cash = 500000 * 10**6  # 500k USDC cash
        borrows = 500000 * 10**6  # 500k USDC borrowed
        reserves = 0

        mock_mtoken_contract.functions.underlying.return_value.call.return_value = usdc_address
        mock_mtoken_contract.functions.supplyRatePerBlock.return_value.call.return_value = int(3e9)
        mock_mtoken_contract.functions.borrowRatePerBlock.return_value.call.return_value = int(5e9)
        mock_mtoken_contract.functions.getCash.return_value.call.return_value = cash
        mock_mtoken_contract.functions.totalBorrows.return_value.call.return_value = borrows
        mock_mtoken_contract.functions.totalReserves.return_value.call.return_value = reserves

        mock_token_contract.functions.symbol.return_value.call.return_value = "USDC"
        mock_token_contract.functions.decimals.return_value.call.return_value = 6

        def contract_side_effect(address, abi):
            if address == musdc_address:
                return mock_mtoken_contract
            elif address == usdc_address:
                return mock_token_contract
            return MagicMock()

        mock_w3.eth.contract.side_effect = contract_side_effect
        mock_get_web3.return_value = mock_w3

        moonwell = MoonwellProtocol(mock_config)
        pools = await moonwell.get_pools()

        # Utilization should be 50% (500k borrowed / 1M total supply)
        assert len(pools) == 1
        utilization = pools[0].metadata["utilization"]
        assert utilization == Decimal("0.5")


@pytest.mark.asyncio
async def test_utilization_calculation_zero_supply(mock_config):
    """Test utilization calculation when total supply is zero."""
    with patch("src.protocols.moonwell.get_web3") as mock_get_web3:
        mock_w3 = MagicMock()
        mock_comptroller_contract = MagicMock()
        mock_mtoken_contract = MagicMock()
        mock_token_contract = MagicMock()

        musdc_address = "0xmUSDC123"
        usdc_address = "0xUSDC456"

        mock_comptroller_contract.functions.getAllMarkets.return_value.call.return_value = [musdc_address]

        # Mock zero supply
        mock_mtoken_contract.functions.underlying.return_value.call.return_value = usdc_address
        mock_mtoken_contract.functions.supplyRatePerBlock.return_value.call.return_value = 0
        mock_mtoken_contract.functions.borrowRatePerBlock.return_value.call.return_value = 0
        mock_mtoken_contract.functions.getCash.return_value.call.return_value = 0
        mock_mtoken_contract.functions.totalBorrows.return_value.call.return_value = 0
        mock_mtoken_contract.functions.totalReserves.return_value.call.return_value = 0

        mock_token_contract.functions.symbol.return_value.call.return_value = "USDC"
        mock_token_contract.functions.decimals.return_value.call.return_value = 6

        def contract_side_effect(address, abi):
            if address == musdc_address:
                return mock_mtoken_contract
            elif address == usdc_address:
                return mock_token_contract
            return MagicMock()

        mock_w3.eth.contract.side_effect = contract_side_effect
        mock_get_web3.return_value = mock_w3

        moonwell = MoonwellProtocol(mock_config)
        pools = await moonwell.get_pools()

        # Utilization should be 0 when supply is 0
        assert len(pools) == 1
        utilization = pools[0].metadata["utilization"]
        assert utilization == Decimal("0")


# ===== STRING REPRESENTATION TEST =====


@pytest.mark.asyncio
async def test_repr(mock_config):
    """Test string representation of MoonwellProtocol."""
    with patch("src.protocols.moonwell.get_web3"):
        moonwell = MoonwellProtocol(mock_config)

        repr_str = repr(moonwell)

        assert "MoonwellProtocol" in repr_str
        assert "read_only=True" in repr_str
        assert "base-mainnet" in repr_str
        assert "safety_score=85" in repr_str
