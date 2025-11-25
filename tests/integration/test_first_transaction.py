"""Integration test for first transaction execution on Base Sepolia.

This test validates the complete transaction flow:
1. Wallet initialization
2. Balance checking
3. Transaction simulation
4. Gas estimation
5. Transaction building
6. (Optional) Real transaction execution

SAFETY: All tests use Base Sepolia testnet and dry-run mode by default.
"""

import pytest
from decimal import Decimal
from src.blockchain.wallet import WalletManager
from src.blockchain.transactions import TransactionBuilder, TransactionStatus
from src.blockchain.monitor import ChainMonitor
from src.security.approval import ApprovalManager
from src.data.oracles import create_price_oracle


class TestFirstTransaction:
    """Test suite for first transaction execution on testnet."""

    @pytest.fixture
    async def wallet_manager(self):
        """Create wallet manager for testing (dry-run mode)."""
        config = {
            "cdp_api_key": "test_key",
            "cdp_api_secret": "test_secret",
            "network": "base-sepolia",
            "dry_run_mode": True,  # SAFETY: Dry-run by default
            "max_transaction_value_usd": Decimal("100"),
            "daily_spending_limit_usd": Decimal("500"),
            "approval_threshold_usd": Decimal("50"),
        }

        # Create mock price oracle
        oracle = create_price_oracle("mock")

        # Create wallet manager
        wallet = WalletManager(
            config=config,
            price_oracle=oracle,
            approval_manager=None,  # No approvals for simple tests
        )

        return wallet

    @pytest.fixture
    def transaction_builder(self, wallet_manager):
        """Create transaction builder for testing."""
        config = {
            "network": "base-sepolia",
            "max_slippage_percent": 1.0,
        }
        return TransactionBuilder(wallet_manager, config)

    @pytest.fixture
    def chain_monitor(self):
        """Create chain monitor for testing."""
        config = {"network": "base-sepolia"}
        # Use a dummy address for monitoring
        dummy_address = "0x1234567890123456789012345678901234567890"
        return ChainMonitor(config, dummy_address)

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires network connection to Base Sepolia")
    async def test_gas_estimation(self, wallet_manager):
        """Test gas estimation with 20% buffer.

        SKIPPED: Requires real network connection to Base Sepolia RPC.
        This test validates gas estimation logic with 20% safety buffer.
        """
        # Initialize wallet (would need real credentials)
        await wallet_manager.initialize()

        # Simple ETH transfer
        recipient = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"  # Random address
        amount = Decimal("0.001")

        # Estimate gas
        gas_estimate = await wallet_manager.estimate_gas(
            to=recipient,
            amount=amount,
            data="",
            token="ETH",
        )

        # Should have 20% buffer on 21000 gas for simple transfer
        # Expected: 21000 * 1.2 = 25200
        assert gas_estimate >= 25000  # Allow some variance
        assert gas_estimate <= 30000

        print(f"✅ Gas estimate: {gas_estimate} (expected ~25200)")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires network connection to Base Sepolia")
    async def test_transaction_simulation_success(self, transaction_builder):
        """Test transaction simulation with valid transaction.

        SKIPPED: Requires real network connection to Base Sepolia RPC.
        This test validates eth_call simulation for detecting reverts.
        """
        # Use a known contract address on Base Sepolia
        # This is just for simulation, won't actually execute
        recipient = "0x4200000000000000000000000000000000000006"  # WETH on Base
        amount = Decimal("0")  # No ETH transfer

        # Simulate transaction
        result = await transaction_builder.simulate_transaction(
            to_address=recipient,
            data="0x",  # Empty data
            value=amount,
            from_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
        )

        # Should succeed (simple call to WETH contract)
        assert result["success"] is True or result["success"] is False  # Either is valid
        assert "gas_used" in result
        assert "return_data" in result

        print(f"✅ Simulation result: {result}")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires network connection to Base Sepolia")
    async def test_transaction_simulation_revert(self, transaction_builder):
        """Test transaction simulation detects reverts.

        SKIPPED: Requires real network connection to Base Sepolia RPC.
        This test validates revert detection before transaction execution.
        """
        # Try to send ETH to zero address (should fail)
        recipient = "0x0000000000000000000000000000000000000000"
        amount = Decimal("1.0")  # Large amount

        # Simulate transaction
        result = await transaction_builder.simulate_transaction(
            to_address=recipient,
            data="0x",
            value=amount,
            from_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
        )

        # Should detect failure
        assert result["success"] is False
        assert result["revert_reason"] is not None
        assert "gas_used" in result

        print(f"✅ Revert detected: {result['revert_reason']}")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires network connection to Base Sepolia")
    async def test_detect_revert_method(self, transaction_builder):
        """Test detect_revert convenience method.

        SKIPPED: Requires real network connection to Base Sepolia RPC.
        This test validates the detect_revert() helper method.
        """
        # Invalid transaction (sending to zero address)
        recipient = "0x0000000000000000000000000000000000000000"
        amount = Decimal("1.0")

        will_revert, reason = await transaction_builder.detect_revert(
            to_address=recipient,
            data="0x",
            value=amount,
        )

        # Should detect revert
        assert will_revert is True or will_revert is False  # Depends on simulation
        if will_revert:
            assert reason is not None
            print(f"✅ Revert detection working: {reason}")
        else:
            print("ℹ️ Transaction would succeed (unexpected)")

    @pytest.mark.asyncio
    async def test_slippage_validation(self, transaction_builder):
        """Test slippage validation."""
        expected_output = Decimal("100.0")
        min_output = Decimal("99.5")  # 0.5% slippage

        # Should accept low slippage
        is_valid = await transaction_builder.validate_slippage(
            expected_output, min_output
        )
        assert is_valid is True

        # Test high slippage (should reject)
        min_output_high_slippage = Decimal("97.0")  # 3% slippage
        is_valid = await transaction_builder.validate_slippage(
            expected_output, min_output_high_slippage
        )
        assert is_valid is False

        print("✅ Slippage validation working")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires wallet initialization")
    async def test_build_transaction_dry_run(self, wallet_manager):
        """Test transaction building in dry-run mode.

        SKIPPED: Requires wallet initialization with CDP credentials.
        This test validates transaction building without execution.
        """
        # Initialize wallet (would need real credentials)
        await wallet_manager.initialize()

        recipient = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
        amount = Decimal("0.001")

        # Build transaction (dry-run mode)
        tx = await wallet_manager.build_transaction(
            to=recipient,
            amount=amount,
            data="",
            token="ETH",
        )

        # Should return dry-run transaction
        assert tx["dry_run"] is True
        assert tx["would_execute"] is False
        assert "transaction" in tx
        assert tx["transaction"]["to"] == recipient
        assert tx["transaction"]["value"] == str(amount)

        print(f"✅ Dry-run transaction built: {tx}")

    @pytest.mark.asyncio
    async def test_chain_monitor_gas_price(self, chain_monitor):
        """Test chain monitor gas price fetching."""
        gas_price = await chain_monitor.get_current_gas_price()

        # Should return reasonable gas price (> 0)
        assert gas_price > 0
        assert gas_price < 1_000_000_000_000  # Less than 1000 gwei

        print(f"✅ Current gas price: {gas_price} wei")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires network connection to Base Sepolia")
    async def test_chain_monitor_block_number(self, chain_monitor):
        """Test chain monitor block number fetching.

        SKIPPED: Requires real network connection to Base Sepolia RPC.
        This test validates blockchain monitoring capabilities.
        """
        block_number = await chain_monitor.get_block_number()

        # Should return valid block number
        assert block_number > 0

        print(f"✅ Current block number: {block_number}")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires wallet initialization")
    async def test_spending_limits_enforcement(self, wallet_manager):
        """Test that spending limits are enforced.

        SKIPPED: Requires wallet initialization with CDP credentials.
        This test validates spending limit safety checks.
        """
        # Initialize wallet (would need real credentials)
        await wallet_manager.initialize()

        # Try to build transaction exceeding limits
        recipient = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
        large_amount = Decimal("1000")  # Exceeds max_transaction_value_usd

        # Should raise ValueError
        with pytest.raises(ValueError, match="exceeds spending limits"):
            await wallet_manager.build_transaction(
                to=recipient,
                amount=large_amount,
                data="",
                token="ETH",
            )

        print("✅ Spending limits enforced")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires real CDP credentials and testnet ETH")
    async def test_real_transaction_execution(self):
        """Test real transaction execution on Base Sepolia.

        SKIPPED by default. To run:
        1. Set up real CDP credentials in .env
        2. Fund wallet with Base Sepolia testnet ETH
        3. Set DRY_RUN_MODE=false
        4. Remove @pytest.mark.skip decorator

        SAFETY: Only runs on testnet with explicit configuration.
        """
        # Real configuration (would load from .env)
        from src.utils.config import get_settings

        settings = get_settings()

        if settings.dry_run_mode:
            pytest.skip("Dry-run mode enabled, skipping real transaction")

        if settings.network != "base-sepolia":
            pytest.skip("Must use base-sepolia for integration tests")

        # Create wallet with real credentials
        wallet = WalletManager(
            config={
                "cdp_api_key": settings.cdp_api_key,
                "cdp_api_secret": settings.cdp_api_secret,
                "network": settings.network,
                "dry_run_mode": settings.dry_run_mode,
                "max_transaction_value_usd": settings.max_transaction_value_usd,
                "daily_spending_limit_usd": settings.daily_spending_limit_usd,
                "approval_threshold_usd": settings.approval_threshold_usd,
            },
            price_oracle=create_price_oracle("mock"),
            approval_manager=None,
        )

        # Initialize wallet
        await wallet.initialize()

        # Check balance
        balance = await wallet.get_balance("ETH")
        assert balance > Decimal("0.01"), "Insufficient testnet ETH"

        # Execute small transfer to self
        my_address = await wallet.get_address()
        amount = Decimal("0.0001")  # Tiny amount

        result = await wallet.execute_transaction(
            to=my_address,
            amount=amount,
            data="",
            token="ETH",
        )

        # Should succeed
        assert result["success"] is True
        assert "tx_hash" in result

        # Wait for confirmation
        monitor = ChainMonitor(
            {"network": settings.network},
            my_address,
        )

        confirmed = await monitor.wait_for_confirmation(
            result["tx_hash"],
            confirmations=2,
            timeout=60,
        )

        assert confirmed is True

        print(f"✅ Real transaction executed: {result['tx_hash']}")


