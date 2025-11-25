"""Execute first test transaction: ETH → WETH wrap.

This script executes the first production transaction to validate:
- All 6 security layers working in production
- Gas estimation accuracy
- Transaction execution flow
- Approval manager responsiveness
- Metrics collection (Refinement #3)

Usage:
    python scripts/execute_first_wrap.py [--amount AMOUNT]

Arguments:
    --amount: Amount of ETH to wrap (default: 0.001)
"""

import sys
import json
import time
from decimal import Decimal
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.blockchain.wallet import WalletManager
from src.utils.web3_provider import get_web3
from src.blockchain.transactions import TransactionBuilder
from src.protocols.weth import WETHProtocol
from src.security.limits import SpendingLimits
from src.security.approval import ApprovalManager
from src.data.oracles import create_price_oracle

logger = get_logger(__name__)


class TransactionMetrics:
    """Metrics collection for transaction execution (Refinement #3)."""

    def __init__(self):
        self.metrics: Dict[str, Any] = {
            "transaction_type": "eth_to_weth_wrap",
            "timestamp_start": datetime.now().isoformat(),
            "network": None,
            "wallet_address": None,
            "amount_eth": None,
            "security_layers": {},
            "gas_metrics": {},
            "execution": {},
            "errors": [],
            "success": False,
        }
        self.start_time = time.time()

    def record_config(self, network: str, address: str, amount: Decimal):
        """Record configuration."""
        self.metrics["network"] = network
        self.metrics["wallet_address"] = address
        self.metrics["amount_eth"] = str(amount)

    def record_security_layer(
        self, layer_name: str, passed: bool, details: Dict[str, Any]
    ):
        """Record security layer result."""
        self.metrics["security_layers"][layer_name] = {
            "passed": passed,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }

    def record_gas_metrics(self, metrics: Dict[str, Any]):
        """Record gas-related metrics."""
        self.metrics["gas_metrics"].update(metrics)

    def record_execution(self, tx_hash: str, receipt: Dict[str, Any]):
        """Record transaction execution."""
        self.metrics["execution"] = {
            "tx_hash": tx_hash,
            "block_number": receipt.get("blockNumber"),
            "gas_used": receipt.get("gasUsed"),
            "effective_gas_price": receipt.get("effectiveGasPrice"),
            "status": receipt.get("status"),
            "timestamp": datetime.now().isoformat(),
        }

    def record_error(self, error: str, layer: str = "unknown"):
        """Record an error."""
        self.metrics["errors"].append(
            {"layer": layer, "error": error, "timestamp": datetime.now().isoformat()}
        )

    def finalize(self, success: bool):
        """Finalize metrics collection."""
        self.metrics["success"] = success
        self.metrics["timestamp_end"] = datetime.now().isoformat()
        self.metrics["duration_seconds"] = time.time() - self.start_time

    def save_json(self, filepath: Path):
        """Save metrics as JSON."""
        with open(filepath, "w") as f:
            json.dump(self.metrics, f, indent=2)
        logger.info(f"Metrics saved to {filepath}")

    def save_markdown(self, filepath: Path):
        """Save metrics as markdown report."""
        md = []
        md.append("# First Transaction Execution Report")
        md.append(f"\n**Transaction Type**: {self.metrics['transaction_type']}")
        md.append(f"**Network**: {self.metrics['network']}")
        md.append(f"**Timestamp**: {self.metrics['timestamp_start']}")
        md.append(f"**Duration**: {self.metrics.get('duration_seconds', 0):.2f}s")
        md.append(
            f"**Success**: {'✅ YES' if self.metrics['success'] else '❌ NO'}\n"
        )

        md.append("## Configuration")
        md.append(f"- **Wallet**: `{self.metrics['wallet_address']}`")
        md.append(f"- **Amount**: {self.metrics['amount_eth']} ETH\n")

        md.append("## Security Layers")
        for layer, data in self.metrics["security_layers"].items():
            status = "✅" if data["passed"] else "❌"
            md.append(f"\n### {status} {layer}")
            for key, value in data["details"].items():
                md.append(f"- **{key}**: {value}")

        md.append("\n## Gas Metrics")
        for key, value in self.metrics["gas_metrics"].items():
            md.append(f"- **{key}**: {value}")

        if self.metrics["execution"]:
            md.append("\n## Execution")
            md.append(f"- **TX Hash**: `{self.metrics['execution']['tx_hash']}`")
            md.append(f"- **Block**: {self.metrics['execution']['block_number']}")
            md.append(f"- **Gas Used**: {self.metrics['execution']['gas_used']}")
            md.append(
                f"- **Effective Gas Price**: {self.metrics['execution']['effective_gas_price']}"
            )
            md.append(f"- **Status**: {self.metrics['execution']['status']}")

        if self.metrics["errors"]:
            md.append("\n## Errors")
            for error in self.metrics["errors"]:
                md.append(f"- **[{error['layer']}]**: {error['error']}")

        with open(filepath, "w") as f:
            f.write("\n".join(md))
        logger.info(f"Markdown report saved to {filepath}")


