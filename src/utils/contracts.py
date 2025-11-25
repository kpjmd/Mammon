"""Contract utilities for ABI management and contract interactions.

Provides utilities for:
- Common ERC20 ABI definitions
- Contract instance creation
- Standard contract call patterns
"""

from typing import Any, Dict, List, Optional
from web3 import Web3
from web3.contract import Contract
from eth_typing import Address, ChecksumAddress
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Standard ERC20 ABI (minimal interface for common operations)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_from", "type": "address"},
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transferFrom",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]

# Uniswap V3 Factory ABI (minimal)
UNISWAP_V3_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Uniswap V3 Pool ABI (minimal)
UNISWAP_V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

# Uniswap V3 Universal Router ABI (minimal - for ETH->Token swaps)
# Handles native ETH without WETH wrapping
UNISWAP_V3_UNIVERSAL_ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "bytes", "name": "commands", "type": "bytes"},
            {"internalType": "bytes[]", "name": "inputs", "type": "bytes[]"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        ],
        "name": "execute",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes", "name": "commands", "type": "bytes"},
            {"internalType": "bytes[]", "name": "inputs", "type": "bytes[]"},
        ],
        "name": "execute",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
]

# Uniswap V3 SwapRouter02 ABI (alternative to Universal Router)
UNISWAP_V3_SWAP_ROUTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "internalType": "struct ISwapRouter.ExactInputSingleParams",
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function",
    },
]


class ContractHelper:
    """Helper class for contract interactions."""

    @staticmethod
    def get_contract(w3: Web3, address: str, abi: List[Dict[str, Any]]) -> Contract:
        """Get a contract instance.

        Args:
            w3: Web3 instance
            address: Contract address (will be checksummed)
            abi: Contract ABI

        Returns:
            Contract instance

        Raises:
            ValueError: If address is invalid
        """
        try:
            # Convert to checksum address
            checksum_address = w3.to_checksum_address(address)
            contract = w3.eth.contract(address=checksum_address, abi=abi)
            logger.debug(f"Created contract instance at {checksum_address}")
            return contract
        except Exception as e:
            logger.error(f"Failed to create contract instance: {e}")
            raise ValueError(f"Invalid contract address {address}: {e}")

    @staticmethod
    def get_erc20_contract(w3: Web3, token_address: str) -> Contract:
        """Get an ERC20 token contract instance.

        Args:
            w3: Web3 instance
            token_address: Token contract address

        Returns:
            ERC20 contract instance
        """
        return ContractHelper.get_contract(w3, token_address, ERC20_ABI)

    @staticmethod
    async def safe_call(
        contract_function: Any, *args: Any, block_identifier: str = "latest", **kwargs: Any
    ) -> Any:
        """Safely call a contract function with error handling.

        Args:
            contract_function: Contract function to call
            *args: Function arguments
            block_identifier: Block to query (default: "latest")
            **kwargs: Additional function arguments

        Returns:
            Function result

        Raises:
            Exception: If call fails
        """
        try:
            result = contract_function(*args, **kwargs).call(block_identifier=block_identifier)
            return result
        except Exception as e:
            logger.error(f"Contract call failed: {e}")
            raise


# Common contract addresses (will be expanded as we integrate protocols)
COMMON_ADDRESSES = {
    # Base mainnet
    "base-mainnet": {
        "WETH": "0x4200000000000000000000000000000000000006",  # Base WETH
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
        "AERO": "0x940181a94A35A4569E4529a3CDfB74e38FD98631",  # AERO token
        "aerodrome_router": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
        "aerodrome_factory": "0x420DD381b31aEf6683db6B902084cB0FFECe40Da",  # Verified ✅
    },
    # Base Sepolia (Testnet) - Sprint 4 Priority 3
    "base-sepolia": {
        # Tokens
        "WETH": "0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14",  # ✅ VERIFIED
        "USDC": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # ✅ VERIFIED (Circle Official)

        # Uniswap V3 (Official Deployments)
        "uniswap_v3_universal_router": "0x5d08bB547e5A1B8C110d7967963A0e7914713E8D",  # ✅ VERIFIED
        "uniswap_v3_factory": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",  # ✅ VERIFIED
        "uniswap_v3_swap_router": "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4",  # ✅ VERIFIED (SwapRouter02)

        # Note: Universal Router handles native ETH, no WETH wrapping needed for ETH swaps
    },
    # Arbitrum Sepolia
    "arbitrum-sepolia": {
        "WETH": "0x980B62Da83eFf3D4576C647993b0c1D7faf17c73",  # WETH on Arb Sepolia (TBD)
        "USDC": "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",  # Circle USDC testnet (TBD)
    },
}


def get_token_address(network_id: str, token_symbol: str) -> Optional[str]:
    """Get token address for a given network.

    Args:
        network_id: Network identifier
        token_symbol: Token symbol (e.g., "WETH", "USDC")

    Returns:
        Token address if found, None otherwise
    """
    network_addresses = COMMON_ADDRESSES.get(network_id, {})
    address = network_addresses.get(token_symbol)

    if address:
        logger.debug(f"Found {token_symbol} address on {network_id}: {address}")
    else:
        logger.warning(f"{token_symbol} address not found for {network_id}")

    return address


def get_protocol_address(network_id: str, protocol_key: str) -> Optional[str]:
    """Get protocol contract address for a given network.

    Args:
        network_id: Network identifier
        protocol_key: Protocol contract key (e.g., "aerodrome_router")

    Returns:
        Contract address if found, None otherwise
    """
    network_addresses = COMMON_ADDRESSES.get(network_id, {})
    address = network_addresses.get(protocol_key)

    if address:
        logger.debug(f"Found {protocol_key} address on {network_id}: {address}")
    else:
        logger.warning(f"{protocol_key} address not found for {network_id}")

    return address
