# Premium RPC Configuration Guide

**Sprint 4 Priority 2** - Implemented: 2025-11-11

## Overview

MAMMON now supports premium RPC providers with automatic fallback, circuit breaker protection, and gradual rollout capabilities. This dramatically improves reliability and reduces latency for production deployments.

## Quick Start

### 1. Sign Up for Premium RPC (Optional)

Premium RPC is **completely optional**. MAMMON works perfectly with public RPCs. However, premium providers offer:

- **Better reliability**: 99.9% uptime SLA
- **Lower latency**: < 100ms vs 200-500ms for public RPCs
- **Higher rate limits**: 100+ RPS vs 10 RPS for public
- **Better support**: Dedicated support teams

#### Alchemy (Primary Provider)

**Free Tier**: 300M compute units/month (plenty for testing)
**Paid**: $5/month pay-as-you-go (recommended for production)

1. Sign up at https://www.alchemy.com/
2. Create a new app for Base and Arbitrum networks
3. Copy your API key
4. Add to `.env`:
   ```bash
   ALCHEMY_API_KEY=your_api_key_here
   PREMIUM_RPC_ENABLED=true
   ```

#### QuickNode (Backup Provider)

**Free Tier**: 10M API credits/month
**Paid**: $9-299/month based on usage

1. Sign up at https://www.quicknode.com/
2. Create endpoints for Base and Arbitrum
3. Copy your endpoint URL
4. Add to `.env`:
   ```bash
   QUICKNODE_ENDPOINT=https://xxx.quiknode.pro/yyy/
   ```

### 2. Configure Gradual Rollout

Start with 10% of traffic on premium RPC to validate:

```bash
PREMIUM_RPC_ENABLED=true
PREMIUM_RPC_PERCENTAGE=10  # Start small!
```

Monitor for 24-48 hours, then increase:

```bash
PREMIUM_RPC_PERCENTAGE=30   # Week 1
PREMIUM_RPC_PERCENTAGE=60   # Week 2
PREMIUM_RPC_PERCENTAGE=100  # Week 3
```

### 3. Monitor Usage

Check daily usage reports in `audit.log`:

```bash
grep "rpc_usage_summary" audit.log | tail -1 | jq
```

Output example:
```json
{
  "event_type": "rpc_usage_summary",
  "period": "daily",
  "premium_requests": 1234,
  "backup_requests": 0,
  "public_requests": 111,
  "alchemy_usage_percent": 12.34,
  "approaching_limit": false,
  "in_free_tier": true,
  "estimated_cost_usd": 0.00
}
```

## Architecture

### Endpoint Priority

MAMMON tries endpoints in this order:

1. **Premium** (Alchemy) - If configured and gradual rollout allows
2. **Backup** (QuickNode) - If premium fails or unavailable
3. **Public** - Always available as final fallback

### Circuit Breaker Pattern

Prevents hammering failed endpoints:

- **Closed**: Normal operation, requests allowed
- **Open**: Too many failures (default: 3), requests blocked for 60s
- **Half-Open**: Testing recovery after timeout

### Rate Limiting

Each endpoint tracks requests per second/minute:

- **Alchemy**: 100 RPS (default, adjust based on plan)
- **QuickNode**: 25 RPS (free tier limit)
- **Public**: 10 RPS (conservative estimate)

If limit reached, automatically tries next endpoint.

## Configuration Reference

### Required (Only If Using Premium RPC)

```bash
# Enable premium RPC
PREMIUM_RPC_ENABLED=true

# At least one premium provider
ALCHEMY_API_KEY=your_key_here
# OR
QUICKNODE_ENDPOINT=https://xxx.quiknode.pro/yyy/
```

### Optional Tuning

```bash
# Gradual rollout (0-100)
PREMIUM_RPC_PERCENTAGE=10

# Rate limits (requests per second)
ALCHEMY_RATE_LIMIT_PER_SECOND=100
QUICKNODE_RATE_LIMIT_PER_SECOND=25
PUBLIC_RATE_LIMIT_PER_SECOND=10

# Circuit breaker
RPC_FAILURE_THRESHOLD=3    # Failures before open
RPC_RECOVERY_TIMEOUT=60    # Seconds before retry

# Health checks
RPC_HEALTH_CHECK_INTERVAL=60  # Seconds between checks
```

## Cost Monitoring

### Free Tier Limits

**Alchemy Free Tier**:
- 300M compute units/month
- ~10M per day
- Sufficient for moderate usage

**QuickNode Free Tier**:
- 10M API credits/month
- ~333K per day
- Good for backup/testing

### Usage Calculation

MAMMON tracks usage and warns when approaching limits:

```python
# Check current usage
from src.utils.web3_provider import get_rpc_usage_summary
from src.utils.config import get_settings

summary = get_rpc_usage_summary(get_settings())
print(f"Today: {summary['premium_requests']} requests")
print(f"Usage: {summary['alchemy_usage_percent']:.1f}%")
print(f"Approaching limit: {summary['approaching_limit']}")
```

### Cost Estimates

Based on typical DeFi agent usage (1000 requests/day):

