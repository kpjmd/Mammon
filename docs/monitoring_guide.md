# Premium RPC Monitoring Guide

**For**: 24-48 hour monitoring period during gradual rollout
**Current Rollout**: 30% to premium RPC
**Goal**: Verify stability before increasing to 60-100%

---

## Quick Start

### Run Monitoring Script (Anytime)

```bash
poetry run python scripts/monitor_rpc_usage.py
```

This shows:
- ✅ Health status
- 📊 Current usage
- 📈 Request distribution
- ⚡ Performance metrics
- 🚨 Issues & alerts
- 💡 Recommendations

---

## Monitoring Schedule

### Hour 0 (Start): Baseline

**Actions**:
1. ✅ Enabled premium RPC at 30%
2. Run performance test
3. Note baseline metrics

```bash
# Performance test
poetry run python scripts/test_rpc_performance.py

# Save baseline
echo "Baseline: $(date)" >> monitoring_log.txt
poetry run python scripts/monitor_rpc_usage.py >> monitoring_log.txt
```

### Hour 6: First Check

**Actions**:
1. Check if RPC requests are being made
2. Verify premium endpoint is being used
3. Check for any errors

```bash
# Quick status check
poetry run python scripts/monitor_rpc_usage.py

# Check recent errors
grep -i "error\|fail" audit.log | tail -20
```

**Expected Results**:
- ✅ Some RPC requests logged
- ✅ ~30% going to premium endpoint
- ✅ No circuit breaker events
- ✅ Success rate > 99%

### Hour 24: Mid-Point Check

**Actions**:
1. Run full monitoring report
2. Run performance test
3. Check cost projections

```bash
# Full report
poetry run python scripts/monitor_rpc_usage.py

# Performance validation
poetry run python scripts/test_rpc_performance.py

# Check usage summaries
grep "rpc_usage_summary" audit.log | tail -5 | jq
```

**Expected Results**:
- ✅ Latency < 100ms (p95)
- ✅ Cost < 50% of free tier
- ✅ No circuit breaker events
- ✅ Success rate > 99.9%

### Hour 48: Final Decision

**Actions**:
1. Run complete monitoring report
2. Run performance test
3. Make rollout decision

```bash
# Complete assessment
poetry run python scripts/monitor_rpc_usage.py
poetry run python scripts/test_rpc_performance.py

# Generate report
echo "=== 48 Hour Report ===" >> monitoring_log.txt
date >> monitoring_log.txt
poetry run python scripts/monitor_rpc_usage.py >> monitoring_log.txt
```

**Decision Criteria**:

✅ **PROCEED TO 60%** if all of these are true:
- Latency < 100ms (p95)
- Cost < 50% of free tier
- No circuit breaker events
- Success rate > 99%
- No critical errors

⚠️ **STAY AT 30%** if:
- Approaching rate limits (>50% of free tier)
- Occasional errors but generally stable
- Need more time to assess

❌ **ROLLBACK TO 10%** if:
- Circuit breaker events occurring
- Success rate < 95%
- Critical errors
- Costs approaching free tier limit

---

## Manual Checks

### Check Latest Usage Summary

```bash
grep "rpc_usage_summary" audit.log | tail -1 | jq
```

**Look for**:
- `premium_requests`: Should be ~30% of total
- `alchemy_usage_percent`: Should be < 50%
- `approaching_limit`: Should be `false`
- `in_free_tier`: Should be `true`

### Check Recent RPC Requests

```bash
grep "rpc_request" audit.log | tail -20 | jq
```

**Look for**:
- `endpoint`: Should see mix of "alchemy" and "public"
- `success`: Should be `true` for most
- `latency_ms`: Should be < 100ms

### Check for Circuit Breaker Events

```bash
grep "rpc_circuit_breaker_opened" audit.log
```

**Expected**: Empty (no events)
**If found**: Investigate why endpoints are failing

### Check for Endpoint Failures

```bash
grep "rpc_endpoint_failure" audit.log | tail -20
```

**Expected**: Few to none
**If found**: Check network connectivity and API keys

---

## Key Metrics to Track

### 1. Request Distribution

**Target**: ~30% premium, ~70% public

```bash
# Count by endpoint
grep "rpc_request" audit.log | jq -r '.metadata.endpoint' | sort | uniq -c
```

**Example Good Output**:
```
300 alchemy
700 public
```

### 2. Success Rate

**Target**: > 99.9%

```bash
# Calculate success rate
total=$(grep "rpc_request" audit.log | wc -l)
success=$(grep "rpc_request" audit.log | jq 'select(.metadata.success == true)' | wc -l)
echo "Success rate: $(echo "scale=2; $success * 100 / $total" | bc)%"
```

### 3. Latency

**Target**: p95 < 100ms

```bash
# Extract latencies
grep "rpc_request" audit.log | jq '.metadata.latency_ms' | sort -n
```

Check the 95th percentile (near the end of sorted list).

### 4. Cost Projection

**Target**: < 50% of free tier

