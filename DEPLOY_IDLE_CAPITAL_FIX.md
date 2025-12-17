# Deployment Guide: Idle Capital Deployment Fix

## Overview
This deployment adds idle capital detection to the MAMMON optimizer, enabling it to deploy idle USDC to the best-yielding protocol instead of exiting with "No current positions to rebalance".

## What Changed
- `src/agents/scheduled_optimizer.py`: Added 3 new methods and modified optimization cycle
  - `_get_idle_capital()`: Detects idle USDC in wallet
  - `_deploy_idle_capital()`: Deploys to best protocol
  - `_is_deployment_profitable()`: Checks profitability
  - Modified `_execute_optimization_cycle()`: Handles idle capital when no positions exist

## Deployment Steps

### 1. SSH to VPS
```bash
ssh root@178.62.235.178
```

### 2. Navigate to MAMMON Directory
```bash
cd /root/mammon
```

### 3. Stop Running Optimizer
```bash
# Find the running process
ps aux | grep autonomous_optimizer

# Kill the process (replace PID with actual process ID)
kill <PID>

# Verify it's stopped
ps aux | grep autonomous_optimizer
```

### 4. Pull Latest Changes
```bash
git pull origin main
```

Expected output:
```
From https://github.com/kpjmd/Mammon
 * branch            main       -> FETCH_HEAD
   8744a44..72e687b  main       -> origin/main
Updating 8744a44..72e687b
Fast-forward
 src/agents/scheduled_optimizer.py | 172 ++++++++++++++++++++++++++++++++++++++
 1 file changed, 172 insertions(+)
```

### 5. Verify Changes
```bash
git log -1 --oneline
# Should show: 72e687b feat: Add idle capital deployment to optimizer

git diff HEAD~1 src/agents/scheduled_optimizer.py | head -50
# Should show the new methods
```

### 6. Restart Autonomous Optimizer
```bash
nohup poetry run python scripts/run_autonomous_optimizer.py > logs/autonomous_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# Get the new process ID
echo $!

# Verify it's running
ps aux | grep autonomous_optimizer
```

### 7. Monitor Logs
```bash
tail -f logs/autonomous_*.log
```

**Look for these key log messages:**
- `💰 Detected idle capital: 100 USDC` (idle capital detection)
- `📊 Best opportunity for 100 USDC: Moonwell @ 4.48% APY` (yield scanning)
- `✅ Deployment profitable: $X/year, break-even in X days` (profitability check)
- `🚀 Deploying 100 USDC → Moonwell` (deployment execution)
- `✅ Deployment successful! Gas: $X` (success confirmation)

### 8. Verify Wallet State
Check wallet on BaseScan:
```
Wallet: 0xF5Fec40E1fafa9e4382C872550d7C4944b5a1e65
BaseScan: https://basescan.org/address/0xF5Fec40E1fafa9e4382C872550d7C4944b5a1e65
```

Expected changes:
- USDC balance decreases from ~100 to ~0 (minus gas)
- New protocol position appears (Moonwell or Aave)
- Transaction history shows deposit to protocol

### 9. Check Database
```bash
poetry run python << 'EOF'
from src.data.position_tracker import PositionTracker

tracker = PositionTracker("data/mammon.db")
positions = tracker.get_all_positions()

print("Current positions:")
for pos in positions:
    if pos.status == "active":
        print(f"  {pos.protocol}: {pos.amount} {pos.token} @ {pos.current_apy}% APY")
EOF
```

## Expected Behavior

### Before Fix
```
🔍 OPTIMIZER: No current positions to rebalance
[Optimizer exits, does nothing]
```

### After Fix
```
🔍 DEBUG: _get_current_positions() called
✅ Detected 0 positions, aggregated to: {}
💰 No positions to rebalance, but found idle capital
💰 Detected idle capital: 100 USDC
📊 Best opportunity for 100 USDC: Moonwell @ 4.48% APY
✅ Deployment profitable: $4.48/year, break-even in 40 days
🚀 Deploying 100 USDC → Moonwell
[DRY RUN] Simulated deposit to Moonwell  # if dry_run_mode=true
✅ Deployment successful! Gas: $0.50
```

## Rollback Plan

If issues occur:
```bash
# Stop the optimizer
kill <PID>

# Rollback to previous commit
git reset --hard 8744a44

# Restart with old code
nohup poetry run python scripts/run_autonomous_optimizer.py > logs/autonomous_rollback.log 2>&1 &
```

## Testing Checklist

- [ ] Optimizer process is running
- [ ] Logs show idle capital detection
- [ ] Best yield opportunity identified (Moonwell or Aave)
- [ ] Profitability check passes
- [ ] Deployment executed (or simulated if dry_run_mode)
- [ ] Wallet balance decreased (if not dry_run)
- [ ] Position recorded in database
- [ ] Audit logs updated
- [ ] No errors in logs

## Notes

- **Dry Run Mode**: If `dry_run_mode=true` in config, deployments will be simulated
- **Gas Costs**: Expect ~$0.50-$1.00 in gas for actual deployment
- **Profitability**: The profitability calculator must approve the deployment
- **Minimum Amount**: Only detects idle capital ≥ $10
- **Supported Tokens**: Currently only USDC (can expand later)

## Contact

Questions? Check:
- Logs: `/root/mammon/logs/autonomous_*.log`
- Database: `/root/mammon/data/mammon.db`
- Wallet: https://basescan.org/address/0xF5Fec40E1fafa9e4382C872550d7C4944b5a1e65
