"""Swap executor with comprehensive security checks.

This module orchestrates the complete swap flow with all security layers:
- Price oracle cross-checking
- Slippage protection
- Gas estimation and limits
- Approval thresholds
- Transaction simulation
- Balance verification
"""

from decimal import Decimal
from typing import Dict, Any, Optional
from web3 import Web3

from src.blockchain.gas_estimator import GasEstimator
from src.blockchain.slippage_calculator import SlippageCalculator, PriceDeviationError
from src.blockchain.wallet import WalletManager
from src.data.oracles import PriceOracle, StalePriceError
from src.protocols.uniswap_v3_quoter import UniswapV3Quoter, UniswapV3Quote
from src.protocols.uniswap_v3_router import UniswapV3Router
from src.security.approval import ApprovalManager, ApprovalRequest
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SwapSecurityCheck:
    """Result of security checks before swap execution.

    Attributes:
        passed: Whether all checks passed
        checks: Dict of individual check results
        errors: List of error messages
    """

    def __init__(self):
        self.passed = True
        self.checks: Dict[str, bool] = {}
        self.errors: list[str] = []

    def add_check(self, name: str, passed: bool, error: str = ""):
        """Add a security check result."""
        self.checks[name] = passed
        if not passed:
            self.passed = False
            if error:
                self.errors.append(f"{name}: {error}")


