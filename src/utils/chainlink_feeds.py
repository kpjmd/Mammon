"""Chainlink price feed registry for multi-network support.

This module provides Chainlink price feed contract addresses and utilities
for querying real-time price data across multiple EVM networks.

Architecture:
- Base Mainnet: Primary price source (reliable, well-tested feeds)
- Arbitrum Sepolia: Testnet execution environment
- Cross-network reads: Query Base prices for use in Arbitrum context
"""

from typing import Dict, Optional
from decimal import Decimal

# Chainlink Aggregator V3 Interface ABI
# Source: https://docs.chain.link/data-feeds/price-feeds/addresses
AGGREGATOR_V3_ABI = [
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "description",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"internalType": "uint80", "name": "roundId", "type": "uint80"},
            {"internalType": "int256", "name": "answer", "type": "int256"},
            {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
            {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
            {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint80", "name": "_roundId", "type": "uint80"}],
        "name": "getRoundData",
        "outputs": [
            {"internalType": "uint80", "name": "roundId", "type": "uint80"},
            {"internalType": "int256", "name": "answer", "type": "int256"},
            {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
            {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
            {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

# Chainlink Price Feed Addresses by Network
# Format: {network_id: {pair: address}}
PRICE_FEEDS: Dict[str, Dict[str, str]] = {
    # Base Mainnet - Primary price source
    # Source: https://docs.chain.link/data-feeds/price-feeds/addresses?network=base
    "base-mainnet": {
        "ETH/USD": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "USDC/USD": "0x7e860098F58bBFC8648a4311b374B1D669a2bc6B",
        "USDT/USD": "0xf19d560eB8d2ADf07BD6D13ed03e1D11215721F9",
        "DAI/USD": "0x591e79239a7d679378eC8c847e5038150364C78F",
        "BTC/USD": "0x64c911996D3c6aC71f9b455B1E8E7266BcbD848F",
        # AERO price feed (if available - TBD, may need to calculate from pools)
        # "AERO/USD": "",  # TODO: Research if Chainlink has AERO feed
    },
    # Arbitrum Sepolia - Testnet execution environment
    # Source: https://docs.chain.link/data-feeds/price-feeds/addresses?network=arbitrum-sepolia
    "arbitrum-sepolia": {
        "ETH/USD": "0xd30e2101a97dcbAeBCBC04F14C3f624E67A35165",
        "USDC/USD": "0x0153002d20B96532C639313c2d54c3dA09109309",
        "USDT/USD": "0x80EDee6f667eCc9f63a0a6f55578F870651f06A4",
        "BTC/USD": "0x56a43EB56Da12C0dc1D972ACb089c06a5dEF8e69",
        # Note: Limited feeds on testnet - may fall back to Base mainnet prices
    },
    # Base Sepolia - Testnet for Base L2
    # Source: https://docs.chain.link/data-feeds/price-feeds/addresses?network=base-sepolia
    # Note: Base Sepolia has limited price feeds available.
    # Common pattern is to use ETH/USD feed at 0x4aDC67696bA383F43DD60A9e78F2C97Fbbfc7cb1
    # Other feeds may not be available on testnet - use Base Mainnet for testing
    "base-sepolia": {
        "ETH/USD": "0x4aDC67696bA383F43DD60A9e78F2C97Fbbfc7cb1",
        # Note: USDC/USD and other feeds typically not available on Base Sepolia
        # Will fallback to mock oracle or Base mainnet prices
    },
}

# Token symbol mappings for price feed resolution
# Maps alternative token symbols to canonical Chainlink feed symbols
TOKEN_SYMBOL_MAPPINGS: Dict[str, str] = {
    # Wrapped tokens use underlying asset price
    "WETH": "ETH",
    "WBTC": "BTC",
    # Bridged/alternative stablecoins
    "USDC.e": "USDC",  # Bridged USDC on some chains
    "USDbC": "USDC",  # USD Base Coin (Coinbase-issued on Base)
    "DAI.e": "DAI",
    "USDT.e": "USDT",
}


def get_feed_address(network_id: str, token_symbol: str, quote: str = "USD") -> Optional[str]:
    """Get Chainlink price feed address for a token pair.

    Args:
        network_id: Network identifier (e.g., "base-mainnet")
        token_symbol: Token symbol (e.g., "ETH", "WETH")
        quote: Quote currency (default: "USD")

    Returns:
        Feed contract address, or None if not found

    Example:
        >>> get_feed_address("base-mainnet", "ETH", "USD")
        '0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70'
        >>> get_feed_address("base-mainnet", "WETH", "USD")  # Maps to ETH
        '0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70'
    """
    # Normalize token symbol
    token_symbol = token_symbol.upper()

    # Check if token needs mapping (e.g., WETH -> ETH)
    if token_symbol in TOKEN_SYMBOL_MAPPINGS:
        canonical_symbol = TOKEN_SYMBOL_MAPPINGS[token_symbol]
    else:
        canonical_symbol = token_symbol

    # Build feed pair key
    pair = f"{canonical_symbol}/{quote.upper()}"

    # Look up feed address
    if network_id in PRICE_FEEDS:
        return PRICE_FEEDS[network_id].get(pair)
    return None


def get_supported_tokens(network_id: str, quote: str = "USD") -> list[str]:
    """Get list of tokens with available price feeds on a network.

    Args:
        network_id: Network identifier
        quote: Quote currency (default: "USD")

    Returns:
        List of supported token symbols

    Example:
        >>> get_supported_tokens("base-mainnet")
        ['ETH', 'USDC', 'USDT', 'DAI', 'BTC']
    """
    if network_id not in PRICE_FEEDS:
        return []

    feeds = PRICE_FEEDS[network_id]
    quote_suffix = f"/{quote.upper()}"

    # Extract base tokens from pair strings
    tokens = [
        pair.split("/")[0]
        for pair in feeds.keys()
        if pair.endswith(quote_suffix)
    ]

    return sorted(tokens)


def get_canonical_symbol(token_symbol: str) -> str:
    """Get canonical token symbol for price feed lookup.

    Maps wrapped/alternative tokens to their canonical symbols.

    Args:
        token_symbol: Original token symbol

    Returns:
        Canonical symbol for price feed lookup

    Example:
        >>> get_canonical_symbol("WETH")
        'ETH'
        >>> get_canonical_symbol("ETH")
        'ETH'
        >>> get_canonical_symbol("USDC.e")
        'USDC'
    """
    token_symbol = token_symbol.upper()
    return TOKEN_SYMBOL_MAPPINGS.get(token_symbol, token_symbol)


def is_feed_available(network_id: str, token_symbol: str, quote: str = "USD") -> bool:
    """Check if a price feed is available for a token on a network.

    Args:
        network_id: Network identifier
        token_symbol: Token symbol
        quote: Quote currency (default: "USD")

    Returns:
        True if feed exists, False otherwise

    Example:
        >>> is_feed_available("base-mainnet", "ETH")
        True
        >>> is_feed_available("base-mainnet", "UNKNOWN")
        False
    """
    return get_feed_address(network_id, token_symbol, quote) is not None


def get_all_networks() -> list[str]:
    """Get list of all networks with Chainlink feeds configured.

    Returns:
        List of network identifiers

    Example:
        >>> get_all_networks()
        ['arbitrum-sepolia', 'base-mainnet']
    """
    return sorted(PRICE_FEEDS.keys())
