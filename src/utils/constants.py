"""Protocol contract addresses and constants.

This module contains all contract addresses for protocols across different networks.
"""

from typing import Dict

# Uniswap V3 Contract Addresses
UNISWAP_V3_ADDRESSES: Dict[str, Dict[str, str]] = {
    "base-sepolia": {
        "universal_router": "0x492E6456D9528771018DeB9E87ef7750EF184104",
        "swap_router_02": "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4",
        "factory": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24",
        "quoter_v2": "0xC5290058841028F1614F3A6F0F5816cAd0df5E27",
        "weth": "0x4200000000000000000000000000000000000006",
    },
    "base-mainnet": {
        "universal_router": "0x6fF5693b99212Da76ad316178A184AB56D299b43",
        "swap_router_02": "0x2626664c2603336E57B271c5C0b26F421741e481",
        "factory": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
        "quoter_v2": "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
        "weth": "0x4200000000000000000000000000000000000006",
    },
}

# Common ERC20 Token Addresses
TOKEN_ADDRESSES: Dict[str, Dict[str, str]] = {
    "base-sepolia": {
        "WETH": "0x4200000000000000000000000000000000000006",
        "USDC": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Base Sepolia USDC
    },
    "base-mainnet": {
        "WETH": "0x4200000000000000000000000000000000000006",
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # Native USDC
    },
}

# Uniswap V3 Fee Tiers (in basis points)
UNISWAP_V3_FEE_TIERS = {
    "lowest": 100,      # 0.01% - for stablecoin pairs
    "low": 500,         # 0.05% - for stable pairs
    "medium": 3000,     # 0.3% - most common for volatile pairs
    "high": 10000,      # 1% - for exotic pairs
}

# Default fee tier for different token pair types
DEFAULT_FEE_TIERS = {
    "stable": 100,      # Stablecoin pairs (USDC/USDT)
    "weth_stable": 500, # ETH/Stablecoin pairs (ETH/USDC)
    "volatile": 3000,   # Normal volatile pairs (ETH/tokens)
    "exotic": 10000,    # Exotic or low liquidity pairs
}
