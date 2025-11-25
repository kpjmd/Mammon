"""Uniswap V3 Router integration for executing swaps.

This module interfaces with Uniswap V3's Universal Router to execute
token swaps on-chain.
"""

from decimal import Decimal
from typing import Dict, Any, Optional
from web3 import Web3
from web3.contract import Contract
import time

from src.utils.constants import UNISWAP_V3_ADDRESSES, TOKEN_ADDRESSES
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Universal Router ABI (simplified - only swap commands we need)
UNIVERSAL_ROUTER_ABI = [
    {
        "inputs": [
            {"name": "commands", "type": "bytes"},
            {"name": "inputs", "type": "bytes[]"},
            {"name": "deadline", "type": "uint256"},
        ],
        "name": "execute",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    }
]

# SwapRouter02 ABI (alternative, more explicit interface)
SWAP_ROUTER_02_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "recipient", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "amountOutMinimum", "type": "uint256"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "refundETH",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "amountMinimum", "type": "uint256"},
            {"name": "recipient", "type": "address"},
        ],
        "name": "sweepToken",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
]


class UniswapV3Router:
    """Uniswap V3 router for executing swaps.

    Interfaces with SwapRouter02 contract for executing token swaps.
    Uses SwapRouter02 instead of Universal Router for clearer interface.

    Attributes:
        w3: Web3 instance
        network: Network identifier
        router: SwapRouter02 contract instance
    """

    def __init__(self, w3: Web3, network: str):
        """Initialize UniswapV3Router.

        Args:
            w3: Web3 instance
            network: Network identifier (e.g., "base-sepolia")
        """
        self.w3 = w3
        self.network = network

        # Get router address (using SwapRouter02 for simplicity)
        if network not in UNISWAP_V3_ADDRESSES:
            raise ValueError(f"Uniswap V3 not supported on {network}")

        router_address = UNISWAP_V3_ADDRESSES[network]["swap_router_02"]
        self.router = self.w3.eth.contract(
            address=Web3.to_checksum_address(router_address),
            abi=SWAP_ROUTER_02_ABI,
        )

        logger.info(
            f"Initialized UniswapV3Router on {network}",
            extra={"router_address": router_address},
        )

    def build_exact_input_single_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        amount_out_minimum: int,
        recipient: str,
        fee_tier: int = 3000,
        deadline_seconds: int = 600,
        sqrt_price_limit_x96: int = 0,
    ) -> Dict[str, Any]:
        """Build exact input single swap transaction.

        Args:
            token_in: Input token address or symbol
            token_out: Output token address or symbol
            amount_in: Input amount (raw units)
            amount_out_minimum: Minimum output amount (raw units)
            recipient: Recipient address
            fee_tier: Fee tier (500 = 0.05%, 3000 = 0.3%)
            deadline_seconds: Deadline from now in seconds
            sqrt_price_limit_x96: Price limit (0 = no limit)

        Returns:
            Transaction dict ready for signing
        """
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

        # Calculate deadline
        deadline = int(time.time()) + deadline_seconds

        # Determine if this is an ETH swap (input is WETH)
        weth_address = TOKEN_ADDRESSES[self.network]["WETH"]
        is_eth_input = token_in_address.lower() == weth_address.lower()

        # Build swap params
        swap_params = (
            Web3.to_checksum_address(token_in_address),
            Web3.to_checksum_address(token_out_address),
            fee_tier,
            Web3.to_checksum_address(recipient),
            amount_in,
            amount_out_minimum,
            sqrt_price_limit_x96,
        )

        # Build transaction - use fixed gas to avoid estimation failure during approval
        tx_params = {
            "from": Web3.to_checksum_address(recipient),
            "gas": 300000,  # Fixed gas limit to avoid estimation during build
        }

        # If swapping native ETH, include value
        if is_eth_input:
            tx_params["value"] = amount_in

        try:
            # Build the transaction without gas estimation
            tx = self.router.functions.exactInputSingle(swap_params).build_transaction(
                tx_params
            )

            logger.info(
                f"Built swap transaction: {token_in} → {token_out}",
                extra={
                    "amount_in": amount_in,
                    "amount_out_minimum": amount_out_minimum,
                    "fee_tier": fee_tier,
                    "deadline": deadline,
                    "is_eth_input": is_eth_input,
                },
            )

            return tx

        except Exception as e:
            logger.error(f"Failed to build swap transaction: {e}")
            raise

    def estimate_swap_gas(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        amount_out_minimum: int,
        sender: str,
        fee_tier: int = 3000,
        sqrt_price_limit_x96: int = 0,
    ) -> int:
        """Estimate gas for swap.

        Args:
            token_in: Input token address or symbol
            token_out: Output token address or symbol
            amount_in: Input amount (raw units)
            amount_out_minimum: Minimum output amount (raw units)
            sender: Sender address
            fee_tier: Fee tier
            sqrt_price_limit_x96: Price limit

        Returns:
            Estimated gas units
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

            # Determine if this is an ETH swap
            weth_address = TOKEN_ADDRESSES[self.network]["WETH"]
            is_eth_input = token_in_address.lower() == weth_address.lower()

            # Build params
            swap_params = (
                Web3.to_checksum_address(token_in_address),
                Web3.to_checksum_address(token_out_address),
                fee_tier,
                Web3.to_checksum_address(sender),
                amount_in,
                amount_out_minimum,
                sqrt_price_limit_x96,
            )

            # Estimate gas
            tx_params = {
                "from": Web3.to_checksum_address(sender),
            }

            if is_eth_input:
                tx_params["value"] = amount_in

            gas_estimate = self.router.functions.exactInputSingle(
                swap_params
            ).estimate_gas(tx_params)

            logger.debug(
                f"Estimated swap gas: {gas_estimate}",
                extra={"token_in": token_in, "token_out": token_out},
            )

            return gas_estimate

        except Exception as e:
            logger.error(f"Failed to estimate swap gas: {e}")
            # Return conservative default for swap
            return 200000

    def encode_path(
        self, tokens: list[str], fees: list[int]
    ) -> bytes:
        """Encode V3 path for multi-hop swap.

        Args:
            tokens: List of token addresses (start to end)
            fees: List of fee tiers between tokens

        Returns:
            Encoded path bytes

        Example:
            # ETH -> USDC -> DAI
            path = encode_path(
                [weth_address, usdc_address, dai_address],
                [3000, 500]  # 0.3% for ETH/USDC, 0.05% for USDC/DAI
            )
        """
        if len(tokens) != len(fees) + 1:
            raise ValueError("Invalid path: len(tokens) must be len(fees) + 1")

        # Resolve addresses
        token_addresses = TOKEN_ADDRESSES[self.network]
        resolved_tokens = []

        for token in tokens:
            if token.upper() in token_addresses:
                resolved_tokens.append(token_addresses[token.upper()])
            else:
                resolved_tokens.append(token)

        # Encode path: token0 + fee0 + token1 + fee1 + token2
        path = b""
        for i, token in enumerate(resolved_tokens[:-1]):
            # Add token address (20 bytes)
            path += bytes.fromhex(token[2:].lower())
            # Add fee (3 bytes, big-endian)
            path += fees[i].to_bytes(3, byteorder="big")

        # Add last token
        path += bytes.fromhex(resolved_tokens[-1][2:].lower())

        logger.debug(
            f"Encoded path: {' -> '.join(tokens)} with fees {fees}",
            extra={"path_length": len(path)},
        )

        return path

    def calculate_deadline(self, seconds_from_now: int = 600) -> int:
        """Calculate transaction deadline.

        Args:
            seconds_from_now: Seconds from now (default: 10 minutes)

        Returns:
            Unix timestamp for deadline
        """
        deadline = int(time.time()) + seconds_from_now
        logger.debug(f"Calculated deadline: {deadline} ({seconds_from_now}s from now)")
        return deadline
