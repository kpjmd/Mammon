"""Integration test for first optimizer-driven rebalance execution.

This test validates the complete end-to-end flow:
1. YieldScanner finds opportunities (mocked for testnet)
2. OptimizerAgent generates recommendations
3. RebalanceExecutor executes the rebalance
4. All steps complete successfully
5. Gas costs and balances are tracked

Uses MockProtocolSimulator for safe, predictable testing.
"""

import pytest
from decimal import Decimal
from typing import Dict

from src.agents.yield_scanner import YieldScannerAgent
from src.agents.optimizer import OptimizerAgent
from src.strategies.simple_yield import SimpleYieldStrategy
from src.blockchain.wallet import WalletManager
from src.blockchain.protocol_action_executor import ProtocolActionExecutor
from src.blockchain.mock_protocol_simulator import MockProtocolSimulator
from src.blockchain.rebalance_executor import RebalanceExecutor, RebalanceStep
from src.blockchain.gas_estimator import GasEstimator
from src.data.oracles import create_price_oracle
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TestFirstOptimizerRebalance:
    """Test suite for first optimizer-driven rebalance execution."""

    @pytest.fixture
    def config(self) -> Dict:
        """Create test configuration."""
        return {
            "network": "base-sepolia",
            "read_only": True,
            "dry_run_mode": True,
            "use_mock_data": False,
            "chainlink_enabled": False,
            "chainlink_fallback_to_mock": True,
            # Profitability gates
            "min_annual_gain_usd": Decimal("10"),
            "max_break_even_days": 30,
            "max_cost_pct": Decimal("0.01"),
            # Strategy settings
            "min_apy_improvement": Decimal("0.5"),
            "min_rebalance_amount": Decimal("100"),
            # Safety limits
            "max_transaction_value_usd": Decimal("10000"),
            "daily_spending_limit_usd": Decimal("50000"),
            "approval_threshold_usd": Decimal("5000"),
        }

    @pytest.fixture
    async def wallet_manager(self, config):
        """Create wallet manager for testing."""
        # Use mock price oracle
        oracle = create_price_oracle("mock")

        wallet = WalletManager(
            config=config,
            price_oracle=oracle,
            approval_manager=None,
        )

        # Note: We don't initialize the wallet for mock testing
        # In real testnet execution, you would call await wallet.initialize()

        return wallet

    @pytest.fixture
    def mock_protocol_executor(self):
        """Create mock protocol executor for safe testing."""
        return MockProtocolSimulator()

    @pytest.fixture
    async def gas_estimator(self, config):
        """Create gas estimator."""
        oracle = create_price_oracle("mock")
        return GasEstimator(
            network=config["network"],
            price_oracle=oracle,
            cache_ttl_seconds=300,
        )

    @pytest.fixture
    async def rebalance_executor(
        self,
        wallet_manager,
        mock_protocol_executor,
        gas_estimator,
        config,
    ):
        """Create rebalance executor with mock protocol executor."""
        oracle = create_price_oracle("mock")

        return RebalanceExecutor(
            wallet_manager=wallet_manager,
            protocol_executor=mock_protocol_executor,
            gas_estimator=gas_estimator,
            price_oracle=oracle,
            config=config,
            swap_router=None,  # No swaps in Phase 4 Sprint 1
        )

    @pytest.fixture
    def yield_scanner(self, config):
        """Create yield scanner."""
        return YieldScannerAgent(config)

    @pytest.fixture
    def simple_strategy(self, config):
        """Create simple yield strategy."""
        return SimpleYieldStrategy(config)

    @pytest.fixture
    def optimizer(self, config, yield_scanner, simple_strategy):
        """Create optimizer agent."""
        return OptimizerAgent(config, yield_scanner, simple_strategy)

    @pytest.mark.asyncio
    async def test_mock_rebalance_execution(
        self,
        rebalance_executor,
        mock_protocol_executor,
    ):
        """Test rebalance execution with mock protocol simulator.

        This test validates the complete workflow using MockProtocolSimulator
        to ensure all steps execute correctly without real blockchain transactions.
        """
        from src.strategies.base_strategy import RebalanceRecommendation

        # Create a test recommendation
        recommendation = RebalanceRecommendation(
            from_protocol="Moonwell",
            to_protocol="Aave V3",
            token="USDC",
            amount=Decimal("1000"),
            expected_apy=Decimal("8.5"),
            reason="Higher APY in Aave V3 (8.5% vs 5.2%)",
            confidence=85,
        )

        logger.info(f"Testing rebalance: {recommendation.from_protocol} → "
                   f"{recommendation.to_protocol}")

        # Execute rebalance
        execution = await rebalance_executor.execute_rebalance(recommendation)

        # Validate execution results
        assert execution.success, "Rebalance execution should succeed"
        assert execution.completed_at is not None, "Should have completion timestamp"

        # Validate all steps completed
        expected_steps = [
            RebalanceStep.VALIDATION,
            RebalanceStep.BALANCE_CHECK,
            RebalanceStep.WITHDRAW,
            RebalanceStep.APPROVE_DEPOSIT,
            RebalanceStep.DEPOSIT,
            RebalanceStep.VERIFICATION,
        ]

        completed_steps = [step.step for step in execution.steps]
        for expected_step in expected_steps:
            assert expected_step in completed_steps, \
                f"Step {expected_step.value} should be completed"

        # Validate all steps succeeded
        for step in execution.steps:
            assert step.success, f"Step {step.step.value} should succeed"

        # Validate gas tracking
        assert execution.total_gas_used > 0, "Should track gas usage"
        assert execution.total_gas_cost_eth >= 0, "Should calculate ETH cost"
        assert execution.total_gas_cost_usd >= 0, "Should calculate USD cost"

        # Print execution summary
        summary = rebalance_executor.get_execution_summary(execution)
        logger.info(f"\n{summary}")

        # Validate transaction hashes exist
        withdraw_result = execution.get_step_result(RebalanceStep.WITHDRAW)
        assert withdraw_result is not None
        assert withdraw_result.tx_hash is not None
        assert withdraw_result.tx_hash.startswith("0xmock_")

        deposit_result = execution.get_step_result(RebalanceStep.DEPOSIT)
        assert deposit_result is not None
        assert deposit_result.tx_hash is not None
        assert deposit_result.tx_hash.startswith("0xmock_")

        logger.info("✅ Mock rebalance execution test passed!")

    @pytest.mark.asyncio
    async def test_new_position_execution(self, rebalance_executor):
        """Test creating a new position (no withdrawal needed)."""
        from src.strategies.base_strategy import RebalanceRecommendation

        # Create recommendation for new position
        recommendation = RebalanceRecommendation(
            from_protocol=None,  # New position, no source
            to_protocol="Aave V3",
            token="USDC",
            amount=Decimal("500"),
            expected_apy=Decimal("7.2"),
            reason="New position in Aave V3",
            confidence=90,
        )

        # Execute rebalance
        execution = await rebalance_executor.execute_rebalance(recommendation)

        # Should succeed
        assert execution.success

        # Should NOT have withdraw step
        withdraw_result = execution.get_step_result(RebalanceStep.WITHDRAW)
        assert withdraw_result is None, "Should not withdraw for new position"

        # Should have deposit step
        deposit_result = execution.get_step_result(RebalanceStep.DEPOSIT)
        assert deposit_result is not None
        assert deposit_result.success

        logger.info("✅ New position execution test passed!")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires full optimizer setup with yield data")
    async def test_full_optimizer_to_executor_flow(
        self,
        optimizer,
        rebalance_executor,
    ):
        """Test complete flow from optimizer to executor.

        SKIPPED: This test requires full yield scanner setup with either:
        - Real testnet protocol data
        - Mock yield opportunities

        Enable this test when ready for full integration testing.
        """
        # Define current positions
        current_positions = {
            "Moonwell": Decimal("5000"),  # $5k in Moonwell
            "Aave V3": Decimal("3000"),   # $3k in Aave V3
        }

        # Get rebalance recommendations from optimizer
        recommendations = await optimizer.find_rebalance_opportunities(
            current_positions
        )

        assert len(recommendations) > 0, "Optimizer should find opportunities"

        # Execute first recommendation
        first_rec = recommendations[0]
        execution = await rebalance_executor.execute_rebalance(first_rec)

        # Validate execution
        assert execution.success
        assert execution.total_gas_used > 0

        logger.info(f"Executed optimizer recommendation: "
                   f"{first_rec.from_protocol} → {first_rec.to_protocol}")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires real testnet wallet and funds")
    async def test_real_testnet_execution(self, config):
        """Test real execution on Base Sepolia testnet.

        SKIPPED BY DEFAULT: This test requires:
        - Real wallet with WALLET_SEED configured
        - Base Sepolia ETH for gas
        - Test USDC on Base Sepolia
        - Aave V3 deployed on Sepolia (or other protocol)

        To run this test:
        1. Set up .env with WALLET_SEED and ALCHEMY_API_KEY
        2. Fund wallet with Sepolia ETH
        3. Get test USDC on Sepolia
        4. Remove @pytest.mark.skip decorator
        5. Run: pytest tests/integration/test_first_optimizer_rebalance.py::TestFirstOptimizerRebalance::test_real_testnet_execution -v
        """
        from src.strategies.base_strategy import RebalanceRecommendation

        # Create REAL wallet and executor
        oracle = create_price_oracle("chainlink")
        wallet = WalletManager(config=config, price_oracle=oracle)
        await wallet.initialize()

        # Use REAL protocol executor (not mock)
        protocol_executor = ProtocolActionExecutor(wallet, config)

        gas_estimator = GasEstimator(
            network=config["network"],
            price_oracle=oracle,
        )

        executor = RebalanceExecutor(
            wallet_manager=wallet,
            protocol_executor=protocol_executor,
            gas_estimator=gas_estimator,
            price_oracle=oracle,
            config=config,
        )

        # Create test recommendation
        recommendation = RebalanceRecommendation(
            from_protocol=None,  # New position
            to_protocol="Aave V3",
            token="USDC",
            amount=Decimal("10"),  # Small test amount
            expected_apy=Decimal("5.0"),
            reason="Test execution on Base Sepolia",
            confidence=100,
        )

        # Execute on REAL testnet
        execution = await executor.execute_rebalance(recommendation)

        # Validate results
        assert execution.success
        assert execution.total_gas_used > 0

        # Print transaction URLs
        for step in execution.steps:
            if step.tx_hash and not step.tx_hash.startswith("0xmock"):
                basescan_url = f"https://sepolia.basescan.org/tx/{step.tx_hash}"
                logger.info(f"📊 View transaction: {basescan_url}")

        logger.info("✅ Real testnet execution successful!")


# Run tests with: pytest tests/integration/test_first_optimizer_rebalance.py -v
