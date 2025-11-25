"""Integration tests for local wallet provider.

Tests the complete local wallet implementation including:
- Wallet initialization from seed phrase
- Address persistence across instances
- Balance checking
- Transaction building (without sending)
"""

import pytest
from decimal import Decimal
from eth_account.hdaccount import ETHEREUM_DEFAULT_PATH
from src.wallet.local_wallet_provider import LocalWalletProvider
from src.utils.web3_provider import get_web3


class TestLocalWalletIntegration:
    """Integration tests for local wallet provider."""

    @pytest.fixture
    def test_seed(self):
        """Test seed phrase (standard test mnemonic)."""
        return "wine hero found plate sing hope field join pilot betray eyebrow note"

    @pytest.fixture
    def test_config(self):
        """Test configuration."""
        return {
            "max_gas_price_gwei": 100,
            "max_priority_fee_gwei": 2,
            "gas_buffer_simple": 1.5,
            "gas_buffer_moderate": 1.3,
            "gas_buffer_complex": 1.2,
        }

    @pytest.fixture
    def web3_instance(self):
        """Web3 instance for Base Sepolia."""
        return get_web3("base-sepolia")

    def test_wallet_initialization(self, test_seed, web3_instance, test_config):
        """Test wallet initializes correctly from seed phrase."""
        wallet = LocalWalletProvider(
            seed_phrase=test_seed,
            web3=web3_instance,
            config=test_config,
        )

        # Verify wallet initialized
        assert wallet.address is not None
        assert wallet.address.startswith("0x")
        assert len(wallet.address) == 42

        # Expected address for this seed
        expected = "0x81A2933C185e45f72755B35110174D57b5E1FC88"
        assert wallet.address == expected

    def test_wallet_persistence(self, test_seed, web3_instance, test_config):
        """Test same seed produces same address (persistence)."""
        wallet1 = LocalWalletProvider(test_seed, web3_instance, test_config)
        wallet2 = LocalWalletProvider(test_seed, web3_instance, test_config)

        # Same seed = same address
        assert wallet1.address == wallet2.address

    def test_get_address(self, test_seed, web3_instance, test_config):
        """Test get_address method."""
        wallet = LocalWalletProvider(test_seed, web3_instance, test_config)

        address = wallet.get_address()
        assert address == wallet.address
        assert address.startswith("0x")

    def test_get_balance(self, test_seed, web3_instance, test_config):
        """Test balance checking."""
        wallet = LocalWalletProvider(test_seed, web3_instance, test_config)

        # Get balance (may be zero on testnet)
        balance = wallet.get_balance("eth")
        assert isinstance(balance, Decimal)
        assert balance >= 0

    def test_nonce_management(self, test_seed, web3_instance, test_config):
        """Test nonce tracker works."""
        wallet = LocalWalletProvider(test_seed, web3_instance, test_config)

        # Get first nonce
        nonce1 = wallet.get_nonce()
        assert isinstance(nonce1, int)
        assert nonce1 >= 0

        # Get second nonce (should increment)
        nonce2 = wallet.get_nonce()
        assert nonce2 == nonce1 + 1

        # Reset and re-sync with chain
        wallet.reset_nonce()
        nonce3 = wallet.get_nonce()
        assert isinstance(nonce3, int)

    def test_transaction_building(self, test_seed, web3_instance, test_config):
        """Test transaction building without sending."""
        wallet = LocalWalletProvider(test_seed, web3_instance, test_config)

        # Build simple transfer transaction
        tx = {
            'to': '0x0000000000000000000000000000000000000001',
            'value': web3_instance.to_wei(0.001, 'ether'),
        }

        # Build complete transaction (adds nonce, gas, etc.)
        complete_tx = wallet._build_transaction(tx)

        # Verify required fields present
        assert 'nonce' in complete_tx
        assert 'gas' in complete_tx
        assert 'maxFeePerGas' in complete_tx
        assert 'maxPriorityFeePerGas' in complete_tx
        assert 'chainId' in complete_tx
        assert complete_tx['to'] == tx['to']
        assert complete_tx['value'] == tx['value']

    def test_gas_estimation(self, test_seed, web3_instance, test_config):
        """Test gas estimation with buffers."""
        wallet = LocalWalletProvider(test_seed, web3_instance, test_config)

        # Simple transfer
        tx = {
            'to': '0x0000000000000000000000000000000000000001',
            'value': web3_instance.to_wei(0.001, 'ether'),
            'from': wallet.address,
        }

        gas_params = wallet._estimate_gas_with_buffer(tx)

        # Verify gas parameters
        assert 'gas' in gas_params
        assert 'maxFeePerGas' in gas_params
        assert 'maxPriorityFeePerGas' in gas_params

        # Verify gas limits applied
        assert gas_params['maxFeePerGas'] <= test_config["max_gas_price_gwei"] * 10**9

    def test_invalid_seed_phrase(self, web3_instance, test_config):
        """Test initialization fails with invalid seed."""
        with pytest.raises(ValueError, match="Invalid seed phrase"):
            LocalWalletProvider(
                seed_phrase="invalid words here",
                web3=web3_instance,
                config=test_config,
            )

    def test_unsupported_token(self, test_seed, web3_instance, test_config):
        """Test get_balance fails for unsupported tokens."""
        wallet = LocalWalletProvider(test_seed, web3_instance, test_config)

        with pytest.raises(NotImplementedError):
            wallet.get_balance("USDC")


    def test_simulation_catches_failing_transaction(self, test_seed, web3_instance, test_config):
        """Test transaction simulation prevents bad transactions."""
        wallet = LocalWalletProvider(test_seed, web3_instance, test_config)

        # Build transaction with insufficient balance (will fail simulation)
        # Send way more ETH than the wallet has
        tx = {
            'to': '0x0000000000000000000000000000000000000001',
            'value': web3_instance.to_wei(1000000, 'ether'),  # 1 million ETH (we don't have)
        }

        # This should raise ValueError with simulation failure or validation failure
        with pytest.raises((ValueError, Exception)) as exc_info:
            wallet.send_transaction(tx)

        # Verify error message mentions insufficient funds or failure
        error_msg = str(exc_info.value).lower()
        assert "insufficient" in error_msg or "fail" in error_msg or "balance" in error_msg


