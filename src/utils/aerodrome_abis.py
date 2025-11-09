"""Aerodrome Finance contract ABIs.

Contains ABI definitions for Aerodrome contracts:
- PoolFactory: For discovering and querying pools
- Pool: For querying pool data (reserves, prices, fees)
"""

# Aerodrome PoolFactory ABI (minimal interface for querying)
AERODROME_FACTORY_ABI = [
    {
        "inputs": [],
        "name": "allPoolsLength",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "name": "allPools",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "name": "isPool",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "bool", "name": "stable", "type": "bool"},
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "_pool", "type": "address"},
            {"internalType": "bool", "name": "_stable", "type": "bool"},
        ],
        "name": "getFee",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Aerodrome Pool ABI (minimal interface for querying pool data)
AERODROME_POOL_ABI = [
    # Token information
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
        "name": "tokens",
        "outputs": [
            {"internalType": "address", "name": "", "type": "address"},
            {"internalType": "address", "name": "", "type": "address"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "stable",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    # Reserves
    {
        "inputs": [],
        "name": "reserve0",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "reserve1",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint256", "name": "_reserve0", "type": "uint256"},
            {"internalType": "uint256", "name": "_reserve1", "type": "uint256"},
            {"internalType": "uint256", "name": "_blockTimestampLast", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # Metadata
    {
        "inputs": [],
        "name": "metadata",
        "outputs": [
            {"internalType": "uint256", "name": "dec0", "type": "uint256"},
            {"internalType": "uint256", "name": "dec1", "type": "uint256"},
            {"internalType": "uint256", "name": "r0", "type": "uint256"},
            {"internalType": "uint256", "name": "r1", "type": "uint256"},
            {"internalType": "bool", "name": "st", "type": "bool"},
            {"internalType": "address", "name": "t0", "type": "address"},
            {"internalType": "address", "name": "t1", "type": "address"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # Pricing
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
        ],
        "name": "getAmountOut",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "granularity", "type": "uint256"},
        ],
        "name": "quote",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # Fee indexes
    {
        "inputs": [],
        "name": "index0",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "index1",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # Total supply (LP tokens)
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # Name and symbol
    {
        "inputs": [],
        "name": "name",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Router ABI (for reference, not currently needed for read-only queries)
AERODROME_ROUTER_ABI = [
    {
        "inputs": [],
        "name": "factory",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]