class FirstTransactionExecutor:
    """Execute first test transaction with full metrics collection."""

    def __init__(self, amount_eth: Decimal = Decimal("0.001")):
        self.config = get_settings()
        self.network = self.config.network
        self.amount_eth = amount_eth
        self.metrics = TransactionMetrics()

        # Initialize components
        self.w3 = get_web3(self.network)
        self.weth = WETHProtocol(self.w3, self.network)
        self.wallet = None  # Will be initialized in execute()
        self.wallet_address = None  # Will be set after wallet init

        limit_config = {
            "max_transaction_value_usd": self.config.max_transaction_value_usd,
            "daily_spending_limit_usd": self.config.daily_spending_limit_usd,
        }
        self.spending_limit_mgr = SpendingLimits(limit_config)
        self.approval_mgr = ApprovalManager(
            approval_threshold_usd=self.config.approval_threshold_usd
        )
        self.price_oracle = create_price_oracle(
            "chainlink" if self.config.chainlink_enabled else "mock",
            network=self.network,
            price_network=self.config.chainlink_price_network if self.config.chainlink_enabled else None,
            fallback_to_mock=self.config.chainlink_fallback_to_mock if self.config.chainlink_enabled else True,
        )

    async def _initialize_wallet(self):
        """Initialize wallet manager and wait for funding if needed."""
        wallet_config = {
            "cdp_api_key": self.config.cdp_api_key,
            "cdp_api_secret": self.config.cdp_api_secret,
            "cdp_wallet_secret": self.config.cdp_wallet_secret,
            "use_local_wallet": self.config.use_local_wallet,
            "wallet_seed": self.config.wallet_seed,
            "network": self.network,
            "dry_run_mode": self.config.dry_run_mode,
            "max_transaction_value_usd": float(self.config.max_transaction_value_usd),
            "daily_spending_limit_usd": float(self.config.daily_spending_limit_usd),
            "approval_threshold_usd": float(self.config.approval_threshold_usd),
            "max_gas_price_gwei": float(self.config.max_gas_price_gwei),
            "max_priority_fee_gwei": float(self.config.max_priority_fee_gwei),
            "gas_buffer_simple": self.config.gas_buffer_simple,
            "gas_buffer_moderate": self.config.gas_buffer_moderate,
            "gas_buffer_complex": self.config.gas_buffer_complex,
        }

        self.wallet = WalletManager(
            config=wallet_config,
            price_oracle=self.price_oracle,
            approval_manager=self.approval_mgr,
        )

        await self.wallet.initialize()
        self.wallet_address = self.wallet.address

        # Check balance and wait for funding if needed
        await self._ensure_wallet_funded()

    async def _ensure_wallet_funded(self):
        """Check wallet balance and wait for funding if insufficient."""
        min_balance = Decimal("0.002")  # Need 0.002 ETH minimum

        # Check balance via Web3 (more reliable than CDP API)
        balance_wei = self.w3.eth.get_balance(self.wallet_address)
        balance_eth = Decimal(balance_wei) / Decimal(10**18)

        if balance_eth >= min_balance:
            print(f"✅ Wallet funded: {balance_eth} ETH")
            return

        # Wallet needs funding
        print()
        print("=" * 80)
        print("⚠️  WALLET FUNDING REQUIRED")
        print("=" * 80)
        print()
        print("CDP created a new wallet that needs funding:")
        print(f"  Address: {self.wallet_address}")
        print(f"  Network: {self.network}")
        print(f"  Current Balance: {balance_eth} ETH")
        print(f"  Required: {min_balance} ETH minimum")
        print()
        print("📤 PLEASE FUND THIS WALLET NOW:")
        print(f"   1. Send at least {min_balance} ETH to: {self.wallet_address}")
        print(f"   2. Network: {self.network}")
        print(f"   3. Wait for transaction to confirm")
        print()

        # Wait for user to fund
        input("Press ENTER after you've sent the funds and they've confirmed...")

        # Check balance again
        print()
        print("🔍 Checking balance...")
        balance_wei = self.w3.eth.get_balance(self.wallet_address)
        balance_eth = Decimal(balance_wei) / Decimal(10**18)

        if balance_eth >= min_balance:
            print(f"✅ Funding confirmed: {balance_eth} ETH")
            print()
        else:
            print(f"❌ Still insufficient: {balance_eth} ETH (need {min_balance} ETH)")
            print()
            retry = input("Retry balance check? (y/n): ")
            if retry.lower() == 'y':
                await self._ensure_wallet_funded()  # Recursive retry
            else:
                raise ValueError(f"Insufficient balance: {balance_eth} ETH")

    async def execute(self) -> bool:
        """Execute transaction with all security layers."""
        # Initialize wallet first
        await self._initialize_wallet()

        print("=" * 80)
        print("MAMMON FIRST TEST TRANSACTION")
        print(f"Type: ETH → WETH Wrap")
        print(f"Amount: {self.amount_eth} ETH")
        print(f"Network: {self.network}")
        print(f"Wallet: {self.wallet_address}")
        print("=" * 80)

        # Record config now that we have wallet address
        self.metrics.record_config(self.network, self.wallet_address, self.amount_eth)

        try:
            # Security Layer 1: Spending Limits
            if not await self._check_spending_limits():
                return False

            # Security Layer 2: Build Transaction
            tx = self._build_transaction()
            if not tx:
                return False

            # Security Layer 3: Simulation
            if not await self._simulate_transaction(tx):
                return False

            # Security Layer 4: Gas Estimation & Caps
            if not await self._check_gas_limits(tx):
                return False

            # Security Layer 5: Approval Manager
            if not await self._get_approval(tx):
                return False

            # Security Layer 6: Final Confirmation
            if not self._get_user_confirmation():
                return False

            # Execute Transaction
            tx_hash = await self._execute_transaction(tx)
            if not tx_hash:
                return False

            # Wait for confirmation
            receipt = await self._wait_for_confirmation(tx_hash)
            if not receipt:
                return False

            self.metrics.finalize(success=True)
            print("\n✅ TRANSACTION SUCCESSFUL!")
            return True

        except Exception as e:
            logger.exception("Transaction execution failed")
            self.metrics.record_error(str(e), layer="execution")
            self.metrics.finalize(success=False)
            print(f"\n❌ TRANSACTION FAILED: {e}")
            return False

        finally:
            # Always save metrics
            self._save_metrics()

    async def _check_spending_limits(self) -> bool:
        """Security Layer 1: Check spending limits."""
        print("\n🔒 Security Layer 1: Spending Limits")
        print("-" * 80)

        try:
            # Get ETH price
            eth_price = await self.price_oracle.get_price("ETH")
            tx_value_usd = self.amount_eth * eth_price

            # Check transaction limit
            max_tx_usd = Decimal(str(self.config.max_transaction_value_usd))

            if tx_value_usd > max_tx_usd:
                self.metrics.record_security_layer(
                    "spending_limits",
                    False,
                    {
                        "tx_value_usd": str(tx_value_usd),
                        "max_tx_usd": str(max_tx_usd),
                        "reason": "Transaction exceeds maximum",
                    },
                )
                print(
                    f"❌ Transaction value ${tx_value_usd} exceeds max ${max_tx_usd}"
                )
                return False

            # Check daily limit
            can_spend, reason = self.spending_limit_mgr.can_spend(tx_value_usd)
            if not can_spend:
                self.metrics.record_security_layer(
                    "spending_limits",
                    False,
                    {"tx_value_usd": str(tx_value_usd), "reason": reason},
                )
                print(f"❌ Spending limit check failed: {reason}")
                return False

            self.metrics.record_security_layer(
                "spending_limits",
                True,
                {
                    "tx_value_usd": str(tx_value_usd),
                    "max_tx_usd": str(max_tx_usd),
                    "eth_price": str(eth_price),
                },
            )
            print(f"✅ Spending limits OK (${tx_value_usd:.2f} of ${max_tx_usd})")
            return True

        except Exception as e:
            self.metrics.record_error(str(e), layer="spending_limits")
            print(f"❌ Spending limit check error: {e}")
            return False

    def _build_transaction(self) -> Dict[str, Any]:
        """Security Layer 2: Build transaction."""
        print("\n🔧 Security Layer 2: Build Transaction")
        print("-" * 80)

        try:
            tx = self.weth.build_wrap_transaction(self.wallet_address, self.amount_eth)

            self.metrics.record_security_layer(
                "build_transaction",
                True,
                {
                    "to": tx["to"],
                    "value": tx["value"],
                    "gas": tx["gas"],
                    "gas_price": tx["gasPrice"],
                },
            )
            print(f"✅ Transaction built successfully")
            print(f"   To: {tx['to']}")
            print(f"   Value: {tx['value']} wei")
            print(f"   Gas: {tx['gas']}")
            return tx

        except Exception as e:
            self.metrics.record_error(str(e), layer="build_transaction")
            print(f"❌ Transaction build error: {e}")
            return None

    async def _simulate_transaction(self, tx: Dict[str, Any]) -> bool:
        """Security Layer 3: Simulate transaction."""
        print("\n🧪 Security Layer 3: Simulation")
        print("-" * 80)

        try:
            # Use TransactionBuilder to simulate
            tx_builder = TransactionBuilder(self.w3, self.network)
            success, result = tx_builder.simulate_transaction(tx)

            if not success:
                self.metrics.record_security_layer(
                    "simulation", False, {"reason": result}
                )
                print(f"❌ Simulation failed: {result}")
                return False

            self.metrics.record_security_layer(
                "simulation", True, {"result": "Transaction will succeed"}
            )
            print(f"✅ Simulation passed")
            return True

        except Exception as e:
            self.metrics.record_error(str(e), layer="simulation")
            print(f"❌ Simulation error: {e}")
            return False

    async def _check_gas_limits(self, tx: Dict[str, Any]) -> bool:
        """Security Layer 4: Check gas limits and estimate."""
        print("\n⛽ Security Layer 4: Gas Limits")
        print("-" * 80)

        try:
            # Get current gas price
            gas_price_wei = tx["gasPrice"]
            gas_price_gwei = Decimal(gas_price_wei) / Decimal(10**9)
            max_gas_gwei = Decimal(str(self.config.max_gas_price_gwei))

            # Check gas price cap
            if gas_price_gwei > max_gas_gwei:
                self.metrics.record_security_layer(
                    "gas_limits",
                    False,
                    {
                        "gas_price_gwei": str(gas_price_gwei),
                        "max_gas_gwei": str(max_gas_gwei),
                    },
                )
                print(
                    f"❌ Gas price {gas_price_gwei} Gwei exceeds max {max_gas_gwei} Gwei"
                )
                return False

            # Estimate gas using TransactionBuilder
            tx_builder = TransactionBuilder(self.w3, self.network)
            gas_estimate = tx_builder.estimate_gas(tx)

            # Calculate total cost
            total_cost_wei = gas_estimate * gas_price_wei
            total_cost_eth = Decimal(total_cost_wei) / Decimal(10**18)

            self.metrics.record_security_layer(
                "gas_limits",
                True,
                {
                    "gas_price_gwei": str(gas_price_gwei),
                    "max_gas_gwei": str(max_gas_gwei),
                    "gas_estimate": gas_estimate,
                    "total_cost_eth": str(total_cost_eth),
                },
            )

            self.metrics.record_gas_metrics(
                {
                    "gas_price_gwei": str(gas_price_gwei),
                    "gas_estimate": gas_estimate,
                    "gas_limit": tx["gas"],
                    "total_cost_eth": str(total_cost_eth),
                }
            )

            print(f"✅ Gas limits OK")
            print(f"   Price: {gas_price_gwei:.2f} Gwei (max {max_gas_gwei})")
            print(f"   Estimate: {gas_estimate} gas")
            print(f"   Total cost: {total_cost_eth:.6f} ETH")
            return True

        except Exception as e:
            self.metrics.record_error(str(e), layer="gas_limits")
            print(f"❌ Gas limit check error: {e}")
            return False

    async def _get_approval(self, tx: Dict[str, Any]) -> bool:
        """Security Layer 5: Get approval from approval manager."""
        print("\n👤 Security Layer 5: Approval Manager")
        print("-" * 80)

        try:
            # Get ETH price for USD value
            eth_price = await self.price_oracle.get_price("ETH")
            tx_value_usd = self.amount_eth * eth_price

            # Submit for approval
            print(f"Submitting transaction for approval (${tx_value_usd:.2f})...")

            approval_start = time.time()
            approved = await self.approval_mgr.request_approval(
                transaction_type="weth_wrap",
                amount_usd=tx_value_usd,
                details={
                    "amount_eth": str(self.amount_eth),
                    "to": tx["to"],
                    "gas": tx["gas"],
                },
            )
            approval_duration = time.time() - approval_start

            if not approved:
                self.metrics.record_security_layer(
                    "approval_manager",
                    False,
                    {
                        "tx_value_usd": str(tx_value_usd),
                        "approval_threshold_usd": str(
                            self.config.approval_threshold_usd
                        ),
                        "duration_seconds": approval_duration,
                    },
                )
                print(f"❌ Approval denied")
                return False

            self.metrics.record_security_layer(
                "approval_manager",
                True,
                {
                    "tx_value_usd": str(tx_value_usd),
                    "approval_threshold_usd": str(self.config.approval_threshold_usd),
                    "duration_seconds": approval_duration,
                },
            )
            print(
                f"✅ Approval granted ({approval_duration:.2f}s via event-driven system)"
            )
            return True

        except Exception as e:
            self.metrics.record_error(str(e), layer="approval_manager")
            print(f"❌ Approval error: {e}")
            return False

    def _get_user_confirmation(self) -> bool:
        """Security Layer 6: Final user confirmation."""
        print("\n✋ Security Layer 6: Final Confirmation")
        print("-" * 80)

        if self.config.environment == "production":
            response = input("Type 'CONFIRM' to execute transaction: ")
            confirmed = response.strip() == "CONFIRM"
        else:
            # Auto-confirm in development
            print("Auto-confirming in development mode")
            confirmed = True

        self.metrics.record_security_layer(
            "user_confirmation", confirmed, {"environment": self.config.environment}
        )

        if confirmed:
            print("✅ User confirmed")
        else:
            print("❌ User cancelled")

        return confirmed

    async def _execute_transaction(self, tx: Dict[str, Any]) -> str:
        """Execute the transaction."""
        print("\n🚀 Executing Transaction")
        print("-" * 80)

        try:
            # Use TransactionBuilder to send transaction
            tx_builder = TransactionBuilder(self.w3, self.network)
            tx_hash = tx_builder.send_transaction(tx)
            print(f"✅ Transaction sent: {tx_hash.hex()}")
            return tx_hash.hex()

        except Exception as e:
            self.metrics.record_error(str(e), layer="execution")
            print(f"❌ Execution error: {e}")
            return None

    async def _wait_for_confirmation(self, tx_hash: str) -> Dict[str, Any]:
        """Wait for transaction confirmation."""
        print("\n⏳ Waiting for Confirmation")
        print("-" * 80)

        try:
            print(f"Waiting for transaction {tx_hash}...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)

            if receipt["status"] == 1:
                print(f"✅ Transaction confirmed in block {receipt['blockNumber']}")
                self.metrics.record_execution(tx_hash, receipt)
                return receipt
            else:
                print(f"❌ Transaction failed (status={receipt['status']})")
                self.metrics.record_error("Transaction reverted", layer="confirmation")
                return None

        except Exception as e:
            self.metrics.record_error(str(e), layer="confirmation")
            print(f"❌ Confirmation error: {e}")
            return None

    def _save_metrics(self):
        """Save metrics to files."""
        print("\n📊 Saving Metrics")
        print("-" * 80)

        # Create metrics directory
        metrics_dir = Path(__file__).parent.parent / "metrics"
        metrics_dir.mkdir(exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = metrics_dir / f"first_transaction_{timestamp}.json"
        md_file = metrics_dir / f"first_transaction_{timestamp}.md"

        # Save both formats
        self.metrics.save_json(json_file)
        self.metrics.save_markdown(md_file)

        print(f"✅ Metrics saved:")
        print(f"   JSON: {json_file}")
        print(f"   Markdown: {md_file}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Execute first test transaction: ETH → WETH wrap"
    )
    parser.add_argument(
        "--amount", type=str, default="0.001", help="Amount of ETH to wrap"
    )
    args = parser.parse_args()

    amount = Decimal(args.amount)

    executor = FirstTransactionExecutor(amount_eth=amount)
    success = await executor.execute()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
