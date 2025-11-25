"""Uniswap V3 Quoter integration for getting swap quotes.

This module interfaces with Uniswap V3's QuoterV2 contract to get
accurate quotes for swaps without executing them.
"""

from decimal import Decimal
from typing import Dict, Optional
from web3 import Web3
from web3.contract import Contract

from src.utils.constants import UNISWAP_V3_ADDRESSES, TOKEN_ADDRESSES
from src.utils.logger import get_logger

logger = get_logger(__name__)

# QuoterV2 ABI (only the methods we need)
QUOTER_V2_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "quoteExactInputSingle",
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "quoteExactOutputSingle",
        "outputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# ERC20 ABI for decimals
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    }
]


class UniswapV3Quote:
    """Represents a Uniswap V3 swap quote.

    Attributes:
        amount_in: Input amount (raw units)
        amount_out: Output amount (raw units)
        amount_in_formatted: Input amount (decimal)
        amount_out_formatted: Output amount (decimal)
        price: Effective price (output per input)
        price_impact_bps: Price impact in basis points
        gas_estimate: Estimated gas units
        sqrt_price_x96_after: Pool price after swap
        ticks_crossed: Number of initialized ticks crossed
    """

    def __init__(
        self,
        amount_in: int,
        amount_out: int,
        amount_in_formatted: Decimal,
        amount_out_formatted: Decimal,
        price: Decimal,
        price_impact_bps: int,
        gas_estimate: int,
        sqrt_price_x96_after: int,
        ticks_crossed: int,
    ):
        self.amount_in = amount_in
        self.amount_out = amount_out
        self.amount_in_formatted = amount_in_formatted
        self.amount_out_formatted = amount_out_formatted
        self.price = price
        self.price_impact_bps = price_impact_bps
        self.gas_estimate = gas_estimate
        self.sqrt_price_x96_after = sqrt_price_x96_after
        self.ticks_crossed = ticks_crossed


