#!/bin/bash
# VPS Deployment Script: Idle Capital Deployment Fix
# Run this on the VPS at 178.62.235.178

set -e  # Exit on error

echo "=========================================="
echo "MAMMON: Deploying Idle Capital Fix"
echo "=========================================="
echo

# 1. Find and stop running optimizer
echo "1. Stopping running optimizer..."
PID=$(ps aux | grep "run_autonomous_optimizer" | grep -v grep | awk '{print $2}')

if [ -n "$PID" ]; then
    echo "   Found optimizer running with PID: $PID"
    kill $PID
    echo "   ✅ Optimizer stopped"
    sleep 2
else
    echo "   ℹ️  No running optimizer found"
fi

# 2. Navigate to mammon directory
echo
echo "2. Navigating to mammon directory..."
cd /root/mammon || { echo "❌ Failed to find /root/mammon"; exit 1; }
echo "   ✅ In directory: $(pwd)"

# 3. Pull latest changes
echo
echo "3. Pulling latest changes from git..."
git fetch origin
CURRENT=$(git rev-parse HEAD)
LATEST=$(git rev-parse origin/main)

if [ "$CURRENT" = "$LATEST" ]; then
    echo "   ℹ️  Already up to date"
else
    echo "   📥 Pulling changes..."
    git pull origin main
    echo "   ✅ Updated to latest commit"
fi

# 4. Show latest commit
echo
echo "4. Latest commit:"
git log -1 --oneline
git log -1 --format='   Author: %an <%ae>' HEAD
git log -1 --format='   Date: %ad' HEAD

# 5. Verify the fix is present
echo
echo "5. Verifying idle capital fix..."
if grep -q "_get_idle_capital" src/agents/scheduled_optimizer.py; then
    echo "   ✅ _get_idle_capital() method found"
else
    echo "   ❌ Fix not found! Check git pull"
    exit 1
fi

if grep -q "_deploy_idle_capital" src/agents/scheduled_optimizer.py; then
    echo "   ✅ _deploy_idle_capital() method found"
else
    echo "   ❌ Fix not found! Check git pull"
    exit 1
fi

# 6. Create log directory if needed
echo
echo "6. Ensuring log directory exists..."
mkdir -p logs
echo "   ✅ Log directory ready"

# 7. Restart optimizer
echo
echo "7. Restarting autonomous optimizer..."
LOGFILE="logs/autonomous_$(date +%Y%m%d_%H%M%S).log"

nohup poetry run python scripts/run_autonomous_optimizer.py > "$LOGFILE" 2>&1 &
NEW_PID=$!

echo "   ✅ Optimizer restarted with PID: $NEW_PID"
echo "   📝 Log file: $LOGFILE"

# 8. Wait a moment for startup
echo
echo "8. Waiting for startup..."
sleep 3

# 9. Verify it's running
if ps -p $NEW_PID > /dev/null; then
    echo "   ✅ Optimizer is running"
else
    echo "   ❌ Optimizer failed to start! Check logs:"
    echo "      tail -50 $LOGFILE"
    exit 1
fi

# 10. Show initial logs
echo
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo
echo "Process ID: $NEW_PID"
echo "Log file: $LOGFILE"
echo
echo "Monitor logs with:"
echo "  tail -f $LOGFILE"
echo
echo "Look for these messages:"
echo "  💰 Detected idle capital: 100 USDC"
echo "  📊 Best opportunity for 100 USDC: ..."
echo "  ✅ Deployment profitable: ..."
echo "  🚀 Deploying 100 USDC → ..."
echo
echo "First 30 lines of log:"
echo "=========================================="
head -30 "$LOGFILE"
echo "=========================================="
echo
echo "Continue monitoring with: tail -f $LOGFILE"
