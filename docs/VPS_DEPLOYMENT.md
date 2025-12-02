# MAMMON VPS Deployment Guide

**Phase 5 Week 1: 48-Hour Moat Validation Test**

This guide walks through deploying MAMMON to a DigitalOcean VPS (or any Ubuntu 22.04 server) for the 48-hour autonomous moat validation test.

---

## Prerequisites

- **VPS**: Ubuntu 22.04 droplet (1GB RAM minimum, $4-6/month)
- **SSH Access**: Root or sudo user access to VPS
- **Git Repository**: MAMMON repository cloned or synced to VPS
- **.env File**: Production .env file with live credentials (never commit this)

---

## Quick Start

```bash
# 1. SSH into VPS
ssh root@your-vps-ip

# 2. Run setup script
cd /root/mammon  # or ~/mammon if non-root
bash scripts/vps_setup.sh

# 3. Copy .env file (from local machine)
scp /path/to/local/.env root@your-vps-ip:/root/mammon/.env

# 4. Install and start systemd service
sudo cp scripts/mammon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mammon
sudo systemctl start mammon

# 5. Monitor logs
journalctl -u mammon -f
```

---

## Step-by-Step Guide

### 1. Create DigitalOcean Droplet (if needed)

**Recommended Specs** (Phase 5 Week 1 test):
- **OS**: Ubuntu 22.04 LTS
- **Plan**: Basic ($4/month)
- **CPU**: 1 vCPU
- **RAM**: 1 GB
- **Storage**: 25 GB SSD
- **Region**: Choose closest to you

**Setup**:
1. Create droplet at https://cloud.digitalocean.com/
2. Add your SSH key during creation
3. Note the IP address once created

---

### 2. SSH into VPS

```bash
ssh root@YOUR_VPS_IP
```

First-time connection will ask to verify SSH fingerprint - type `yes`.

---

### 3. Clone or Sync Repository

**Option A: Git Clone**
```bash
cd /root
git clone https://github.com/kpjmd/Mammon.git mammon
cd mammon
```

**Option B: DigitalOcean App Platform Auto-Sync** (if configured)
```bash
# Repository should already be synced at /root/mammon
cd /root/mammon
git pull origin main  # Pull latest changes
```

---

### 4. Run VPS Setup Script

This installs Python 3.11, Poetry, and all dependencies:

```bash
cd /root/mammon
bash scripts/vps_setup.sh
```

**What it does**:
1. Updates system packages
2. Installs Python 3.11 from deadsnakes PPA
3. Installs Poetry package manager
4. Runs `poetry install --no-dev` to install dependencies
5. Creates `data/` directory for logs and summaries

**Expected output**:
```
=== MAMMON VPS Setup ===
[1/6] Updating system packages...
[2/6] Installing Python 3.11...
[3/6] Installing Poetry...
[4/6] Verifying installations...
[5/6] Setting up MAMMON project...
[6/6] Setup Complete ===
```

---

### 5. Copy .env File to VPS

**From your local machine**, copy your production .env:

```bash
scp /Users/kpj/Agents/Mammon/.env root@YOUR_VPS_IP:/root/mammon/.env
```

**Critical**: Ensure .env contains:
- `DRY_RUN_MODE=false` (live mode)
- Valid CDP wallet credentials
- Valid Anthropic API key
- Sufficient ETH balance for gas (~$10)
- Base **mainnet** RPC URL (not Sepolia)

---

### 6. Verify .env Configuration

**SSH back into VPS**:

```bash
ssh root@YOUR_VPS_IP
cd /root/mammon
cat .env | grep -E "(DRY_RUN_MODE|BASE_RPC_URL|CDP_|ANTHROPIC)"
```

**Verify**:
```
DRY_RUN_MODE=false
BASE_RPC_URL=https://mainnet.base.org
CDP_API_KEY=<set>
CDP_API_SECRET=<set>
ANTHROPIC_API_KEY=<set>
```

---

### 7. Install Systemd Service

```bash
# Copy service file to systemd directory
sudo cp scripts/mammon.service /etc/systemd/system/

# Reload systemd to recognize new service
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable mammon
```

---

### 8. Start MAMMON

```bash
sudo systemctl start mammon
```

**Verify it's running**:
```bash
sudo systemctl status mammon
```

**Expected output**:
```
● mammon.service - MAMMON Autonomous Yield Optimizer
     Loaded: loaded (/etc/systemd/system/mammon.service; enabled)
     Active: active (running) since Mon 2025-12-02 10:00:00 UTC
```