```bash
# Get latest usage percentage
grep "rpc_usage_summary" audit.log | tail -1 | jq '.metadata.alchemy_usage_percent'
```

**Free tier limit**: 300M compute units/month = 10M/day

### 5. Error Rate

**Target**: < 1%

```bash
# Count failures
grep "rpc_request" audit.log | jq 'select(.metadata.success == false)' | wc -l
```

---

## Common Issues & Solutions

### Issue: No RPC usage data in audit log

**Cause**: No RPC requests made yet
**Solution**: Make some transactions or run tests to generate traffic

```bash
# Generate some RPC traffic
poetry run python scripts/test_rpc_performance.py
```

### Issue: All requests going to public RPC (0% premium)

**Possible causes**:
1. `PREMIUM_RPC_ENABLED=false` in .env
2. `PREMIUM_RPC_PERCENTAGE=0` in .env
3. Invalid Alchemy API key
4. Premium endpoints marked unhealthy

**Check**:
```bash
# Verify config
grep PREMIUM_RPC .env

# Check for unhealthy endpoints in logs
grep "marked unhealthy" audit.log
```

### Issue: High latency (>100ms p95)

**Possible causes**:
1. Network issues
2. RPC provider issues
3. Wrong RPC region

**Check**:
```bash
# Run performance test
poetry run python scripts/test_rpc_performance.py

# Check recent latencies
grep "rpc_request" audit.log | tail -100 | jq '.metadata.latency_ms' | sort -n
```

### Issue: Circuit breaker events

**Cause**: Endpoint failing repeatedly
**Action**: Investigate errors, check API keys, verify connectivity

```bash
# See circuit breaker details
grep "rpc_circuit_breaker_opened" audit.log | jq

# See what caused it
grep "rpc_endpoint_failure" audit.log | tail -10 | jq
```

### Issue: Approaching rate limits

**Cause**: High usage or wrong percentage calculation
**Action**: Review usage, consider paid tier, or reduce rollout

```bash
# Check usage
grep "rpc_usage_summary" audit.log | tail -1 | jq '.metadata'

# If needed, reduce rollout
# In .env: PREMIUM_RPC_PERCENTAGE=10
```

---

## Increasing Rollout

### After 48 Hours of Stable Operation

If all metrics look good, increase rollout:

**Week 1 → Week 2**: 30% → 60%

```bash
# In .env
PREMIUM_RPC_PERCENTAGE=60

# Restart application (if needed)
# Monitor for another 24-48 hours
```

**Week 2 → Week 3**: 60% → 100%

```bash
# In .env
PREMIUM_RPC_PERCENTAGE=100

# Final production configuration
# Monitor for 1 week to ensure stable
```

---

## Emergency Rollback

If serious issues occur:

### Option 1: Reduce Rollout Percentage

```bash
# In .env
PREMIUM_RPC_PERCENTAGE=10  # Or 0

# Application will automatically adjust
# No restart needed (picks up on next request)
```

### Option 2: Disable Premium RPC

```bash
# In .env
PREMIUM_RPC_ENABLED=false

# Falls back to 100% public RPC
# System remains fully functional
```

---

## Automated Monitoring (Optional)

For continuous monitoring, you can set up a cron job:

```bash
# Add to crontab (run every 6 hours)
0 */6 * * * cd /path/to/Mammon && poetry run python scripts/monitor_rpc_usage.py >> monitoring_log.txt 2>&1
```

Or create a simple monitoring loop:

```bash
#!/bin/bash
# monitor_loop.sh

while true; do
    echo "=== $(date) ===" >> monitoring_log.txt
    poetry run python scripts/monitor_rpc_usage.py >> monitoring_log.txt
    sleep 21600  # 6 hours
done
```

---

## Summary Checklist

### Before Increasing Rollout

- [ ] Ran monitoring script at 0h, 24h, 48h
- [ ] Ran performance tests 2-3 times
- [ ] Checked audit logs for errors
- [ ] Verified success rate > 99%
- [ ] Confirmed latency < 100ms (p95)
- [ ] Verified cost < 50% of free tier
- [ ] No circuit breaker events
- [ ] No critical errors

### If All Checkboxes Passed

✅ Safe to increase to 60%

### If Any Issues

⚠️ Stay at 30% and investigate
❌ Rollback to 10% if critical

---

## Next Steps After 100% Rollout

1. **Continue monitoring** for 1 week
2. **Set up alerts** for approaching rate limits
3. **Review monthly costs** at end of first month
4. **Consider paid tier** if consistently approaching limits
5. **Proceed to Priority 3**: Real DEX Swap

---

## Support

**Documentation**:
- `docs/rpc_configuration.md` - Full RPC setup guide
- `docs/test_results_sprint4_priority2.md` - Test results
- `docs/sprint4_priority2_complete.md` - Implementation details

**Scripts**:
- `scripts/monitor_rpc_usage.py` - Usage monitoring (this guide)
- `scripts/test_rpc_performance.py` - Performance testing

**Questions?** Check audit log patterns or re-run tests.
