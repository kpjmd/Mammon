# Phase 5: MAMMON x402 Launch Roadmap

**Created**: December 2, 2025
**Status**: Planning Complete - Ready for Execution
**Timeline**: 4 weeks to x402 marketplace

---

## Executive Summary

**Strategic Direction**: Prove MAMMON's competitive moat with existing Aave ↔ Moonwell integration, launch on x402 marketplace, then add new protocols as v1.1 upgrade.

**Key Insight**: MAMMON's competitive advantage is NOT "highest APY available" - it's:
1. **Zero unprofitable rebalances** (mathematically proven profitability gates)
2. **Autonomous decision-making** (no human intervention required)
3. **Auditable on-chain track record** (BaseScan proof)
4. **Gas-efficient execution** (Base L2 advantage)

---

## Current Status (Phase 4 Sprint 4 Complete)

### Achievements
- First live autonomous rebalance executed (Aave V3 → Moonwell)
- $200.05 USDC moved successfully
- APY improvement: 3.27% → 5.00% (+1.73%)
- Gas cost: $0.0083 (less than 1 cent)
- 100% success rate (1/1 rebalances)
- Zero errors during 1:20 hour test
- All three critical bugs fixed

### Current Position
- Wallet: 0x81A2933C185e45f72755B35110174D57b5E1FC88
- Position: ~$200 USDC in Moonwell @ ~5% APY
- ETH: ~$10 for gas

---

## Phase 1: Prove Core Competitive Moat (Week 1)

### Objective
Demonstrate MAMMON's "zero unprofitable rebalances" moat with 48-hour autonomous test on Aave ↔ Moonwell.

### Step 1: Deploy to VPS (Days 1-2)

**Infrastructure**: DigitalOcean Droplet ($4/month)
- Ubuntu 22.04
- 1 GB RAM / 1 CPU
- 25 GB SSD

### Step 2: Run 48-Hour Autonomous Test (Days 3-5)

**Configuration** (optimized for Aave/Moonwell fluctuations):
```bash
SCAN_INTERVAL_HOURS=2           # Check every 2 hours
MIN_APY_IMPROVEMENT=0.3         # Lower threshold to catch fluctuations
MIN_ANNUAL_GAIN_USD=1.0         # Lower profit requirement
MIN_PROFIT_USD=0.50             # Lower per-rebalance minimum
MAX_REBALANCES_PER_DAY=8        # Allow more opportunities
MAX_GAS_PER_DAY=5.0             # Reasonable gas budget
```

**Command**:
```bash
screen -S mammon
unset DRY_RUN_MODE && poetry run python -u scripts/run_autonomous_optimizer.py \
  --duration 48 \
  --interval 2 \
  2>&1 | tee data/moat_validation_48h.log
```

### Step 3: Analyze Results (Days 6-7)

**Success Criteria**:
- 48 hours continuous operation (no hangs/crashes)
- 24 scans completed
- 0-4 rebalances executed (depending on market conditions)
- 100% rebalance success rate
- Zero unprofitable rebalances
- Gas costs reasonable (<$0.10 total)

---

## Phase 2: Performance Dashboard & Documentation (Week 2)

### Deliverables
- `scripts/generate_moat_report.py` - Parse logs and generate metrics
- `docs/MAMMON_TRACK_RECORD.md` - Professional track record document
- `docs/X402_SERVICE_DESCRIPTION.md` - x402 listing materials

---

## Phase 3: Capital Scaling Test (Week 3)

### Objective
Validate system stability with production-scale capital ($500 USDC)

### Steps
1. Fund wallet with additional USDC ($300 more)
2. Run 1-week autonomous test
3. Monitor gas efficiency at higher amounts
4. Document results

---

## Phase 4: x402 Integration (Week 4)

### Deliverables
- `src/api/x402_service.py` - x402-compatible API wrapper
- x402 marketplace listing submission

**Listing Details**:
- Service Name: MAMMON Conservative Yield Optimizer
- Description: Zero unprofitable rebalances - mathematically proven
- Supported Networks: Base
- Supported Protocols: Aave V3, Moonwell
- Pricing: 10% of realized profit

---

## Phase 5: Production & Future Expansion (Week 5+)

### Future Protocol Expansion (v1.1)

**Priority Order**:

1. **Fluid Protocol** (HIGH PRIORITY)
   - Lending protocol (simpler than DEX)
   - Same integration pattern as Aave/Moonwell

2. **Aerodrome** (MEDIUM PRIORITY)
   - DEX liquidity provision (complex)
   - Requires APY calculation from subgraph

3. **Morpho** (LOW PRIORITY)
   - API too slow/unreliable
   - Defer until Morpho improves

---

## Key Technical Notes

### Aerodrome Current State (for future reference)
- Pool discovery via BitQuery: Working
- Real-time APY: Returns 0 (requires subgraph integration)
- Deposit/Withdraw: Not implemented
- BitQuery pool variability: Expected behavior (±10-20% due to 24h volume fluctuations)

### Morpho Current State
- Read operations: Working
- Write operations: Not implemented
- API: 30s+ response times (too slow for production)

---

## Files Modified in Phase 4 Sprint 4

| File | Change |
|------|--------|
| `src/agents/yield_scanner.py:236` | Changed `return_exceptions=True` |
| `src/blockchain/rebalance_executor.py:39` | Added `APPROVE` enum |
| `scripts/run_autonomous_optimizer.py` | Reordered initialization |

---

## Documentation Created

- `FIRST_LIVE_AUTONOMOUS_REBALANCE.md` - Historic first rebalance
- `BUG_FIXES_AUTONOMOUS_RUNNER.md` - Bug fixes + live test success

---

## Next Session Start Point

**Immediate Next Step**: Deploy to DigitalOcean VPS for 48-hour moat validation test

**Command to run after VPS setup**:
```bash
screen -S mammon
unset DRY_RUN_MODE && poetry run python -u scripts/run_autonomous_optimizer.py \
  --duration 48 \
  --interval 2 \
  2>&1 | tee data/moat_validation_48h.log
```
