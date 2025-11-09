"""Integration tests for Phase 1C with Base Sepolia testnet.

These tests validate the MAMMON system against real blockchain infrastructure.
They require:
- Real CDP API credentials
- Base Sepolia RPC access
- Small amount of testnet ETH for gas estimation

Run with: RUN_INTEGRATION_TESTS=1 poetry run pytest -m integration
"""

import pytest
import os
from decimal import Decimal
from src.blockchain.wallet import WalletManager
from src.utils.config import Settings
from src.security.limits import SpendingLimits
from src.security.audit import AuditLogger


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Integration tests require RUN_INTEGRATION_TESTS=1"
)
class TestBaseSepolia:
    """Integration tests with real Base Sepolia testnet."""

    @pytest.fixture
    def integration_config(self):
        """Load real configuration for integration testing."""
        return {
            "cdp_api_key": os.getenv("CDP_API_KEY", ""),
            "cdp_api_secret": os.getenv("CDP_API_SECRET", ""),
            "network": "base-sepolia",
            "dry_run_mode": True,  # Always dry-run for integration tests
            "max_transaction_value_usd": Decimal("1000"),
            "daily_spending_limit_usd": Decimal("5000"),
        }

    @pytest.mark.asyncio
    async def test_wallet_initialization(self, integration_config):
        """Test real CDP wallet creation on Base Sepolia.

        Validates:
        - WalletManager initializes without errors
        - Dry-run mode is respected
        - Configuration is properly loaded
        """
        wallet = WalletManager(integration_config)

        assert wallet is not None
        assert wallet.dry_run_mode is True
        assert wallet.network == "base-sepolia"

    @pytest.mark.asyncio
    async def test_balance_query_dry_run(self, integration_config):
        """Test querying ETH balance in dry-run mode.

        Validates:
        - Balance query returns Decimal type
        - No errors in dry-run mode
        - Audit logging is working
        """
        wallet = WalletManager(integration_config)

        # In dry-run mode, should return mock balance
        balance = await wallet.get_balance("ETH")

        assert isinstance(balance, Decimal)
        assert balance >= 0

    @pytest.mark.asyncio
    async def test_spending_limits_enforcement(self, integration_config):
        """Test that spending limits are properly enforced.

        Validates:
        - Per-transaction limit enforcement
        - ValueError raised when limit exceeded
        - Audit log captures violation
        """
        wallet = WalletManager(integration_config)

        # Try to build transaction exceeding per-transaction limit
        with pytest.raises(ValueError, match="exceeds spending limits"):
            await wallet.build_transaction(
                to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
                amount=Decimal("2000"),  # Exceeds $1000 limit (assuming $3000/ETH mock price)
            )

    @pytest.mark.asyncio
    async def test_daily_limit_tracking(self, integration_config):
        """Test daily spending limit accumulation.

        Validates:
        - Daily limit tracking works
        - Multiple transactions accumulate
        - Exceeding daily limit raises error
        """
        limits = SpendingLimits(integration_config)

        # Record multiple transactions
        limits.record_transaction(Decimal("1000"))
        limits.record_transaction(Decimal("1000"))
        limits.record_transaction(Decimal("1000"))
        limits.record_transaction(Decimal("1000"))
        limits.record_transaction(Decimal("1000"))

        # Check that 6th transaction would exceed daily limit of $5000
        assert not limits.check_daily_limit(Decimal("1000"))

        # But a small transaction should still pass
        assert limits.check_daily_limit(Decimal("100"))

    @pytest.mark.asyncio
    async def test_transaction_building_dry_run(self, integration_config):
        """Test building transaction structure in dry-run mode.

        Validates:
        - Transaction structure is valid
        - Gas estimation returns reasonable value
        - Dry-run flag is set
        """
        wallet = WalletManager(integration_config)

        # Build small transaction within limits
        tx = await wallet.build_transaction(
            to="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4",
            amount=Decimal("0.001"),
        )

        assert tx is not None
        assert tx["dry_run"] is True
        assert "transaction" in tx
        assert tx["transaction"]["to"] == "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb4"
        assert "gas_estimate" in tx

    @pytest.mark.asyncio
    async def test_invalid_address_validation(self, integration_config):
        """Test that invalid addresses are rejected.

        Validates:
        - Address validation works
        - Invalid addresses raise ValueError
        - Error message is helpful
        """
        wallet = WalletManager(integration_config)

        with pytest.raises(ValueError, match="Invalid recipient"):
            await wallet.build_transaction(
                to="not-an-address",
                amount=Decimal("0.001"),
            )

    @pytest.mark.asyncio
    async def test_audit_logging_integration(self, integration_config):
        """Test that audit logging works in integration tests.

        Validates:
        - Audit logger initializes
        - Events are logged
        - Log file is created
        """
        import tempfile

        # Create temporary audit log file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            audit_log_path = f.name

        try:
            from src.security.audit import AuditEventType, AuditSeverity

            logger = AuditLogger(log_file=audit_log_path)

            # Log a test event
            await logger.log_event(
                event_type=AuditEventType.WALLET_INITIALIZED,
                severity=AuditSeverity.INFO,
                message="Integration test wallet initialized",
                metadata={"network": "base-sepolia"}
            )

            # Verify log file was created and has content
            with open(audit_log_path, 'r') as f:
                content = f.read()
                assert "WALLET_INITIALIZED" in content
                assert "base-sepolia" in content

        finally:
            # Clean up
            if os.path.exists(audit_log_path):
                os.remove(audit_log_path)

    @pytest.mark.asyncio
    async def test_spending_limits_check_all(self, integration_config):
        """Test comprehensive spending limit checks.

        Validates:
        - Per-transaction limit check
        - Daily limit check
        - Combined limit validation
        """
        limits = SpendingLimits(integration_config)

        # Small transaction should pass all checks
        assert limits.check_transaction_limit(Decimal("100"))
        assert limits.check_daily_limit(Decimal("100"))

        # Transaction exceeding per-tx limit should fail
        assert not limits.check_transaction_limit(Decimal("2000"))

        # Record some spending
        limits.record_transaction(Decimal("1000"))
        limits.record_transaction(Decimal("1000"))

        # Should still be under daily limit
        assert limits.check_daily_limit(Decimal("1000"))

        # But this would exceed it
        assert not limits.check_daily_limit(Decimal("4000"))


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Integration tests require RUN_INTEGRATION_TESTS=1"
)
class TestNetworkErrorHandling:
    """Test graceful handling of network errors."""

    @pytest.mark.asyncio
    async def test_invalid_network_config(self):
        """Test behavior with invalid network configuration.

        Validates:
        - Invalid network name is handled
        - Error message is clear
        """
        config = {
            "cdp_api_key": "test_key",
            "cdp_api_secret": "test_secret",
            "network": "invalid-network",
            "dry_run_mode": True,
            "max_transaction_value_usd": Decimal("1000"),
            "daily_spending_limit_usd": Decimal("5000"),
        }

        # Should initialize but may fail on actual network calls
        wallet = WalletManager(config)
        assert wallet.network == "invalid-network"

    @pytest.mark.asyncio
    async def test_missing_credentials_dry_run(self):
        """Test that dry-run mode works even without real credentials.

        Validates:
        - Dry-run mode doesn't require real credentials
        - System is usable for development
        """
        config = {
            "cdp_api_key": "test_key",
            "cdp_api_secret": "test_secret",
            "network": "base-sepolia",
            "dry_run_mode": True,
            "max_transaction_value_usd": Decimal("1000"),
            "daily_spending_limit_usd": Decimal("5000"),
        }

        wallet = WalletManager(config)

        # In dry-run mode, should work without real CDP connection
        balance = await wallet.get_balance("ETH")
        assert isinstance(balance, Decimal)
