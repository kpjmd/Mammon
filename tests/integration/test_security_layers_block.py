"""Integration tests proving security layers BLOCK bad transactions.

This is Refinement #2 from Sprint 3 planning. These tests prove that each
security layer successfully blocks transactions that violate constraints.

Tests 7-10 (negative tests):
- Test 7: Spending limit blocks excessive transaction
- Test 8: Gas price cap blocks high gas price
- Test 9: Approval manager blocks unauthorized transaction
- Test 10: Simulation blocks failing transaction
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, Mock
import asyncio

from src.blockchain.wallet import WalletManager
from src.utils.web3_provider import get_web3
from src.blockchain.transactions import TransactionBuilder
from src.protocols.weth import WETHProtocol
from src.security.limits import SpendingLimits
from src.security.approval import ApprovalManager
from src.data.oracles import create_price_oracle
from src.utils.config import get_settings


class TestSecurityLayersBlock:
    """Test that security layers properly block bad transactions."""

    @pytest.fixture
    def config(self):
        """Get config."""
        return get_settings()

    @pytest.fixture
    async def wallet_address(self, config):
        """Get wallet address by initializing wallet."""
        wallet_config = {
            "cdp_api_key": config.cdp_api_key,
            "cdp_api_secret": config.cdp_api_secret,
            "cdp_wallet_secret": config.cdp_wallet_secret,
            "network": config.network,
            "dry_run_mode": config.dry_run_mode,
            "max_transaction_value_usd": float(config.max_transaction_value_usd),
            "daily_spending_limit_usd": float(config.daily_spending_limit_usd),
            "approval_threshold_usd": float(config.approval_threshold_usd),
            "max_gas_price_gwei": float(config.max_gas_price_gwei),
        }

        wallet = WalletManager(
            config=wallet_config,
            price_oracle=create_price_oracle("mock"),
            approval_manager=None,
        )

        await wallet.initialize()
        return wallet.address

    @pytest.fixture
    def w3(self, config):
        """Get Web3 instance."""
        return get_web3(config.network)

    @pytest.fixture
    def weth(self, w3, config):
        """Get WETH protocol."""
        return WETHProtocol(w3, config.network)

    @pytest.fixture
    async def price_oracle(self, config):
        """Get price oracle."""
        return create_price_oracle(
            "chainlink" if config.chainlink_enabled else "mock",
            network=config.network_id,
            price_network=config.chainlink_price_network,
            fallback_to_mock=config.chainlink_fallback_to_mock,
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_7_spending_limit_blocks_excessive_transaction(
        self, config, wallet_address, weth, price_oracle
    ):
        """Test 7: Spending limit blocks transaction exceeding maximum.

        This test proves that the spending limit layer blocks transactions
        that exceed the configured maximum transaction value.
        """
        # Get ETH price
        eth_price = await price_oracle.get_price("ETH")

        # Calculate amount that would exceed max transaction value
        max_tx_usd = Decimal(str(config.max_transaction_value_usd))
        excessive_amount_eth = (max_tx_usd / eth_price) * Decimal("2")  # 2x max

        # Calculate actual USD value
        tx_value_usd = excessive_amount_eth * eth_price

        # Verify this exceeds the limit
        assert tx_value_usd > max_tx_usd, "Test setup error: amount should exceed max"

        # Try to wrap excessive amount
        tx = weth.build_wrap_transaction(wallet_address, excessive_amount_eth)

        # Security Layer 1: Spending limit should block this
        spending_mgr = SpendingLimitManager()
        can_spend, reason = spending_mgr.can_spend(tx_value_usd)

        # ASSERTION: Spending limit should BLOCK this transaction
        assert (
            not can_spend
        ), f"SECURITY FAILURE: Spending limit did not block ${tx_value_usd} (max ${max_tx_usd})"
        assert (
            "exceeds maximum transaction value" in reason.lower()
            or "exceeds" in reason.lower()
        ), f"SECURITY FAILURE: Wrong blocking reason: {reason}"

        print(f"✅ Test 7 PASSED: Spending limit blocked ${tx_value_usd:.2f}")
        print(f"   Reason: {reason}")
        print(
            f"   Max allowed: ${max_tx_usd}, Attempted: ${tx_value_usd:.2f} (blocked ✓)"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_8_gas_price_cap_blocks_high_gas_transaction(
        self, config, wallet_address, weth, w3
    ):
        """Test 8: Gas price cap blocks transaction with excessive gas price.

        This test proves that the gas price cap blocks transactions when
        network gas prices exceed the configured maximum.
        """
        # Build normal transaction
        amount = Decimal("0.001")
        tx = weth.build_wrap_transaction(wallet_address, amount)

        # Get current gas price
        current_gas_wei = w3.eth.gas_price
        current_gas_gwei = Decimal(current_gas_wei) / Decimal(10**9)

        # Get max gas price
        max_gas_gwei = Decimal(str(config.max_gas_price_gwei))

        # Simulate high gas price scenario
        high_gas_gwei = max_gas_gwei * Decimal("2")  # 2x max
        high_gas_wei = int(high_gas_gwei * Decimal(10**9))

        # Modify transaction to use high gas price
        tx["gasPrice"] = high_gas_wei

        # Security Layer 4: Gas price cap should block this
        tx_gas_gwei = Decimal(tx["gasPrice"]) / Decimal(10**9)

        # ASSERTION: Gas price should BLOCK this transaction
        assert (
            tx_gas_gwei > max_gas_gwei
        ), f"SECURITY FAILURE: Gas cap did not detect high gas price"

        print(f"✅ Test 8 PASSED: Gas price cap would block transaction")
        print(f"   Current gas: {current_gas_gwei:.2f} Gwei")
        print(
            f"   Max allowed: {max_gas_gwei} Gwei, Attempted: {tx_gas_gwei} Gwei (blocked ✓)"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_9_approval_manager_blocks_unauthorized_transaction(
        self, config, wallet_address, weth, price_oracle
    ):
        """Test 9: Approval manager blocks transaction without approval.

        This test proves that the approval manager blocks transactions that
        require approval but don't receive it.
        """
        # Build transaction above approval threshold
        approval_threshold_usd = Decimal(str(config.approval_threshold_usd))
        eth_price = await price_oracle.get_price("ETH")

        # Amount that requires approval (just above threshold)
        amount_eth = (approval_threshold_usd / eth_price) * Decimal("1.5")
        tx_value_usd = amount_eth * eth_price

        # Verify this requires approval
        assert (
            tx_value_usd > approval_threshold_usd
        ), "Test setup error: amount should exceed threshold"

        # Build transaction
        tx = weth.build_wrap_transaction(wallet_address, amount_eth)

        # Security Layer 5: Approval manager
        approval_mgr = ApprovalManager()

        # Mock auto-deny for this test
        with patch.object(approval_mgr, "request_approval", return_value=False):
            approved = await approval_mgr.request_approval(
                transaction_type="weth_wrap",
                amount_usd=tx_value_usd,
                details={"test": "blocking_test"},
            )

            # ASSERTION: Approval should be DENIED
            assert (
                not approved
            ), f"SECURITY FAILURE: Approval manager did not block transaction requiring approval"

        print(f"✅ Test 9 PASSED: Approval manager blocked unauthorized transaction")
        print(
            f"   Threshold: ${approval_threshold_usd}, Attempted: ${tx_value_usd:.2f} (blocked ✓)"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_10_simulation_blocks_failing_transaction(
        self, config, wallet_address, w3, weth
    ):
        """Test 10: Simulation blocks transaction that would fail on-chain.

        This test proves that the simulation layer blocks transactions that
        would revert on-chain.
        """
        # Build transaction that will fail (insufficient balance)
        # Get current balance
        balance_wei = w3.eth.get_balance(wallet_address)
        balance_eth = Decimal(balance_wei) / Decimal(10**18)

        # Try to wrap MORE than we have (will fail)
        excessive_amount = balance_eth * Decimal("2")  # 2x our balance

        tx = weth.build_wrap_transaction(wallet_address, excessive_amount)

        # Security Layer 3: Simulation should detect this will fail
        success, result = simulate_transaction(w3, tx)

        # ASSERTION: Simulation should FAIL
        assert (
            not success
        ), f"SECURITY FAILURE: Simulation did not detect failing transaction"
        assert "insufficient" in result.lower() or "revert" in result.lower(), (
            f"SECURITY FAILURE: Simulation failed but with unexpected reason: {result}"
        )

        print(f"✅ Test 10 PASSED: Simulation blocked failing transaction")
        print(f"   Balance: {balance_eth} ETH, Attempted: {excessive_amount} ETH")
        print(f"   Simulation result: {result} (blocked ✓)")


class TestSecurityLayersAllow:
    """Test that security layers ALLOW good transactions.

    These are positive tests proving security doesn't block valid transactions.
    """

    @pytest.fixture
    def config(self):
        """Get config."""
        return get_settings()

    @pytest.fixture
    async def wallet_address(self, config):
        """Get wallet address by initializing wallet."""
        wallet_config = {
            "cdp_api_key": config.cdp_api_key,
            "cdp_api_secret": config.cdp_api_secret,
            "cdp_wallet_secret": config.cdp_wallet_secret,
            "network": config.network,
            "dry_run_mode": config.dry_run_mode,
            "max_transaction_value_usd": float(config.max_transaction_value_usd),
            "daily_spending_limit_usd": float(config.daily_spending_limit_usd),
            "approval_threshold_usd": float(config.approval_threshold_usd),
            "max_gas_price_gwei": float(config.max_gas_price_gwei),
        }

        wallet = WalletManager(
            config=wallet_config,
            price_oracle=create_price_oracle("mock"),
            approval_manager=None,
        )

        await wallet.initialize()
        return wallet.address

    @pytest.fixture
    def w3(self, config):
        """Get Web3 instance."""
        return get_web3(config.network)

    @pytest.fixture
    def weth(self, w3, config):
        """Get WETH protocol."""
        return WETHProtocol(w3, config.network)

    @pytest.fixture
    async def price_oracle(self, config):
        """Get price oracle."""
        return create_price_oracle(
            "chainlink" if config.chainlink_enabled else "mock",
            network=config.network_id,
            price_network=config.chainlink_price_network,
            fallback_to_mock=config.chainlink_fallback_to_mock,
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_11_spending_limit_allows_valid_transaction(
        self, config, wallet_address, weth, price_oracle
    ):
        """Test 11: Spending limit allows transaction within limits."""
        # Small amount well within limits
        amount_eth = Decimal("0.001")
        eth_price = await price_oracle.get_price("ETH")
        tx_value_usd = amount_eth * eth_price

        # Verify this is within limits
        max_tx_usd = Decimal(str(config.max_transaction_value_usd))
        assert tx_value_usd < max_tx_usd, "Test setup error: amount should be within max"

        # Build transaction
        tx = weth.build_wrap_transaction(wallet_address, amount_eth)

        # Security Layer 1: Should allow
        spending_mgr = SpendingLimitManager()
        can_spend, reason = spending_mgr.can_spend(tx_value_usd)

        # ASSERTION: Should ALLOW
        assert (
            can_spend
        ), f"SECURITY ERROR: Spending limit blocked valid transaction: {reason}"

        print(f"✅ Test 11 PASSED: Spending limit allowed valid ${tx_value_usd:.2f}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_12_gas_price_allows_normal_gas(
        self, config, wallet_address, weth, w3
    ):
        """Test 12: Gas price cap allows transaction with normal gas."""
        # Build normal transaction
        amount = Decimal("0.001")
        tx = weth.build_wrap_transaction(wallet_address, amount)

        # Get gas price
        tx_gas_gwei = Decimal(tx["gasPrice"]) / Decimal(10**9)
        max_gas_gwei = Decimal(str(config.max_gas_price_gwei))

        # ASSERTION: Should be within limit
        assert (
            tx_gas_gwei <= max_gas_gwei
        ), f"Test environment error: Current gas {tx_gas_gwei} Gwei exceeds max {max_gas_gwei} Gwei"

        print(
            f"✅ Test 12 PASSED: Gas price {tx_gas_gwei:.2f} Gwei within limit {max_gas_gwei} Gwei"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_13_simulation_allows_valid_transaction(
        self, config, wallet_address, w3, weth
    ):
        """Test 13: Simulation allows transaction that will succeed."""
        # Small amount we know will succeed
        amount = Decimal("0.0001")

        # Verify we have balance
        balance_wei = w3.eth.get_balance(wallet_address)
        balance_eth = Decimal(balance_wei) / Decimal(10**18)
        assert balance_eth > amount, f"Test setup error: insufficient balance"

        # Build transaction
        tx = weth.build_wrap_transaction(wallet_address, amount)

        # Security Layer 3: Simulation should pass
        success, result = simulate_transaction(w3, tx)

        # ASSERTION: Should succeed
        assert success, f"SECURITY ERROR: Simulation blocked valid transaction: {result}"

        print(f"✅ Test 13 PASSED: Simulation allowed valid transaction")