---

## Monitoring the 48-Hour Test

### View Live Logs

```bash
journalctl -u mammon -f
```

**What to look for**:
- `Starting autonomous optimizer for 48.00 hours` - Confirms startup
- `Scan #1/24: Checking yield opportunities` - Each scan cycle
- `✓ No profitable rebalances found` - Normal (preserves moat)
- `Profitable rebalance found!` - Opportunity detected
- `Executing rebalance: AAVE → MOONWELL` - Live rebalance
- `Gas cost: $0.0083` - Cost tracking
- `Sleep until next scan` - Waiting for next cycle

### Check Status Anytime

```bash
sudo systemctl status mammon
```

### View Full Logs (non-live)

```bash
journalctl -u mammon
```

### Check Summary Files

```bash
ls -lh /root/mammon/data/autonomous_run_*.json
cat /root/mammon/data/autonomous_run_20251202_100000.json | jq .
```

---

## Stopping/Restarting MAMMON

### Stop the Service

```bash
sudo systemctl stop mammon
```

### Restart the Service

```bash
sudo systemctl restart mammon
```

### Disable Auto-Start on Boot

```bash
sudo systemctl disable mammon
```

---

## Post-48-Hour Test

### 1. Stop MAMMON

```bash
sudo systemctl stop mammon
```

### 2. Download Summary Files

**From local machine**:
```bash
scp -r root@YOUR_VPS_IP:/root/mammon/data/*.json ./moat_validation_results/
```

### 3. Analyze Results

**Key Metrics**:
- Total scans completed: 24 (48 hours ÷ 2 hours/scan)
- Total rebalances executed: X
- Success rate: 100% (all rebalances profitable)
- Total gas spent: $Y
- Net P&L: $Z
- Average APY improvement: N%

**Success Criteria**:
- ✅ Zero unprofitable rebalances
- ✅ Zero failed transactions
- ✅ No process hangs or crashes
- ✅ Gas costs < $0.10 per rebalance

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs for errors
journalctl -u mammon -n 50

# Common issues:
# - Missing .env file
# - Invalid credentials in .env
# - Poetry not in PATH
# - Insufficient ETH for gas
```

### Process Crashes/Restarts

```bash
# Systemd will auto-restart on failure (30s delay)
# Check logs for error:
journalctl -u mammon --since "1 hour ago"

# If persistent:
sudo systemctl stop mammon
# Fix issue, then:
sudo systemctl start mammon
```

### Low Disk Space

```bash
# Check disk usage
df -h

# Clean up old logs if needed
sudo journalctl --vacuum-time=7d  # Keep only 7 days
```

### Out of ETH

```bash
# Check wallet balance
poetry run python scripts/check_balance.py

# Fund wallet with more ETH via Coinbase or bridge
```

---

## Security Notes

- **Never commit .env to git**
- Keep only minimum ETH needed (~$10-20)
- Monitor wallet balance regularly
- Review all rebalances on BaseScan: https://basescan.org/address/YOUR_WALLET
- Set `MAX_TRANSACTION_VALUE_USD` limit in .env
- Consider using a dedicated wallet for testing

---

## Next Steps (Phase 5 Week 2)

After successful 48-hour test:
1. **Analyze results** - Generate moat validation report
2. **Document findings** - Update MAMMON_TRACK_RECORD.md
3. **Scale capital** - Increase to $500 USDC for Week 3 test
4. **Prepare x402 integration** - Begin x402 service wrapper development

---

## Useful Commands Reference

```bash
# Service management
sudo systemctl start mammon
sudo systemctl stop mammon
sudo systemctl restart mammon
sudo systemctl status mammon

# Logs
journalctl -u mammon -f            # Live logs
journalctl -u mammon -n 100        # Last 100 lines
journalctl -u mammon --since today # Today's logs

# File management
ls -lh /root/mammon/data/          # List summary files
tail -f /root/mammon/*.log         # View log files (if any)

# Git updates
cd /root/mammon && git pull        # Update code from repo

# Environment
poetry env info                    # Check Python environment
poetry show                        # List installed packages
```

---

## Support

If you encounter issues:
1. Check logs: `journalctl -u mammon -f`
2. Review .env configuration
3. Verify wallet has sufficient ETH
4. Check BaseScan for transaction details
5. Consult Phase 5 planning docs: `PHASE5_X402_ROADMAP.md`

---

**Last Updated**: December 2, 2025
**Phase**: Phase 5 Week 1 - Moat Validation Test