class UniswapV3Quoter:
    """Uniswap V3 quoter for getting swap quotes.

    Interfaces with QuoterV2 contract to get accurate quotes
    for token swaps on Uniswap V3.

    Attributes:
        w3: Web3 instance
        network: Network identifier
        quoter: QuoterV2 contract instance
    """

    def __init__(self, w3: Web3, network: str):
        """Initialize UniswapV3Quoter.

        Args:
            w3: Web3 instance
            network: Network identifier (e.g., "base-sepolia")
        """
        self.w3 = w3
        self.network = network

        # Get quoter address
        if network not in UNISWAP_V3_ADDRESSES:
            raise ValueError(f"Uniswap V3 not supported on {network}")

        quoter_address = UNISWAP_V3_ADDRESSES[network]["quoter_v2"]
        self.quoter = self.w3.eth.contract(
            address=Web3.to_checksum_address(quoter_address),
            abi=QUOTER_V2_ABI,
        )

        logger.info(
            f"Initialized UniswapV3Quoter on {network}",
            extra={"quoter_address": quoter_address},
        )

    def _get_token_decimals(self, token_address: str) -> int:
        """Get token decimals.

        Args:
            token_address: Token contract address

        Returns:
            Number of decimals
        """
        token = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )
        return token.functions.decimals().call()

    async def quote_exact_input(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        fee_tier: int = 3000,
        sqrt_price_limit_x96: int = 0,
    ) -> Optional[UniswapV3Quote]:
        """Get quote for exact input swap.

        Args:
            token_in: Input token address or symbol
            token_out: Output token address or symbol
            amount_in: Input amount (in token units, e.g., 0.001 ETH)
            fee_tier: Fee tier (500 = 0.05%, 3000 = 0.3%, 10000 = 1%)
            sqrt_price_limit_x96: Price limit (0 = no limit)

        Returns:
            UniswapV3Quote or None if quote fails
        """
        try:
            # Resolve token addresses
            token_addresses = TOKEN_ADDRESSES[self.network]

            if token_in.upper() in token_addresses:
                token_in_address = token_addresses[token_in.upper()]
            else:
                token_in_address = token_in

            if token_out.upper() in token_addresses:
                token_out_address = token_addresses[token_out.upper()]
            else:
                token_out_address = token_out

            # Get decimals
            token_in_decimals = self._get_token_decimals(token_in_address)
            token_out_decimals = self._get_token_decimals(token_out_address)

            # Convert amount to raw units
            amount_in_raw = int(amount_in * Decimal(10**token_in_decimals))

            # Call quoter
            logger.debug(
                f"Getting quote: {amount_in} {token_in} → {token_out} "
                f"(fee: {fee_tier/10000}%)"
            )

            result = self.quoter.functions.quoteExactInputSingle(
                (
                    Web3.to_checksum_address(token_in_address),
                    Web3.to_checksum_address(token_out_address),
                    amount_in_raw,
                    fee_tier,
                    sqrt_price_limit_x96,
                )
            ).call()

            amount_out_raw = result[0]
            sqrt_price_x96_after = result[1]
            ticks_crossed = result[2]
            gas_estimate = result[3]

            # Format amounts
            amount_out_formatted = Decimal(amount_out_raw) / Decimal(
                10**token_out_decimals
            )

            # Calculate effective price
            price = amount_out_formatted / amount_in

            # Estimate price impact (simplified - actual calculation would use pool state)
            # For now, we'll calculate it when we have oracle price to compare
            price_impact_bps = 0

            quote = UniswapV3Quote(
                amount_in=amount_in_raw,
                amount_out=amount_out_raw,
                amount_in_formatted=amount_in,
                amount_out_formatted=amount_out_formatted,
                price=price,
                price_impact_bps=price_impact_bps,
                gas_estimate=gas_estimate,
                sqrt_price_x96_after=sqrt_price_x96_after,
                ticks_crossed=ticks_crossed,
            )

            logger.info(
                f"Quote: {amount_in} {token_in} → {amount_out_formatted:.6f} {token_out} "
                f"(price: {price:.2f}, gas: {gas_estimate})"
            )

            return quote

        except Exception as e:
            logger.error(f"Failed to get quote: {e}")
            return None

    async def quote_exact_output(
        self,
        token_in: str,
        token_out: str,
        amount_out: Decimal,
        fee_tier: int = 3000,
        sqrt_price_limit_x96: int = 0,
    ) -> Optional[UniswapV3Quote]:
        """Get quote for exact output swap.

        Args:
            token_in: Input token address or symbol
            token_out: Output token address or symbol
            amount_out: Desired output amount (in token units)
            fee_tier: Fee tier (500 = 0.05%, 3000 = 0.3%, 10000 = 1%)
            sqrt_price_limit_x96: Price limit (0 = no limit)

        Returns:
            UniswapV3Quote or None if quote fails
        """
        try:
            # Resolve token addresses
            token_addresses = TOKEN_ADDRESSES[self.network]

            if token_in.upper() in token_addresses:
                token_in_address = token_addresses[token_in.upper()]
            else:
                token_in_address = token_in

            if token_out.upper() in token_addresses:
                token_out_address = token_addresses[token_out.upper()]
            else:
                token_out_address = token_out

            # Get decimals
            token_in_decimals = self._get_token_decimals(token_in_address)
            token_out_decimals = self._get_token_decimals(token_out_address)

            # Convert amount to raw units
            amount_out_raw = int(amount_out * Decimal(10**token_out_decimals))

            # Call quoter
            logger.debug(
                f"Getting quote for exact output: ? {token_in} → {amount_out} {token_out} "
                f"(fee: {fee_tier/10000}%)"
            )

            result = self.quoter.functions.quoteExactOutputSingle(
                (
                    Web3.to_checksum_address(token_in_address),
                    Web3.to_checksum_address(token_out_address),
                    amount_out_raw,
                    fee_tier,
                    sqrt_price_limit_x96,
                )
            ).call()

            amount_in_raw = result[0]
            sqrt_price_x96_after = result[1]
            ticks_crossed = result[2]
            gas_estimate = result[3]

            # Format amounts
            amount_in_formatted = Decimal(amount_in_raw) / Decimal(
                10**token_in_decimals
            )

            # Calculate effective price
            price = amount_out / amount_in_formatted

            # Price impact placeholder
            price_impact_bps = 0

            quote = UniswapV3Quote(
                amount_in=amount_in_raw,
                amount_out=amount_out_raw,
                amount_in_formatted=amount_in_formatted,
                amount_out_formatted=amount_out,
                price=price,
                price_impact_bps=price_impact_bps,
                gas_estimate=gas_estimate,
                sqrt_price_x96_after=sqrt_price_x96_after,
                ticks_crossed=ticks_crossed,
            )

            logger.info(
                f"Quote: {amount_in_formatted:.6f} {token_in} → {amount_out} {token_out} "
                f"(price: {price:.2f}, gas: {gas_estimate})"
            )

            return quote

        except Exception as e:
            logger.error(f"Failed to get quote: {e}")
            return None

    def calculate_price_impact(
        self, quote: UniswapV3Quote, oracle_price: Decimal
    ) -> Decimal:
        """Calculate price impact compared to oracle price.

        Args:
            quote: Uniswap quote
            oracle_price: Oracle price (e.g., from Chainlink)

        Returns:
            Price impact as percentage (e.g., 0.5 for 0.5%)
        """
        # Price impact = (execution_price - oracle_price) / oracle_price * 100
        deviation = abs(quote.price - oracle_price) / oracle_price * Decimal(100)

        logger.debug(
            f"Price impact: {deviation:.4f}% "
            f"(Uniswap: {quote.price:.2f}, Oracle: {oracle_price:.2f})"
        )

        return deviation