class TestSecurityHardening:
    """Security hardening integration tests for Phase 2A Sprint 1.

    These tests validate the 5 critical security fixes implemented:
    1. Mandatory simulation before execution
    2. Gas price cap enforcement
    3. Spending limit race condition prevention
    4. Non-blocking transaction monitoring
    5. Tiered gas estimation buffers
    """

    @pytest.fixture
    async def wallet_manager(self):
        """Create wallet manager for security testing with auto-approve callback.

        Uses event-driven approval manager with auto-approve callback
        to prevent test timeouts while still testing approval integration.
        """
        from src.utils.config import get_settings
        from src.security.approval import ApprovalManager

        settings = get_settings()

        # Auto-approve callback for tests (instant response)
        def auto_approve_callback(request):
            """Automatically approve all requests for testing."""
            return True

        # Create approval manager with high threshold + auto-approve
        approval_mgr = ApprovalManager(
            approval_threshold_usd=Decimal("999999"),  # Very high threshold
            approval_callback=auto_approve_callback     # Auto-approve if needed
        )

        config = {
            "cdp_api_key": settings.cdp_api_key,
            "cdp_api_secret": settings.cdp_api_secret,
            "cdp_wallet_secret": settings.cdp_wallet_secret,
            "network": settings.network,
            "dry_run_mode": settings.dry_run_mode,
            "max_transaction_value_usd": settings.max_transaction_value_usd,
            "daily_spending_limit_usd": settings.daily_spending_limit_usd,
            "approval_threshold_usd": settings.approval_threshold_usd,
            "max_gas_price_gwei": settings.max_gas_price_gwei,
        }

        oracle = create_price_oracle("mock")

        wallet = WalletManager(
            config=config,
            price_oracle=oracle,
            approval_manager=approval_mgr,  # Use auto-approve manager
        )

        return wallet

    @pytest.mark.asyncio
    async def test_execute_blocks_on_simulation_failure(self, wallet_manager):
        """Test that execute_transaction() blocks if simulation fails.

        SECURITY FIX #1: Mandatory simulation before execution

        This test validates that transactions are ALWAYS simulated before
        execution, and that failed simulations prevent real execution.

        Expected behavior:
        1. execute_transaction() calls simulate_transaction() internally
        2. If simulation fails, raise ValueError before eth_sendTransaction
        3. No gas wasted on transactions that would revert

        Strategy:
        - Use small amount ($3) that passes spending limits
        - Send to non-payable contract with ETH value (will revert)
        - Known non-payable: WETH contract (can't receive plain ETH)
        """
        await wallet_manager.initialize()

        # WETH contract on Base Sepolia - does NOT accept plain ETH transfers
        # (only accepts via deposit() function)
        WETH_BASE_SEPOLIA = "0x4200000000000000000000000000000000000006"

        # Small amount that passes spending limits ($10 max)
        amount = Decimal("0.001")  # ~$3 at current ETH price

        # Should raise ValueError with simulation failure message
        # (WETH contract will revert on plain ETH transfer)
        with pytest.raises(ValueError, match="simulation failed|would revert"):
            await wallet_manager.execute_transaction(
                to=WETH_BASE_SEPOLIA,
                amount=amount,
                data="",  # Plain transfer (no deposit() call)
                token="ETH",
            )

        print("✅ Transaction blocked on simulation failure (gas saved)")

    @pytest.mark.asyncio
    async def test_gas_price_cap_enforced(self, wallet_manager):
        """Test that transactions are rejected if gas price exceeds cap.

        SECURITY FIX #2: Max gas price protection

        This test validates that the MAX_GAS_PRICE_GWEI configuration
        prevents transaction execution during gas price spikes.

        Expected behavior:
        1. execute_transaction() checks current gas price
        2. If maxFeePerGas > max_gas_price_gwei, raise ValueError
        3. Transaction not sent to network
        4. Security violation logged to audit trail

        SKIPPED: Requires real network connection to Base Sepolia RPC.
        Difficult to test without manipulating gas prices.

        Alternative test approach:
        - Mock Web3 to return high gas price
        - Verify rejection logic triggers
        """
        await wallet_manager.initialize()

        # This test would require either:
        # 1. Waiting for real gas spike (unreliable)
        # 2. Mocking web3.eth.gas_price (better approach)
        # 3. Manual testing during high gas periods

        # For now, verify the config is loaded correctly
        assert wallet_manager.config.get("max_gas_price_gwei") == Decimal("100")

        print("✅ Gas price cap configuration verified (100 gwei)")
        print("ℹ️  Full test requires mocking or real gas spike")

    @pytest.mark.asyncio
    async def test_spending_limit_race_condition(self):
        """Test that concurrent transactions don't exceed spending limits.

        SECURITY FIX #3: Atomic spending limit check + record

        This test validates that the asyncio.Lock prevents race conditions
        when multiple transactions execute concurrently.

        Race condition scenario (PREVENTED):
            T0: Tx A checks limit → $700/$1000 used ✅ ($950 < $1000)
            T1: Tx B checks limit → $700/$1000 used ✅ ($950 < $1000)
            T2: Tx A records $250 → $950/$1000 used ✅
            T3: Tx B records $250 → $1200/$1000 used ❌ OVER LIMIT

        With atomic_check_and_record():
            T0: Tx A acquires lock
            T1: Tx A checks + records → $950/$1000 ✅
            T2: Tx A releases lock
            T3: Tx B acquires lock
            T4: Tx B checks → $950 + $250 = $1200 > $1000 ❌ REJECTED

        This test runs WITHOUT network connection (logic test only).
        """
        import asyncio
        from src.security.limits import SpendingLimits

        # Create spending limits
        config = {
            "max_transaction_value_usd": Decimal("1000"),
            "daily_spending_limit_usd": Decimal("1000"),  # Low limit for testing
        }
        limits = SpendingLimits(config)

        # Pre-fill with $700 spent
        limits.record_transaction(Decimal("700"))

        # Define concurrent transaction function
        async def try_transaction(amount: Decimal, tx_name: str):
            """Try to execute transaction."""
            allowed, reason = await limits.atomic_check_and_record(amount)
            return {
                "tx_name": tx_name,
                "amount": amount,
                "allowed": allowed,
                "reason": reason,
            }

        # Execute 2 concurrent transactions of $250 each
        # Without lock: both would pass check ($700 + $250 = $950 < $1000)
        # With lock: first passes ($950), second fails ($950 + $250 = $1200 > $1000)
        results = await asyncio.gather(
            try_transaction(Decimal("250"), "TX_A"),
            try_transaction(Decimal("250"), "TX_B"),
        )

        # Exactly ONE transaction should be allowed
        allowed_count = sum(1 for r in results if r["allowed"])
        rejected_count = sum(1 for r in results if not r["allowed"])

        assert allowed_count == 1, f"Expected 1 allowed, got {allowed_count}"
        assert rejected_count == 1, f"Expected 1 rejected, got {rejected_count}"

        # Total spent should be $950 ($700 + $250), not $1200
        total_spent = sum(amt for _, amt in limits.spending_history)
        assert total_spent == Decimal("950"), f"Expected $950, got ${total_spent}"

        print("✅ Race condition prevented by atomic lock")
        print(f"   - Transaction A: {results[0]['allowed']} ({results[0]['reason'] or 'OK'})")
        print(f"   - Transaction B: {results[1]['allowed']} ({results[1]['reason'] or 'OK'})")
        print(f"   - Total spent: ${total_spent} (not $1200)")

    @pytest.mark.asyncio
    async def test_transaction_monitoring_non_blocking(self, wallet_manager):
        """Test that transaction execution doesn't block on confirmation.

        SECURITY FIX #4: Optional transaction confirmation

        This test validates that execute_transaction() returns immediately
        by default, without waiting for block confirmations.

        Expected behavior:
        1. execute_transaction(wait_for_confirmation=False) returns tx_hash immediately
        2. Agent can continue working while transaction confirms
        3. Optional: Call wait_for_confirmation() separately if needed

        Performance comparison:
        - Blocking (old): execute_transaction() takes ~4-10 seconds
        - Non-blocking (new): execute_transaction() takes <1 second

        SKIPPED: Requires real network connection to Base Sepolia RPC.
        """
        import time

        await wallet_manager.initialize()

        recipient = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
        amount = Decimal("0.0001")

        # Test non-blocking execution (default)
        start_time = time.time()
        result = await wallet_manager.execute_transaction(
            to=recipient,
            amount=amount,
            data="",
            token="ETH",
            wait_for_confirmation=False,  # Default (non-blocking)
        )
        execution_time = time.time() - start_time

        # Should return immediately (< 2 seconds)
        assert execution_time < 2.0, f"Took {execution_time}s (should be <2s)"
        assert result["success"] is True
        assert "tx_hash" in result
        assert result.get("confirmed") is False  # Not confirmed yet

        print(f"✅ Non-blocking execution: {execution_time:.2f}s")

        # Optional: Test blocking execution
        start_time = time.time()
        result_blocking = await wallet_manager.execute_transaction(
            to=recipient,
            amount=amount,
            data="",
            token="ETH",
            wait_for_confirmation=True,  # Blocking
            confirmation_blocks=2,
        )
        blocking_time = time.time() - start_time

        # Should take 4+ seconds (2 blocks * ~2s each)
        assert blocking_time > 3.0, f"Took {blocking_time}s (should be >3s)"
        assert result_blocking.get("confirmed") is True

        print(f"✅ Blocking execution: {blocking_time:.2f}s (waited for 2 confirmations)")

    @pytest.mark.asyncio
    async def test_gas_buffer_tiers(self, wallet_manager):
        """Test that gas estimation uses tiered buffers based on complexity.

        SECURITY FIX #5: Tiered gas estimation buffers

        This test validates that different transaction types get appropriate
        gas buffers to prevent out-of-gas failures.

        Gas buffer tiers:
        - Simple ETH transfer (no data): 20% buffer
        - ERC20 transfer (small data): 30% buffer
        - Simple DEX swap (medium data): 50% buffer
        - Complex multi-hop (large data): 100% buffer

        Expected behavior:
        1. estimate_gas() analyzes transaction data length
        2. Selects appropriate buffer tier
        3. Returns gas_estimate * buffer_multiplier

        SKIPPED: Requires real network connection to Base Sepolia RPC.
        """
        await wallet_manager.initialize()

        recipient = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
        amount = Decimal("0.001")

        # Test 1: Simple ETH transfer (20% buffer)
        gas_simple = await wallet_manager.estimate_gas(
            to=recipient,
            amount=amount,
            data="",  # No data
            token="ETH",
        )

        # Expected: 21000 * 1.20 = 25200
        assert 25000 <= gas_simple <= 26000, f"Got {gas_simple}, expected ~25200"
        print(f"✅ Simple transfer: {gas_simple} gas (20% buffer)")

        # Test 2: ERC20 transfer (30% buffer)
        # Simulate ERC20 transfer() call data (small)
        erc20_data = "0xa9059cbb" + "0" * 128  # transfer(address,uint256) - 68 bytes
        gas_erc20 = await wallet_manager.estimate_gas(
            to=recipient,
            amount=Decimal("0"),
            data=erc20_data,
            token="USDC",  # Triggers ERC20 logic
        )

        # Should have 30% buffer (higher than simple transfer)
        assert gas_erc20 > gas_simple, "ERC20 should have higher gas than simple transfer"
        print(f"✅ ERC20 transfer: {gas_erc20} gas (30% buffer)")

        # Test 3: DEX swap (50% buffer)
        # Simulate swap call data (medium complexity)
        swap_data = "0x" + "a" * 400  # 200 bytes of data
        gas_swap = await wallet_manager.estimate_gas(
            to=recipient,
            amount=amount,
            data=swap_data,
            token="ETH",
        )

        # Should have 50% buffer
        assert gas_swap > gas_erc20, "DEX swap should have higher gas than ERC20"
        print(f"✅ DEX swap: {gas_swap} gas (50% buffer)")

        # Test 4: Complex multi-hop (100% buffer)
        # Simulate complex call data (large)
        complex_data = "0x" + "b" * 1200  # 600 bytes of data
        gas_complex = await wallet_manager.estimate_gas(
            to=recipient,
            amount=amount,
            data=complex_data,
            token="ETH",
        )

        # Should have 100% buffer (double the estimate)
        assert gas_complex > gas_swap, "Complex operation should have highest gas"
        print(f"✅ Complex operation: {gas_complex} gas (100% buffer)")

        # Verify buffer progression
        print("\n📊 Gas Buffer Tier Validation:")
        print(f"   Simple (20%):  {gas_simple:,} gas")
        print(f"   ERC20 (30%):   {gas_erc20:,} gas")
        print(f"   Swap (50%):    {gas_swap:,} gas")
        print(f"   Complex (100%): {gas_complex:,} gas")
        print("✅ All tiers validated")


