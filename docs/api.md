# MAMMON API Documentation

## Overview

This document describes the internal APIs and interfaces used within MAMMON.

## Protocol Interface

All protocol integrations must implement `BaseProtocol` from `src/protocols/base.py`.

### Required Methods

```python
async def get_pools() -> List[ProtocolPool]:
    """Fetch all available pools/vaults."""

async def get_pool_apy(pool_id: str) -> Decimal:
    """Get current APY for a pool."""

async def deposit(pool_id: str, token: str, amount: Decimal) -> str:
    """Deposit tokens into pool."""

async def withdraw(pool_id: str, token: str, amount: Decimal) -> str:
    """Withdraw tokens from pool."""

async def get_user_balance(pool_id: str, user_address: str) -> Decimal:
    """Get user's balance in pool."""

async def estimate_gas(operation: str, params: Dict) -> int:
    """Estimate gas cost."""
```

## Strategy Interface

All strategies must implement `BaseStrategy` from `src/strategies/base_strategy.py`.

### Required Methods

```python
async def analyze_opportunities(
    current_positions: Dict[str, Decimal],
    available_yields: Dict[str, Decimal],
) -> List[RebalanceRecommendation]:
    """Analyze and recommend rebalances."""

def calculate_optimal_allocation(
    total_capital: Decimal,
    opportunities: Dict[str, Decimal],
) -> Dict[str, Decimal]:
    """Calculate optimal capital allocation."""

def should_rebalance(
    current_apy: Decimal,
    target_apy: Decimal,
    gas_cost: Decimal,
    amount: Decimal,
) -> bool:
    """Determine if rebalancing is worthwhile."""
```

## Database Models

See `src/data/models.py` for complete schema documentation.

## Configuration

Configuration is managed via `src/utils/config.py` using Pydantic.

### Environment Variables

```bash
# Blockchain
CDP_API_KEY=...
CDP_API_SECRET=...
WALLET_SEED=...
BASE_RPC_URL=...

# AI
ANTHROPIC_API_KEY=...

# Limits
MAX_TRANSACTION_VALUE_USD=1000
DAILY_SPENDING_LIMIT_USD=5000
APPROVAL_THRESHOLD_USD=100

# Environment
ENVIRONMENT=development
LOG_LEVEL=INFO
```

## Logging

Use structured logging from `src/utils/logger.py`.

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("Operation completed", extra={"tx_hash": "0x..."})
```

## Validation

All external inputs should be validated using `src/utils/validators.py`.

```python
from src.utils.validators import validate_ethereum_address, validate_amount

address = validate_ethereum_address(user_input)
amount = validate_amount(user_amount, min_value=Decimal("0.01"))
```

## Error Handling

Always use explicit error handling:

```python
from src.utils.validators import ValidationError

try:
    amount = validate_amount(input_amount)
except ValidationError as e:
    logger.error(f"Validation failed: {e}")
    return error_response
```

## Testing

Write tests using pytest:

```python
import pytest
from src.utils.validators import validate_amount, ValidationError

def test_validate_amount_positive():
    result = validate_amount(Decimal("100"))
    assert result == Decimal("100")

def test_validate_amount_negative():
    with pytest.raises(ValidationError):
        validate_amount(Decimal("-10"))
```

## Future API (x402)

### Service Discovery

```python
services = await client.discover_services(category="yield_data")
```

### Service Call

```python
result = await client.call_service(
    service_id="premium_yield_data",
    params={"token": "USDC"},
)
```

### Service Registration

```python
await server.register_endpoint(ServiceEndpoint(
    endpoint_id="mammon_strategy",
    name="MAMMON Yield Strategy",
    price=Decimal("0.01"),
    handler=strategy_handler,
))
```
