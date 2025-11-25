"""Pre-flight validation script for first test transaction.

Validates all prerequisites before executing the ETH → WETH wrap:
- Wallet connectivity and balance
- RPC endpoint health
- WETH contract deployment
- Security layer configuration
- Gas price sanity

This is Refinement #1 from Sprint 3 planning.
"""

import sys
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.blockchain.wallet import WalletManager
from src.utils.web3_provider import get_web3
from src.protocols.weth import WETHProtocol, WETH_ADDRESSES
from src.security.limits import SpendingLimits
from src.security.approval import ApprovalManager
from src.data.oracles import create_price_oracle

logger = get_logger(__name__)


class PreFlightCheck:
    """Pre-flight validation for first transaction."""

    def __init__(self):
        self.config = get_settings()
        self.network = self.config.network
        self.checks_passed = []
        self.checks_failed = []
        self.warnings = []
        self.wallet = None

    async def run_all_checks(self) -> bool:
        """Run all pre-flight checks.

        Returns:
            True if all critical checks pass
        """
        print("=" * 80)
        print("MAMMON PRE-FLIGHT VALIDATION")
        print(f"Network: {self.network}")
        print("=" * 80)

        # Critical checks (must pass)
        critical_checks = [
            ("Configuration Loaded", self.check_config),
            ("RPC Endpoint Health", self.check_rpc),
            ("WETH Contract Deployed", self.check_weth_contract),
            ("Security Layers Configured", self.check_security_layers),
            ("Gas Price Reasonable", self.check_gas_price),
            ("Wallet Connectivity", self.check_wallet),
            ("Sufficient ETH Balance", self.check_eth_balance),
        ]

        # Warning checks (should pass but not critical)
        warning_checks = [
            ("Approval Manager Responsive", self.check_approval_manager),
            ("Spending Limits Configured", self.check_spending_limits),
        ]

        print("\n🔍 CRITICAL CHECKS:")
        print("-" * 80)

        for check_name, check_func in critical_checks:
            try:
                # Check if function is async
                import inspect
                if inspect.iscoroutinefunction(check_func):
                    result, message = await check_func()
                else:
                    result, message = check_func()

                if result:
                    print(f"✅ {check_name}: {message}")
                    self.checks_passed.append(check_name)
                else:
                    print(f"❌ {check_name}: {message}")
                    self.checks_failed.append(check_name)
            except Exception as e:
                print(f"❌ {check_name}: EXCEPTION - {e}")
                self.checks_failed.append(check_name)
                logger.exception(f"Pre-flight check failed: {check_name}")

        print("\n⚠️  WARNING CHECKS:")
        print("-" * 80)

        for check_name, check_func in warning_checks:
            try:
                # Check if function is async
                import inspect
                if inspect.iscoroutinefunction(check_func):
                    result, message = await check_func()
                else:
                    result, message = check_func()

                if result:
                    print(f"✅ {check_name}: {message}")
                    self.checks_passed.append(check_name)
                else:
                    print(f"⚠️  {check_name}: {message}")
                    self.warnings.append(check_name)
            except Exception as e:
                print(f"⚠️  {check_name}: EXCEPTION - {e}")
                self.warnings.append(check_name)

        # Summary
        print("\n" + "=" * 80)
        print("PRE-FLIGHT SUMMARY")
        print("=" * 80)
        print(f"✅ Passed: {len(self.checks_passed)}")
        print(f"❌ Failed: {len(self.checks_failed)}")
        print(f"⚠️  Warnings: {len(self.warnings)}")

        if self.checks_failed:
            print("\n❌ CRITICAL FAILURES - CANNOT PROCEED:")
            for check in self.checks_failed:
                print(f"  - {check}")
            print("\nFix these issues before executing first transaction.")
            return False
        elif self.warnings:
            print("\n⚠️  WARNINGS - REVIEW BEFORE PROCEEDING:")
            for check in self.warnings:
                print(f"  - {check}")
            print("\nConsider fixing warnings for optimal operation.")

        print("\n✅ ALL CRITICAL CHECKS PASSED - READY FOR EXECUTION")
        return True

    def check_config(self) -> tuple[bool, str]:
        """Validate configuration loaded."""
        if not self.config:
            return False, "Configuration not loaded"

        required_fields = [
            "network",
            "max_transaction_value_usd",
            "max_gas_price_gwei",
        ]

        for field in required_fields:
            if not hasattr(self.config, field):
                return False, f"Missing required config field: {field}"

        return True, f"Config loaded with {len(required_fields)} required fields"

    async def check_wallet(self) -> tuple[bool, str]:
        """Validate wallet connectivity."""
        try:
            # Initialize wallet manager
            oracle = create_price_oracle(
                "chainlink" if self.config.chainlink_enabled else "mock",
                network=self.network,
                price_network=self.config.chainlink_price_network if self.config.chainlink_enabled else None,
                fallback_to_mock=self.config.chainlink_fallback_to_mock if self.config.chainlink_enabled else True,
            )

            wallet_config = {
                "cdp_api_key": self.config.cdp_api_key,
                "cdp_api_secret": self.config.cdp_api_secret,
                "cdp_wallet_secret": self.config.cdp_wallet_secret,
                "network": self.network,
                "dry_run_mode": self.config.dry_run_mode,
                "max_transaction_value_usd": float(self.config.max_transaction_value_usd),
                "daily_spending_limit_usd": float(self.config.daily_spending_limit_usd),
                "approval_threshold_usd": float(self.config.approval_threshold_usd),
                "max_gas_price_gwei": float(self.config.max_gas_price_gwei),
            }

            self.wallet = WalletManager(
                config=wallet_config,
                price_oracle=oracle,
                approval_manager=None,
            )

            await self.wallet.initialize()

            if not self.wallet.address:
                return False, "Could not get wallet address"

            return True, f"Wallet connected: {self.wallet.address[:10]}...{self.wallet.address[-8:]}"
        except Exception as e:
            return False, f"Wallet error: {e}"

    def check_rpc(self) -> tuple[bool, str]:
        """Validate RPC endpoint health."""
        try:
            w3 = get_web3(self.network)
            if not w3.is_connected():
                return False, "RPC not connected"

            block_number = w3.eth.block_number
            if block_number == 0:
                return False, "RPC connected but no blocks"

            return True, f"RPC connected, latest block: {block_number}"
        except Exception as e:
            return False, f"RPC error: {e}"

    def check_weth_contract(self) -> tuple[bool, str]:
        """Validate WETH contract deployed."""
        try:
            if self.network not in WETH_ADDRESSES:
                return False, f"WETH not configured for {self.network}"

            weth_address = WETH_ADDRESSES[self.network]
            w3 = get_web3(self.network)

            # Check contract code exists
            code = w3.eth.get_code(w3.to_checksum_address(weth_address))
            if code == b"" or code == "0x":
                return False, f"No contract code at {weth_address}"

            # Try to instantiate WETH protocol
            weth = WETHProtocol(w3, self.network)

            return True, f"WETH contract deployed at {weth_address}"
        except Exception as e:
            return False, f"WETH contract error: {e}"

    def check_security_layers(self) -> tuple[bool, str]:
        """Validate security layers configured."""
        try:
            # Check spending limits
            if not hasattr(self.config, "max_transaction_value_usd"):
                return False, "Transaction value limit not configured"

            if not hasattr(self.config, "max_gas_price_gwei"):
                return False, "Gas price limit not configured"

            # Check approval threshold
            if not hasattr(self.config, "approval_threshold_usd"):
                return False, "Approval threshold not configured"

            limits = [
                f"Max TX: ${self.config.max_transaction_value_usd}",
                f"Max Gas: {self.config.max_gas_price_gwei} Gwei",
                f"Approval: ${self.config.approval_threshold_usd}",
            ]

            return True, f"Security configured ({', '.join(limits)})"
        except Exception as e:
            return False, f"Security config error: {e}"

    async def check_eth_balance(self) -> tuple[bool, str]:
        """Validate sufficient ETH balance for test transaction."""
        try:
            if not self.wallet:
                return False, "Wallet not initialized"

            balance = await self.wallet.get_balance("ETH")

            # Need at least 0.002 ETH (0.001 to wrap + gas)
            min_balance = Decimal("0.002")

            if balance < min_balance:
                return (
                    False,
                    f"Insufficient balance: {balance} ETH (need {min_balance})",
                )

            return True, f"Balance: {balance} ETH (sufficient)"
        except Exception as e:
            return False, f"Balance check error: {e}"

    def check_gas_price(self) -> tuple[bool, str]:
        """Validate gas price is reasonable."""
        try:
            w3 = get_web3(self.network)
            gas_price_wei = w3.eth.gas_price
            gas_price_gwei = Decimal(gas_price_wei) / Decimal(10**9)

            max_gas_gwei = Decimal(str(self.config.max_gas_price_gwei))

            if gas_price_gwei > max_gas_gwei:
                return (
                    False,
                    f"Gas too high: {gas_price_gwei} Gwei (max {max_gas_gwei})",
                )

            return True, f"Gas price: {gas_price_gwei:.2f} Gwei (acceptable)"
        except Exception as e:
            return False, f"Gas price check error: {e}"

    def check_approval_manager(self) -> tuple[bool, str]:
        """Validate approval manager responsive."""
        try:
            # Try to initialize approval manager
            approval_mgr = ApprovalManager(
                approval_threshold_usd=self.config.approval_threshold_usd
            )

            return True, "Approval manager initialized"
        except Exception as e:
            return False, f"Approval manager error: {e}"

    def check_spending_limits(self) -> tuple[bool, str]:
        """Validate spending limits configured."""
        try:
            # Try to initialize spending limit manager
            wallet_config = {
                "max_transaction_value_usd": self.config.max_transaction_value_usd,
                "daily_spending_limit_usd": self.config.daily_spending_limit_usd,
            }
            limit_mgr = SpendingLimits(wallet_config)

            return True, "Spending limit manager initialized"
        except Exception as e:
            return False, f"Spending limit error: {e}"


async def main():
    """Run pre-flight checks."""
    checker = PreFlightCheck()
    success = await checker.run_all_checks()

    if success:
        print("\n✅ Pre-flight complete - ready to execute first transaction")
        sys.exit(0)
    else:
        print("\n❌ Pre-flight failed - fix issues before proceeding")
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