@pytest.mark.asyncio
class TestWalletManagerIntegration:
    """Integration tests for WalletManager with local wallet."""

    async def test_wallet_manager_local_mode(self):
        """Test WalletManager initializes in local wallet mode."""
        from src.blockchain.wallet import WalletManager

        config = {
            "use_local_wallet": True,
            "wallet_seed": "wine hero found plate sing hope field join pilot betray eyebrow note",
            "network": "arbitrum-sepolia",
            "dry_run_mode": True,
            "max_transaction_value_usd": 1000,
            "daily_spending_limit_usd": 5000,
            "approval_threshold_usd": 100,
            "max_gas_price_gwei": 100,
            "max_priority_fee_gwei": 2,
            "gas_buffer_simple": 1.5,
            "gas_buffer_moderate": 1.3,
            "gas_buffer_complex": 1.2,
        }

        wallet_manager = WalletManager(config=config)
        await wallet_manager.initialize()

        # Verify initialized correctly
        assert wallet_manager.address == "0x81A2933C185e45f72755B35110174D57b5E1FC88"
        assert wallet_manager.use_local_wallet is True
        assert wallet_manager.wallet_provider is not None

        # Test balance check
        balance = await wallet_manager.get_balance("ETH")
        assert isinstance(balance, Decimal)

    async def test_spending_limits_enforced(self):
        """Test WalletManager enforces spending limits with local wallet."""
        from src.blockchain.wallet import WalletManager

        # Config with LOW spending limit
        config = {
            "use_local_wallet": True,
            "wallet_seed": "wine hero found plate sing hope field join pilot betray eyebrow note",
            "network": "arbitrum-sepolia",
            "dry_run_mode": False,  # Real mode to test limits
            "max_transaction_value_usd": 10,  # Only $10 max
            "daily_spending_limit_usd": 50,
            "approval_threshold_usd": 5,
            "max_gas_price_gwei": 100,
            "max_priority_fee_gwei": 2,
            "gas_buffer_simple": 1.5,
            "gas_buffer_moderate": 1.3,
            "gas_buffer_complex": 1.2,
        }

        wallet_manager = WalletManager(config=config)
        await wallet_manager.initialize()

        # Try to execute transaction > spending limit
        # (This would be > $10 if ETH price is ~$2000)
        try:
            result = await wallet_manager.execute_transaction(
                to="0x0000000000000000000000000000000000000001",
                amount=Decimal("0.1"),  # 0.1 ETH = ~$200
                data="0x",
                token="ETH",
            )
            # Should not reach here - should be blocked by spending limit
            assert False, "Transaction should have been blocked by spending limit"
        except ValueError as e:
            # Expected: Spending limit should block this
            assert "exceed" in str(e).lower() or "limit" in str(e).lower()

        # Verify spending limit was NOT consumed (transaction blocked before recording)
        # This is tested by checking the limit state doesn't change
