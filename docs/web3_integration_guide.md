# Web3 Integration Guide

**MAMMON DeFi Yield Optimizer**
**Phase**: 1C Sprint 3
**Version**: 1.0
**Date**: 2025-11-06

---

## Overview

MAMMON's Web3 infrastructure provides multi-network blockchain connectivity for querying DeFi protocols on Base and Arbitrum networks. This guide covers usage, best practices, and current limitations.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Supported Networks](#supported-networks)
3. [Core Features](#core-features)
4. [Usage Examples](#usage-examples)
5. [Best Practices](#best-practices)
6. [Current Limitations](#current-limitations)
7. [Phase 2A Improvements](#phase-2a-improvements)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Basic Connection

```python
from src.utils.web3_provider import get_web3

# Connect to Base mainnet
w3 = get_web3("base-mainnet")

# Check connection
if w3.is_connected():
    block = w3.eth.block_number
    print(f"Connected! Latest block: {block}")
```

### Query Token Balance

```python
from src.tokens import ERC20Token

# USDC on Base mainnet
usdc = ERC20Token("base-mainnet", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

# Get metadata (cached after first call)
symbol = usdc.get_symbol()     # "USDC"
decimals = usdc.get_decimals() # 6

# Get balance
balance = usdc.get_balance_formatted("0xYourAddress")
print(f"Balance: {balance:,.2f} {symbol}")
```

### Query Protocol Data

```python
from src.protocols.aerodrome import AerodromeProtocol

# Initialize protocol
protocol = AerodromeProtocol({
    "network": "base-mainnet",
    "dry_run_mode": False  # Query real data
})

# Get real pools from Base mainnet
pools = await protocol.get_pools()
print(f"Found {len(pools)} Aerodrome pools")

for pool in pools:
    print(f"{pool.name}: ${pool.tvl:,.0f} TVL, {pool.apy}% APY")
```

---

## Supported Networks

### Production Networks

#### Base Mainnet
- **Network ID**: `base-mainnet`
- **Chain ID**: 8453
- **RPC URL**: `https://mainnet.base.org/` (public)
- **Explorer**: https://basescan.org/
- **Status**: ✅ Active
- **Rate Limits**: ~10-15 requests/minute (public RPC)

### Testnet Networks

#### Base Sepolia
- **Network ID**: `base-sepolia`
- **Chain ID**: 84532
- **RPC URL**: `https://sepolia.base.org/`
- **Explorer**: https://sepolia.basescan.org/
- **Status**: ✅ Active (mock data only)

#### Arbitrum Sepolia
- **Network ID**: `arbitrum-sepolia`
- **Chain ID**: 421614
- **RPC URL**: `https://sepolia-rollup.arbitrum.io/rpc`
- **Explorer**: https://sepolia.arbiscan.io/
- **Status**: ✅ Active (testing only)

---

## Core Features

### 1. Connection Management

#### Automatic Connection Caching
```python
# First call creates connection
w3_1 = get_web3("base-mainnet")  # Creates new connection

# Subsequent calls reuse cached connection
w3_2 = get_web3("base-mainnet")  # Returns cached connection

# Same instance
assert w3_1 is w3_2  # True
```

#### Custom RPC URLs
```python
# Use custom/premium RPC endpoint
w3 = get_web3("base-mainnet", custom_rpc_url="https://base.llamarpc.com")
```

#### Connection Health Checks
```python
from src.utils.web3_provider import check_network_health

health = check_network_health("base-mainnet")
print(f"Connected: {health['connected']}")
print(f"Block: {health['block_number']}")
print(f"Gas Price: {health['gas_price_gwei']:.2f} gwei")
```

### 2. Retry Logic

Automatic retry with exponential backoff:
```python
# Configured automatically
max_retries = 3
backoff_schedule = [1s, 2s, 4s]

# Handles transient failures gracefully
w3 = get_web3("base-mainnet")  # Retries up to 3 times
```

### 3. PoA Middleware

Automatically injected for Base networks:
```python
# Handles extraData field in block headers
# Required for Proof-of-Authority chains like Base
# Injected automatically - no action needed
```

### 4. Network Verification

Automatic chain ID validation:
```python
# Verifies chain ID matches expected network
w3 = get_web3("base-mainnet")
# Raises ConnectionError if chain ID != 8453
```

---

## Usage Examples

### Example 1: Query Multiple Networks

```python
from src.utils.web3_provider import get_web3

networks = ["base-mainnet", "arbitrum-sepolia"]

for network_id in networks:
    w3 = get_web3(network_id)
    block = w3.eth.block_number
    chain_id = w3.eth.chain_id
    print(f"{network_id}: Block {block}, Chain ID {chain_id}")
```

### Example 2: Token Metadata Caching

```python
from src.tokens import ERC20Token

# Create token instance
weth = ERC20Token("base-mainnet", "0x4200000000000000000000000000000000000006")

# First call queries blockchain
symbol = weth.get_symbol()  # RPC call

# Subsequent calls use cached value
symbol_2 = weth.get_symbol()  # Instant (cached)
```

### Example 3: Contract Interactions

```python
from src.utils.web3_provider import get_web3
from src.utils.contracts import ContractHelper, ERC20_ABI

w3 = get_web3("base-mainnet")

# Create contract instance
usdc_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
usdc = ContractHelper.get_erc20_contract(w3, usdc_address)

# Call contract methods
total_supply = usdc.functions.totalSupply().call()
print(f"USDC Total Supply: {total_supply / 10**6:,.0f}")
```

### Example 4: Pool Queries with Error Handling

```python
from src.protocols.aerodrome import AerodromeProtocol
from src.utils.logger import get_logger

logger = get_logger(__name__)

protocol = AerodromeProtocol({
    "network": "base-mainnet",
    "dry_run_mode": False
})

try:
    # Fetch limited number of pools to avoid rate limits
    pools = await protocol._get_real_pools_from_mainnet(max_pools=5)

    for pool in pools:
        logger.info(f"Pool: {pool.name}")
        logger.info(f"  TVL: ${pool.tvl:,.0f}")
        logger.info(f"  Tokens: {', '.join(pool.tokens)}")

except Exception as e:
    logger.error(f"Failed to fetch pools: {e}")
    # Fallback to mock data
    pools = await protocol.get_pools()  # Returns mock data
```

---

## Best Practices

### 1. Connection Management

✅ **DO**: Reuse Web3 instances via caching
```python
w3 = get_web3("base-mainnet")  # Cached automatically
```

❌ **DON'T**: Create multiple instances for same network
```python
for i in range(100):
    w3 = Web3(HTTPProvider(rpc_url))  # Creates 100 connections!
```

### 2. Rate Limiting

✅ **DO**: Limit bulk queries to avoid rate limits
```python
pools = await protocol._get_real_pools_from_mainnet(max_pools=10)
```

❌ **DON'T**: Query all pools at once on public RPC
```python
pools = await protocol._get_real_pools_from_mainnet(max_pools=14049)  # Timeout!
```

### 3. Metadata Caching

✅ **DO**: Use ERC20Token class for automatic caching
```python
token = ERC20Token(network, address)
symbol = token.get_symbol()  # Cached after first call
```

❌ **DON'T**: Query metadata repeatedly
```python
for i in range(100):
    symbol = contract.functions.symbol().call()  # 100 RPC calls!
```

### 4. Error Handling

✅ **DO**: Handle connection errors gracefully
```python
try:
    w3 = get_web3("base-mainnet")
except ConnectionError as e:
    logger.error(f"Connection failed: {e}")
    # Use fallback or mock data
```

❌ **DON'T**: Let exceptions bubble up
```python
w3 = get_web3("base-mainnet")  # May crash if RPC down
```

### 5. TVL Usage

✅ **DO**: Use TVL for relative comparisons only
```python
# Sort pools by relative TVL
pools_sorted = sorted(pools, key=lambda p: p.tvl, reverse=True)
```

❌ **DON'T**: Use TVL for financial calculations
```python
# WRONG - TVL is approximate ($1/token assumption)
risk_score = position_value / pool.tvl  # Inaccurate!
```

---

## Current Limitations

### 1. RPC Rate Limiting (Base Mainnet)

**Issue**: Public Base RPC limits ~10-15 requests/minute

**Impact**:
- Cannot query >10 pools at once
- Balance queries may timeout
- Dashboard refresh rates limited

**Workaround**:
```python
# Limit queries
pools = await protocol._get_real_pools_from_mainnet(max_pools=5)

# Add delays between queries
import time
for pool in pool_addresses:
    data = query_pool(pool)
    time.sleep(0.5)  # 500ms delay
```

**Resolution**: Phase 2A will add premium RPC providers (see below)

### 2. No Request Batching

**Issue**: Each query is a separate RPC call

**Impact**:
- 3 RPC calls per token (symbol, decimals, balance)
- Slow for bulk operations
- Hits rate limits faster

**Workaround**:
```python
# Use ERC20Token caching
token = ERC20Token(network, address)
token.get_info()  # Returns all metadata with caching
```

**Resolution**: Phase 2A will implement request batching

### 3. Simplified TVL Calculation

**Issue**: TVL assumes $1 per token (inaccurate)

**Safeguards Implemented**:
- Enhanced docstring warnings
- Metadata flags: `tvl_is_estimate`, `tvl_method`, `tvl_warning`
- NOT used in calculations (display/filtering only)

**Resolution**: Phase 2A Chainlink price oracle integration

### 4. Single RPC Endpoint

**Issue**: No fallback if RPC endpoint fails

**Impact**:
- Single point of failure
- Downtime if RPC provider has issues

**Workaround**: Use custom RPC URL parameter

**Resolution**: Phase 2A RPC rotation/fallback

---

## Phase 2A Improvements

### 1. Premium RPC Providers

**Implementation**:
```python
RPC_PROVIDERS = {
    "base-mainnet": {
        "alchemy": "https://base-mainnet.g.alchemy.com/v2/{API_KEY}",
        "infura": "https://base-mainnet.infura.io/v3/{PROJECT_ID}",
        "quicknode": "https://YOUR-ENDPOINT.base.quiknode.pro/{TOKEN}/",
        "llamarpc": "https://base.llamarpc.com",  # Fallback
    }
}
```

**Benefits**:
- 100-300M requests/month (vs ~10k on public)
- Better reliability and SLA
- Higher rate limits
- WebSocket support for real-time updates

### 2. Request Batching

**Implementation**:
```python
# Current: 3 separate calls
symbol = token.functions.symbol().call()
decimals = token.functions.decimals().call()
balance = token.functions.balanceOf(addr).call()

# Phase 2A: 1 batched call
batch = w3.batch_requests([
    token.functions.symbol(),
    token.functions.decimals(),
    token.functions.balanceOf(addr),
])
symbol, decimals, balance = batch.results()
```

**Benefits**:
- 60-70% reduction in RPC calls
- Faster bulk operations
- Lower rate limit impact

### 3. Connection Pooling

**Implementation**:
```python
connection_pool = ConnectionPool(
    max_connections=10,
    max_idle_time=300,  # 5 minutes
    health_check_interval=60,
)
```

**Benefits**:
- Reuse persistent connections
- Better performance for repeated queries
- Automatic connection health monitoring

### 4. RPC Rotation & Fallback

**Implementation**:
```python
def get_web3_with_fallback(network_id):
    endpoints = get_rpc_endpoints(network_id)

    for endpoint in endpoints:
        try:
            w3 = get_web3(network_id, custom_rpc_url=endpoint)
            if w3.is_connected():
                return w3
        except Exception as e:
            logger.warning(f"RPC {endpoint} failed: {e}")
            continue

    raise ConnectionError("All RPC endpoints failed")
```

**Benefits**:
- No single point of failure
- Automatic failover
- Better uptime

### 5. Chainlink Price Oracle

**Implementation**:
```python
from src.data.oracles import ChainlinkPriceOracle

oracle = ChainlinkPriceOracle("base-mainnet")
usdc_price = oracle.get_price("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
# Returns: Decimal("1.00")

# Update TVL calculation
tvl = (amount0 * price0) + (amount1 * price1)  # Accurate!
```

**Benefits**:
- Accurate TVL calculations
- Real-time price data
- Reliable, battle-tested oracles

---

## Troubleshooting

### Connection Timeout

**Error**: `ConnectionError: Failed to connect to base-mainnet`

**Causes**:
1. RPC endpoint down
2. Network connectivity issues
3. Firewall blocking requests

**Solutions**:
```python
# 1. Check network health
health = check_network_health("base-mainnet")
print(health)

# 2. Try custom RPC
w3 = get_web3("base-mainnet", custom_rpc_url="https://base.llamarpc.com")

# 3. Clear cache and retry
from src.utils.web3_provider import Web3Provider
Web3Provider.clear_cache("base-mainnet")
w3 = get_web3("base-mainnet")
```

### Rate Limiting (429 Error)

**Error**: `HTTPError: 429 Client Error: Too Many Requests`

**Cause**: Hit RPC rate limit (public Base RPC)

**Solutions**:
```python
# 1. Reduce query count
pools = await protocol._get_real_pools_from_mainnet(max_pools=5)

# 2. Add delays
import time
time.sleep(0.5)  # Between queries

# 3. Use custom RPC with higher limits
w3 = get_web3("base-mainnet", custom_rpc_url="YOUR_PREMIUM_RPC")
```

### Chain ID Mismatch

**Error**: `Chain ID mismatch: expected 8453, got 1`

**Cause**: Connected to wrong network (e.g., Ethereum mainnet instead of Base)

**Solution**:
```python
# Verify RPC URL is correct for network
network = get_network("base-mainnet")
print(f"Expected RPC: {network.rpc_url}")
print(f"Expected Chain ID: {network.chain_id}")
```

### PoA Middleware Error

**Error**: `ExtraDataLengthError: The field extraData is 97 bytes, but should be 32`

**Cause**: Missing PoA middleware for Base network

**Solution**: Middleware is injected automatically. If error persists:
```python
from web3.middleware import ExtraDataToPOAMiddleware

w3 = get_web3("base-mainnet")
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
```

---

## API Reference

### Functions

#### `get_web3(network_id: str, custom_rpc_url: Optional[str] = None) -> Web3`
Get or create a Web3 instance for the specified network.

**Parameters**:
- `network_id`: Network identifier (e.g., "base-mainnet")
- `custom_rpc_url`: Optional custom RPC URL

**Returns**: Configured Web3 instance

**Raises**: `ValueError` if network not supported, `ConnectionError` if connection fails

---

#### `check_network_health(network_id: str) -> Dict`
Check network connection health.

**Parameters**:
- `network_id`: Network identifier

**Returns**: Dict with health status information
```python
{
    "network_id": "base-mainnet",
    "connected": True,
    "chain_id": 8453,
    "block_number": 37779276,
    "gas_price_gwei": 0.05,
    "rpc_url": "https://mainnet.base.org/"
}
```

---

### Classes

#### `ERC20Token(network_id: str, token_address: str)`
ERC20 token interaction utility with automatic caching.

**Methods**:
- `get_symbol() -> str`: Get token symbol (cached)
- `get_decimals() -> int`: Get token decimals (cached)
- `get_name() -> str`: Get token name (cached)
- `get_balance(address: str) -> int`: Get raw balance
- `get_balance_formatted(address: str) -> Decimal`: Get formatted balance
- `get_info() -> Dict`: Get all metadata

---

## Additional Resources

- **Web3.py Docs**: https://web3py.readthedocs.io/
- **Base Network**: https://docs.base.org/
- **Alchemy**: https://www.alchemy.com/
- **Infura**: https://www.infura.io/
- **Chainlink Oracles**: https://docs.chain.link/

---

**Guide Version**: 1.0
**Last Updated**: 2025-11-06
**Next Update**: Phase 2A (Premium RPC implementation)