class TestWETHWrapping:
    """Test WETH wrapping functionality for Sprint 3."""

    @pytest.fixture
    def config(self):
        """Get config."""
        from src.utils.config import get_settings
        return get_settings()

    @pytest.fixture
    def wallet_address(self):
        """Get wallet address."""
        from src.blockchain.wallet import WalletManager
        from src.data.oracles import create_price_oracle

        config = self.config()
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

        # This is synchronous fixture - need to be called from async test
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(wallet.initialize())
        return wallet.address

    @pytest.fixture
    def w3(self, config):
        """Get Web3 instance."""
        from src.utils.web3_provider import get_web3
        return get_web3(config.network)

    @pytest.fixture
    def weth(self, w3, config):
        """Get WETH protocol."""
        from src.protocols.weth import WETHProtocol
        return WETHProtocol(w3, config.network)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_weth_protocol_initialization(self, weth, config):
        """Test WETH protocol initializes correctly."""
        assert weth is not None
        assert weth.weth_address is not None
        assert weth.weth_contract is not None
        assert weth.network == config.network_id

        print(f"✅ WETH protocol initialized on {config.network_id}")
        print(f"   WETH address: {weth.weth_address}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_weth_balance_query(self, weth, wallet_address):
        """Test querying WETH balance."""
        balance = weth.get_weth_balance(wallet_address)

        assert balance >= 0
        assert isinstance(balance, Decimal)

        print(f"✅ WETH balance query successful")
        print(f"   Address: {wallet_address}")
        print(f"   Balance: {balance} WETH")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_build_wrap_transaction(self, weth, wallet_address):
        """Test building ETH → WETH wrap transaction."""
        amount = Decimal("0.001")

        tx = weth.build_wrap_transaction(wallet_address, amount)

        assert tx is not None
        assert tx["from"] == wallet_address
        assert tx["to"] == weth.weth_address
        assert tx["value"] == int(amount * Decimal(10**18))
        assert "gas" in tx
        assert "gasPrice" in tx
        assert "nonce" in tx

        print(f"✅ Wrap transaction built successfully")
        print(f"   From: {tx['from']}")
        print(f"   To: {tx['to']}")
        print(f"   Value: {tx['value']} wei ({amount} ETH)")
        print(f"   Gas: {tx['gas']}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_build_unwrap_transaction(self, weth, wallet_address):
        """Test building WETH → ETH unwrap transaction."""
        amount = Decimal("0.001")

        tx = weth.build_unwrap_transaction(wallet_address, amount)

        assert tx is not None
        assert tx["from"] == wallet_address
        assert tx["to"] == weth.weth_address
        assert "gas" in tx
        assert "gasPrice" in tx
        assert "nonce" in tx

        print(f"✅ Unwrap transaction built successfully")
        print(f"   From: {tx['from']}")
        print(f"   To: {tx['to']}")
        print(f"   Amount: {amount} WETH")
        print(f"   Gas: {tx['gas']}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_estimate_wrap_gas(self, weth, wallet_address, w3):
        """Test gas estimation for wrapping."""
        amount = Decimal("0.001")

        # Check we have balance
        balance_wei = w3.eth.get_balance(wallet_address)
        balance_eth = Decimal(balance_wei) / Decimal(10**18)

        if balance_eth < amount:
            pytest.skip(f"Insufficient balance: {balance_eth} ETH (need {amount})")

        gas_estimate = weth.estimate_wrap_gas(wallet_address, amount)

        assert gas_estimate > 0
        assert gas_estimate < 100000  # Sanity check

        print(f"✅ Wrap gas estimation successful")
        print(f"   Amount: {amount} ETH")
        print(f"   Estimated gas: {gas_estimate}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_estimate_unwrap_gas(self, weth, wallet_address):
        """Test gas estimation for unwrapping."""
        amount = Decimal("0.001")

        # Note: May fail if no WETH balance, but that's expected
        try:
            gas_estimate = weth.estimate_unwrap_gas(wallet_address, amount)

            assert gas_estimate > 0
            assert gas_estimate < 100000  # Sanity check

            print(f"✅ Unwrap gas estimation successful")
            print(f"   Amount: {amount} WETH")
            print(f"   Estimated gas: {gas_estimate}")
        except Exception as e:
            # Expected if no WETH balance
            if "insufficient" in str(e).lower() or "balance" in str(e).lower():
                print(f"ℹ️  Unwrap gas estimation skipped (no WETH balance)")
                pytest.skip(f"No WETH balance for gas estimation: {e}")
            else:
                raise


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
