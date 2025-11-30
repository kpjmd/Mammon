# Autonomous Runner Bug Fixes - 2025-11-30

## Summary
Fixed two critical bugs preventing proper autonomous operation of Mammon's scheduled optimizer.

## Bug #1: No-Sleep Loop

**Issue**: When scan interval exceeded remaining duration, loop continued scanning instead of exiting.

**Root Cause**: Missing break statement when `next_scan >= end_time`.

**Fix**: Added explicit exit condition in `scripts/run_autonomous_optimizer.py:331-334`

```python
# BUG FIX #2: Exit gracefully if next scan would exceed end time
if next_scan >= self.end_time:
    logger.info(f"Next scan at {next_scan} would exceed end time {self.end_time}, exiting")
    print(f"\n✅ Next scan would exceed end time, completing run")
    break
```

**Validation**: Test with `--duration 0.01 --interval 1` → 1 scan, clean exit ✅

## Bug #2: Sleep Timing & Monitoring

**Issue**: Original bug reports showed sleep lasting 4+ hours instead of 30 minutes.

**Investigation**: Added comprehensive debug logging to track sleep behavior.

**Features Added** (lines 336-377):
- Per-iteration timing (warns if >30s)
- Heartbeat logs every 10 minutes
- Sleep anomaly detection
- Iteration count transparency

```python
# Sleep in short intervals with debug logging
for i in range(sleep_iterations):
    if not self.running:
        break

    # Time each iteration to detect blocking
    iter_start = datetime.now(UTC)
    await asyncio.sleep(10)
    iter_duration = (datetime.now(UTC) - iter_start).total_seconds()
    iterations_completed += 1

    # Warn if single iteration took >30s (should be ~10s)
    if iter_duration > 30:
        logger.warning(f"⚠️  Sleep iteration {i} took {iter_duration:.1f}s (expected 10s)")

    # Log every 60 iterations (10 min) as heartbeat
    if iterations_completed % 60 == 0:
        elapsed = (datetime.now(UTC) - sleep_start).total_seconds()
        logger.info(f"💤 Sleep heartbeat: {iterations_completed}/{sleep_iterations} iterations, {elapsed:.0f}s elapsed")
```

**Findings**:
- Code is correct - sleep timing works properly
- Anomalies were caused by laptop sleep (validated via debug logs)
- For production: Deploy on always-on system

## Test Results

| Test | Scans | Duration | Result |
|------|-------|----------|--------|
| Bug #1 validation | 1 | 25s | ✅ Exit condition works |
| 15-min test | 3 | 11:14 | ✅ Sleep timing accurate |
| 30-min test | 3 | 21:32 | ✅ Heartbeats working |
| 2-hour laptop test | 2 | 3.5h | ✅ Detected laptop sleep |

## Production Requirements
- Always-on system (server/desktop with sleep disabled/Raspberry Pi)
- NOT laptop with auto-sleep enabled

## Validation Evidence

### Bug #1 Fix - Single Scan Test
```
Duration: 0.01 hours
Scan Interval: 1.0 hours
Total Scans: 1
✅ Next scan would exceed end time, completing run
```

### Bug #2 Debug Logging - Heartbeat Test
```
Next scan at 16:22:48 UTC
Sleeping for 0.167 hours (60 × 10s iterations)...
  💤 Sleep heartbeat: 60/60 iterations (600s elapsed)
```

### Laptop Sleep Detection
```
⚠️  Sleep iteration 127 took 1650.7s (expected 10s)
⚠️  Sleep iteration 129 took 924.4s (expected 10s)
⚠️  Sleep iteration 135 took 3070.8s (expected 10s)
```

## Files Modified
- `scripts/run_autonomous_optimizer.py` (lines 327-377)

## Next Steps
With these bugs fixed, Mammon is ready for:
1. Extended autonomous testing on always-on system
2. Live rebalance validation test (Aave → Moonwell)
3. 24+ hour stability validation before production deployment