class SwapExecutor:
    """Executes token swaps with comprehensive security checks.

    This orchestrator implements the complete swap flow:
    1. Get quote from Uniswap
    2. Get oracle price from Chainlink
    3. Cross-check prices
    4. Calculate slippage protection
    5. Estimate gas
    6. Check approval threshold
    7. Simulate transaction
    8. Execute (if approved and wallet_manager provided)
    9. Verify balances

    The SwapExecutor integrates with WalletManager to enable real on-chain
    transaction execution. If wallet_manager is not provided, the executor
    operates in dry-run mode, performing all validation steps except actual
    transaction submission.

    Transaction Execution Flow:
        - Dry-run mode (wallet_manager=None): Validates and simulates only
        - Real execution mode (wallet_manager provided): Signs and submits tx

    Attributes:
        w3: Web3 instance
        network: Network identifier
        quoter: Uniswap quoter
        router: Uniswap router
        gas_estimator: Gas estimator
        slippage_calc: Slippage calculator
        price_oracle: Price oracle
        approval_manager: Approval manager
        wallet_manager: Wallet manager for transaction signing (optional)
    """

    def __init__(
        self,
        w3: Web3,
        network: str,
        price_oracle: PriceOracle,
        approval_manager: ApprovalManager,
        wallet_manager: Optional[WalletManager] = None,
        default_slippage_bps: int = 50,
        max_price_deviation_percent: Decimal = Decimal("2.0"),
        deadline_seconds: int = 600,
    ):
        """Initialize swap executor.

        Args:
            w3: Web3 instance
            network: Network identifier
            price_oracle: Price oracle for price validation
            approval_manager: Approval manager for transaction approval
            wallet_manager: Wallet manager for transaction signing (optional)
            default_slippage_bps: Default slippage tolerance (50 = 0.5%)
            max_price_deviation_percent: Max DEX/oracle deviation (2.0 = 2%)
            deadline_seconds: Default deadline in seconds (600 = 10 minutes)
        """
        self.w3 = w3
        self.network = network
        self.price_oracle = price_oracle
        self.approval_manager = approval_manager
        self.wallet_manager = wallet_manager

        # Initialize components
        self.quoter = UniswapV3Quoter(w3, network)
        self.router = UniswapV3Router(w3, network)
        self.gas_estimator = GasEstimator(network, price_oracle)
        self.slippage_calc = SlippageCalculator(
            default_slippage_bps=default_slippage_bps,
            max_price_deviation_percent=max_price_deviation_percent,
        )

        self.default_slippage_bps = default_slippage_bps
        self.deadline_seconds = deadline_seconds

        logger.info(
            f"Initialized SwapExecutor on {network}",
            extra={
                "slippage_bps": default_slippage_bps,
                "max_deviation": float(max_price_deviation_percent),
                "deadline": deadline_seconds,
            },
        )

    async def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        from_address: str,
        recipient: Optional[str] = None,
        slippage_bps: Optional[int] = None,
        fee_tier: int = 3000,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Execute a token swap with full security checks.

        This method performs comprehensive validation and optional execution
        of a token swap through Uniswap V3. The execution behavior depends
        on the dry_run flag and wallet_manager availability.

        Execution Modes:
            1. Dry-run (dry_run=True): Validates all security checks and
               simulates the transaction, but does not execute on-chain.
               Returns: {success: True, executed: False, ...}

            2. Real execution (dry_run=False, wallet_manager provided):
               Performs all validations, simulates, then signs and submits
               the transaction on-chain using the WalletManager.
               Returns: {success: True, executed: True, tx_hash: "0x...", ...}

            3. Real execution without wallet (dry_run=False, wallet_manager=None):
               Performs all validations and simulations, but cannot execute
               because no wallet is available for signing.
               Returns: {success: True, executed: False, note: "Execution requires WalletManager"}

        Security Validation (8 steps):
            1. Get Uniswap quote from QuoterV2
            2. Get oracle price from Chainlink (or fallback)
            3. Cross-check DEX vs oracle price deviation
            4. Calculate slippage protection (minimum output)
            5. Estimate gas cost with full transaction data
            6. Check if approval threshold exceeded
            7. Simulate transaction with eth_call
            8. Execute (if not dry_run and wallet_manager available)

        Args:
            token_in: Input token symbol (e.g., "WETH", "ETH")
            token_out: Output token symbol (e.g., "USDC")
            amount_in: Amount to swap (in token units, e.g., 0.001 ETH)
            from_address: Sender address
            recipient: Recipient address (defaults to sender)
            slippage_bps: Slippage tolerance in basis points (None = use default 50)
            fee_tier: Uniswap fee tier (3000 = 0.3%, 500 = 0.05%, 10000 = 1%)
            dry_run: If True, simulate only (don't execute on-chain)

        Returns:
            Dict with swap results and security check details:
                {
                    "success": bool,              # Overall success
                    "executed": bool,             # Whether tx was executed on-chain
                    "tx_hash": str,               # Transaction hash (if executed)
                    "confirmations": int,         # Block confirmations (if executed)
                    "balance_change_eth": str,    # ETH balance change (if executed)
                    "quote": {...},               # Uniswap quote details
                    "oracle_price": Decimal,      # Oracle price
                    "price_impact": Decimal,      # Price impact %
                    "slippage": {...},            # Slippage protection details
                    "gas": {...},                 # Gas estimation details
                    "security_checks": {...},     # All security check results
                    "error": str,                 # Error message (if failed)
                }

        Raises:
            PriceDeviationError: If DEX vs oracle deviation exceeds tolerance
            StalePriceError: If oracle price is stale and strict mode enabled
            ValueError: If security checks fail critically

        Example:
            # Dry-run mode (validation only)
            result = await executor.execute_swap(
                token_in="WETH",
                token_out="USDC",
                amount_in=Decimal("0.001"),
                from_address=wallet_address,
                dry_run=True,
            )

            # Real execution (requires wallet_manager)
            result = await executor.execute_swap(
                token_in="WETH",
                token_out="USDC",
                amount_in=Decimal("0.001"),
                from_address=wallet_address,
                dry_run=False,
            )
            if result["executed"]:
                print(f"Swap executed! TX: {result['tx_hash']}")
        """
        if recipient is None:
            recipient = from_address

        slippage = slippage_bps if slippage_bps is not None else self.default_slippage_bps

        logger.info(
            f"{'[DRY RUN] ' if dry_run else ''}Executing swap: "
            f"{amount_in} {token_in} → {token_out}",
            extra={
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": str(amount_in),
                "slippage_bps": slippage,
                "fee_tier": fee_tier,
                "dry_run": dry_run,
            },
        )

        security = SwapSecurityCheck()
        result: Dict[str, Any] = {
            "success": False,
            "dry_run": dry_run,
            "security_checks": security,
        }

        try:
            # STEP 1: Get Uniswap quote
            logger.info("Step 1: Getting Uniswap quote...")
            quote = await self.quoter.quote_exact_input(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
                fee_tier=fee_tier,
            )

            if quote is None:
                security.add_check("uniswap_quote", False, "Failed to get quote")
                result["error"] = "Failed to get Uniswap quote"
                return result

            security.add_check("uniswap_quote", True)
            result["quote"] = {
                "amount_out": str(quote.amount_out_formatted),
                "price": str(quote.price),
                "gas_estimate": quote.gas_estimate,
            }

            logger.info(
                f"✅ Quote: {quote.amount_in_formatted} {token_in} → "
                f"{quote.amount_out_formatted} {token_out} "
                f"(price: {quote.price:.2f}, gas: {quote.gas_estimate})"
            )

            # STEP 2: Get oracle price
            logger.info("Step 2: Getting Chainlink oracle price...")

            try:
                # For ETH/USDC swap, get ETH/USD price
                if token_in.upper() in ["ETH", "WETH"]:
                    oracle_price = await self.price_oracle.get_price("ETH", "USD")
                elif token_out.upper() in ["ETH", "WETH"]:
                    # Inverse swap (USDC -> ETH)
                    oracle_price_usd_eth = await self.price_oracle.get_price("ETH", "USD")
                    oracle_price = Decimal(1) / oracle_price_usd_eth
                else:
                    # For other pairs, try to get price
                    oracle_price = await self.price_oracle.get_price(token_in, token_out)

                security.add_check("oracle_price", True)
                result["oracle_price"] = str(oracle_price)

                logger.info(f"✅ Oracle price: {oracle_price:.2f}")

            except StalePriceError as e:
                security.add_check("oracle_staleness", False, str(e))
                result["error"] = f"Stale oracle price: {e}"
                return result

            # STEP 3: Cross-check prices
            logger.info("Step 3: Cross-checking DEX vs Oracle price...")

            try:
                self.slippage_calc.validate_price_deviation(
                    dex_price=quote.price,
                    oracle_price=oracle_price,
                )
                security.add_check("price_deviation", True)

                # Calculate price impact
                price_impact = self.slippage_calc.calculate_price_impact(
                    amount_in=amount_in,
                    amount_out=quote.amount_out_formatted,
                    oracle_price=oracle_price,
                )
                result["price_impact"] = str(price_impact)

                logger.info(f"✅ Price check passed (impact: {price_impact:.4f}%)")

            except PriceDeviationError as e:
                security.add_check("price_deviation", False, str(e))
                result["error"] = f"Price deviation too high: {e}"
                return result

            # STEP 4: Calculate slippage protection
            logger.info("Step 4: Calculating slippage protection...")

            min_output = self.slippage_calc.calculate_min_output(
                expected_amount=quote.amount_out_formatted,
                slippage_bps=slippage,
            )

            # Convert to raw units (same decimals as quote)
            decimals_ratio = Decimal(quote.amount_out) / quote.amount_out_formatted
            min_output_raw = int(min_output * decimals_ratio)

            security.add_check("slippage_protection", True)
            result["slippage"] = {
                "tolerance_bps": slippage,
                "tolerance_percent": self.slippage_calc.format_slippage_bps(slippage),
                "expected_output": str(quote.amount_out_formatted),
                "min_output": str(min_output),
            }

            logger.info(
                f"✅ Slippage protection: min output = {min_output} "
                f"({slippage}bps = {self.slippage_calc.format_slippage_bps(slippage)})"
            )

            # STEP 5: Estimate gas
            logger.info("Step 5: Estimating gas cost...")

            # Build transaction first to get encoded data for accurate gas estimation
            temp_tx = self.router.build_exact_input_single_swap(
                token_in=token_in,
                token_out=token_out,
                amount_in=quote.amount_in,
                amount_out_minimum=min_output_raw,
                recipient=recipient,
                fee_tier=fee_tier,
                deadline_seconds=self.deadline_seconds,
            )

            # Estimate gas with actual transaction data
            gas_estimate = await self.gas_estimator.estimate_gas(
                to=self.router.router.address,
                value=quote.amount_in if token_in.upper() in ["ETH", "WETH"] else 0,
                data=temp_tx.get("data", "0x"),
                from_address=from_address,
            )

            gas_cost_usd = await self.gas_estimator.calculate_gas_cost(
                gas_limit=gas_estimate,
                in_usd=True,
            )

            security.add_check("gas_estimation", True)
            result["gas"] = {
                "estimate": gas_estimate,
                "cost_usd": str(gas_cost_usd),
            }

            logger.info(f"✅ Gas estimate: {gas_estimate} units (${gas_cost_usd:.2f})")

            # STEP 6: Check approval threshold
            logger.info("Step 6: Checking approval threshold...")

            # Calculate total cost in USD
            if token_in.upper() in ["ETH", "WETH"]:
                eth_price = await self.price_oracle.get_price("ETH", "USD")
                swap_value_usd = amount_in * eth_price
            else:
                # For other tokens, use quote output value
                swap_value_usd = quote.amount_out_formatted

            requires_approval = self.approval_manager.requires_approval(
                amount_usd=swap_value_usd,
                gas_cost_usd=gas_cost_usd,
            )

            result["approval"] = {
                "required": requires_approval,
                "swap_value_usd": str(swap_value_usd),
                "gas_cost_usd": str(gas_cost_usd),
                "total_cost_usd": str(swap_value_usd + gas_cost_usd),
            }

            if requires_approval:
                logger.info(
                    f"⚠️  Approval required: ${swap_value_usd + gas_cost_usd:.2f} "
                    f"(swap: ${swap_value_usd:.2f}, gas: ${gas_cost_usd:.2f})"
                )

                if not dry_run:
                    # Request approval
                    approval_request = await self.approval_manager.request_approval(
                        transaction_type=f"Uniswap V3 Swap ({token_in}→{token_out})",
                        amount_usd=swap_value_usd,
                        from_protocol="Wallet",
                        to_protocol="Uniswap V3",
                        rationale=f"Swap {amount_in} {token_in} for ~{quote.amount_out_formatted:.4f} {token_out}",
                        gas_estimate_wei=gas_estimate,
                        gas_cost_usd=gas_cost_usd,
                    )

                    # Wait for approval
                    approval_status = await self.approval_manager.wait_for_approval(
                        approval_request
                    )

                    if approval_status.value != "approved":
                        security.add_check("approval", False, f"Status: {approval_status.value}")
                        result["error"] = f"Swap not approved: {approval_status.value}"
                        return result

                    logger.info("✅ Swap approved by user")

            security.add_check("approval", True)

            # STEP 7: Simulate transaction
            logger.info("Step 7: Simulating transaction...")

            try:
                # Build transaction
                tx = self.router.build_exact_input_single_swap(
                    token_in=token_in,
                    token_out=token_out,
                    amount_in=quote.amount_in,
                    amount_out_minimum=min_output_raw,
                    recipient=recipient,
                    fee_tier=fee_tier,
                    deadline_seconds=self.deadline_seconds,
                )

                # Simulate with eth_call
                self.w3.eth.call(tx)

                security.add_check("simulation", True)
                result["transaction"] = {
                    "to": tx["to"],
                    "value": tx.get("value", 0),
                    "gas": tx.get("gas", gas_estimate),
                }

                logger.info("✅ Transaction simulation successful")

            except Exception as e:
                security.add_check("simulation", False, str(e))
                result["error"] = f"Transaction simulation failed: {e}"
                return result

            # STEP 8: Execute (if not dry run)
            if not dry_run:
                logger.info("Step 8: Executing swap...")

                # Check if wallet manager is available
                if not self.wallet_manager:
                    logger.warning(
                        "⚠️  Transaction execution not possible - "
                        "WalletManager not provided"
                    )
                    result["executed"] = False
                    result["note"] = "Execution requires WalletManager"
                else:
                    # Get balances before
                    balance_before = self.w3.eth.get_balance(from_address)

                    try:
                        # Execute the swap transaction
                        tx_result = await self.wallet_manager.execute_transaction(
                            to=tx["to"],
                            amount=Decimal(str(tx.get("value", 0))) / Decimal(10**18),  # Convert Wei to ETH
                            data=tx["data"],
                            token="ETH",
                            wait_for_confirmation=True,
                            confirmation_blocks=2,
                        )

                        logger.info(f"✅ Transaction sent: {tx_result['tx_hash']}")

                        # Wait for confirmation is handled by execute_transaction
                        if tx_result.get("confirmed"):
                            logger.info(f"✅ Transaction confirmed with {tx_result.get('confirmations', 0)} blocks")

                            # Verify balance changed
                            balance_after = self.w3.eth.get_balance(from_address)
                            balance_change = Decimal(balance_before - balance_after) / Decimal(10**18)

                            result["executed"] = True
                            result["tx_hash"] = tx_result["tx_hash"]
                            result["confirmations"] = tx_result.get("confirmations", 0)
                            result["balance_change_eth"] = str(balance_change)

                            logger.info(f"✅ Balance change verified: -{balance_change} ETH")
                        else:
                            logger.warning("Transaction sent but not yet confirmed")
                            result["executed"] = True
                            result["tx_hash"] = tx_result["tx_hash"]
                            result["note"] = "Transaction sent, awaiting confirmation"

                    except Exception as e:
                        logger.error(f"Transaction execution failed: {e}")
                        result["executed"] = False
                        result["error"] = f"Transaction execution failed: {e}"
                        return result

            else:
                logger.info("✅ Dry run complete - all security checks passed")
                result["executed"] = False

            # Mark as successful
            result["success"] = True
            security.add_check("overall", True)

            return result

        except Exception as e:
            logger.error(f"Swap execution failed: {e}", exc_info=True)
            security.add_check("overall", False, str(e))
            result["error"] = str(e)
            return result

    def get_security_summary(self, security: SwapSecurityCheck) -> str:
        """Get human-readable security check summary.

        Args:
            security: Security check results

        Returns:
            Formatted summary string
        """
        summary = "\n" + "=" * 60 + "\n"
        summary += "SECURITY CHECK SUMMARY\n"
        summary += "=" * 60 + "\n"

        for check_name, passed in security.checks.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            summary += f"{status}: {check_name}\n"

        if security.errors:
            summary += "\nERRORS:\n"
            for error in security.errors:
                summary += f"  ❌ {error}\n"

        summary += "=" * 60

        return summary