| Scenario | Alchemy | QuickNode | Total/Month |
|----------|---------|-----------|-------------|
| Free tier only | $0 | $0 | $0 |
| Light usage (< 10K/day) | $0 | $0 | $0 |
| Moderate (10-50K/day) | $5 | $0 | $5/month |
| Heavy (50K+/day) | $5-20 | $9 | $14-29/month |

## Security Considerations

### API Key Protection

**CRITICAL**: Never commit API keys to git!

```bash
# ✅ CORRECT
ALCHEMY_API_KEY=abc123def456  # In .env (gitignored)

# ❌ NEVER DO THIS
ALCHEMY_API_KEY=abc123def456  # In code
```

### URL Sanitization

MAMMON automatically sanitizes RPC URLs in logs:

```python
# Full URL (contains API key)
url = "https://base-mainnet.g.alchemy.com/v2/abc123def456"

# Logged as (API key hidden)
logged = "https://base-mainnet.g.alchemy.com/v2/***"
```

### Audit Logging

All RPC requests are logged (without API keys):

```json
{
  "event_type": "rpc_request",
  "endpoint": "alchemy",     // Provider name only!
  "network": "base-mainnet",
  "method": "eth_call",
  "latency_ms": 45.2,
  "success": true
}
```

## Troubleshooting

### Premium RPC Not Being Used

Check configuration:

```python
poetry run python -c "
from src.utils.config import get_settings
config = get_settings()
print(f'Premium enabled: {config.premium_rpc_enabled}')
print(f'Alchemy key set: {bool(config.alchemy_api_key)}')
print(f'Rollout: {config.premium_rpc_percentage}%')
"
```

Common issues:
1. `PREMIUM_RPC_ENABLED=false` in `.env`
2. `ALCHEMY_API_KEY` not set or invalid
3. `PREMIUM_RPC_PERCENTAGE=0` (no traffic routed)

### High Latency

Check RPC endpoint health:

```bash
grep "rpc_request" audit.log | grep "latency_ms" | tail -20
```

If latency > 200ms consistently:
1. Try different RPC region
2. Check network connection
3. Verify API key is valid

### Rate Limit Errors

Increase rate limits or reduce request frequency:

```bash
# If hitting Alchemy limits
ALCHEMY_RATE_LIMIT_PER_SECOND=50  # Reduce from 100

# Or upgrade your plan
```

### Circuit Breaker Constantly Opening

Check audit logs for endpoint failures:

```bash
grep "rpc_circuit_breaker_opened" audit.log
```

Possible causes:
1. Invalid API key
2. Network connectivity issues
3. Rate limiting from provider
4. Provider outage

## Performance Testing

Test RPC performance before full rollout:

```bash
# Run performance tests (Phase 5)
poetry run python scripts/test_rpc_performance.py

# Expected results:
# - Latency < 100ms (p95) for premium
# - Latency < 200ms (p95) for public
# - Success rate > 99.9%
# - Failover < 500ms
```

## Integration Examples

### Using Premium RPC in Code

```python
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings

# Get settings
config = get_settings()

# Get Web3 with premium RPC support
w3 = get_web3("base-mainnet", config=config)

# Use normally
block = w3.eth.block_number
print(f"Latest block: {block}")
```

### Monitoring Usage

```python
from src.utils.web3_provider import get_rpc_usage_summary
from src.utils.config import get_settings

# Get daily summary
summary = get_rpc_usage_summary(get_settings())

# Check if approaching limits
if summary['approaching_limit']:
    print("⚠️  Approaching RPC limit!")
    print(f"Usage: {summary['alchemy_usage_percent']:.1f}%")
```

### Forcing Public RPC

```python
# Disable premium RPC temporarily
w3 = get_web3("base-mainnet")  # No config = public RPC only

# Or use custom RPC
w3 = get_web3("base-mainnet", custom_rpc_url="https://my-rpc.com")
```

## Migration Path

### From Public to Premium

1. **Week 0**: Set up accounts, get API keys
2. **Week 1**: Enable at 10%, monitor costs
3. **Week 2**: Increase to 30-50%
4. **Week 3**: Full 100% if stable
5. **Week 4**: Remove public fallback (optional)

### Rollback Plan

If issues arise, instantly disable premium:

```bash
# In .env
PREMIUM_RPC_ENABLED=false
```

Or reduce rollout:

```bash
PREMIUM_RPC_PERCENTAGE=0  # Route all to public
```

No code changes required!

## Best Practices

1. **Start Small**: 10% rollout for first week
2. **Monitor Daily**: Check usage summaries
3. **Set Alerts**: Alert when > 80% of free tier
4. **Test Failover**: Simulate endpoint failures
5. **Review Costs**: Monthly cost analysis
6. **Keep Public Fallback**: Always have backup
7. **Rotate Keys**: Periodically rotate API keys
8. **Document Limits**: Track rate limit changes

## Support

- **Alchemy Support**: https://www.alchemy.com/support
- **QuickNode Support**: https://www.quicknode.com/contact
- **MAMMON Issues**: https://github.com/kpjmd/Mammon/issues

## Changelog

- **2025-11-11**: Initial implementation (Sprint 4 Priority 2)
  - Alchemy + QuickNode support
  - Circuit breaker pattern
  - Gradual rollout
  - Cost tracking
  - Security hardening (URL sanitization)
