# Demo Sprint 3 - Running Guide

**Quick Reference**: How to run the Phase 3 Sprint 3 demonstration

---

## Quick Start

```bash
# Make sure you're in the project root
cd /path/to/Mammon

# Run the demo
poetry run python scripts/demo_sprint3.py
```

---

## Prerequisites

### Required
- ✅ Python 3.11+ with Poetry installed
- ✅ Project dependencies installed (`poetry install`)
- ✅ Internet connection (queries Base mainnet)

### Recommended
- ✅ Alchemy API key (avoid RPC rate limiting)
- ✅ `.env` file configured

### Optional
- Base Sepolia testnet wallet (not needed for demo - read-only)

---

## Configuration

### Option 1: With Alchemy (Recommended)

Create/update `.env`:
```bash
# Premium RPC (recommended to avoid rate limits)
ALCHEMY_API_KEY=your_alchemy_api_key_here

# Other settings
LOG_LEVEL=INFO
```

**Benefits**:
- No 429 rate limiting errors
- Faster protocol scanning
- Better reliability

### Option 2: Without Alchemy (May Hit Rate Limits)

Demo will work but may encounter:
- `429 Too Many Requests` errors
- Slower scanning
- Some protocols may fail

**The demo will warn you if no Alchemy key is detected.**

---

## What the Demo Shows

### 1. Multi-Protocol Yield Scanning
- Scans 4 protocols on Base mainnet
- Real-time yield data
- Top 10 opportunities by APY

### 2. SimpleYield Optimization (Aggressive)
- Current portfolio: $5k Aave + $10k Moonwell
- Finds highest APY moves
- Validates profitability (4-gate system)

### 3. RiskAdjusted Optimization (Conservative)
- Same portfolio
- Filters by risk (7-factor analysis)
- Shows safer, diversified recommendations

### 4. New Capital Allocation
- $10k new capital
- SimpleYield: 100% to best opportunity
- RiskAdjusted: Diversified across protocols

### 5. Strategy Comparison
- Side-by-side comparison
- Aggressive vs Conservative
- Concentration vs Diversification

### 6. Profitability Gates Explained
- 4-gate system breakdown
- Cost components
- Why moves are blocked

### 7. Risk Assessment Explained
- 7-factor risk scoring
- Protocol safety scores
- Risk levels (LOW/MEDIUM/HIGH/CRITICAL)

---

## Expected Output

### Success Case (With Alchemy)
```
================================================================================
                 MAMMON - Phase 3 Sprint 3 Demonstration
================================================================================

⚠️  IMPORTANT: This demo queries real Base mainnet data
   - Requires RPC access (Alchemy recommended to avoid rate limits)
   - Some tokens may not have Chainlink price feeds
   - Scanning 4 protocols may take 10-30 seconds

Components:
  ✓ YieldScanner - Multi-protocol opportunity discovery
  ✓ ProfitabilityCalculator - 4-gate validation system
  ...

✅ Using Alchemy Premium RPC

--------------------------------------------------------------------------------
INITIALIZATION: Setting up optimization engine
--------------------------------------------------------------------------------

✅ YieldScanner initialized with 4 protocols
✅ SimpleYieldStrategy initialized (aggressive mode)
...

================================================================================
                     DEMO 1: Multi-Protocol Yield Scanning
================================================================================

Scanning all 4 protocols on Base mainnet...
  - Aerodrome (DEX)
  - Morpho Blue (Lending)
  - Aave V3 (Lending)
  - Moonwell (Lending)

⏳ This may take 10-30 seconds depending on RPC performance...

✅ Found 127 total opportunities

📈 Top 10 Yield Opportunities (by APY):

   1. Morpho      - USDC          :  7.85% APY ($  45,234,567 TVL)
   2. Aave V3     - WETH          :  5.23% APY ($ 125,678,901 TVL)
   ...
```

### Warning Case (No Alchemy)
```
⚠️  No Alchemy API key found - using public RPC (may hit rate limits)
   Set ALCHEMY_API_KEY in .env for better performance

[... demo continues but may show 429 errors ...]
```

---

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'src'`
**Fix**: This is already fixed in the script. If you see this:
```bash
# Make sure you're using the latest version
git pull
```

### Issue: `429 Too Many Requests for url: https://mainnet.base.org/`
**Cause**: No Alchemy API key configured
**Fix**:
1. Sign up for Alchemy (free): https://www.alchemy.com/
2. Get API key for Base
3. Add to `.env`: `ALCHEMY_API_KEY=your_key_here`
4. Re-run demo

### Issue: Warnings about missing Chainlink feeds (CBBTC/USD, WEETH/USD)
**Cause**: Some tokens don't have direct price feeds on Base
**Impact**: Those pools will be skipped in results
**Fix**: This is expected - demo will continue with available data
**Future**: Phase 4 will add composite feed support

### Issue: No opportunities found
**Possible Causes**:
1. RPC rate limiting (configure Alchemy)
2. Network connectivity issues
3. Protocols temporarily unavailable

**Debug Steps**:
```bash
# Check if you can reach Base mainnet
curl https://mainnet.base.org

# Check logs for specific errors
LOG_LEVEL=DEBUG poetry run python scripts/demo_sprint3.py
```

### Issue: Takes longer than 30 seconds
**Cause**: Slow RPC connection or rate limiting
**Fix**: Configure Alchemy API key
**Workaround**: Be patient - it will complete

---

## Performance Notes

### With Alchemy Premium RPC
- Scan time: 10-15 seconds
- Success rate: ~95%+
- No rate limiting

### With Public RPC
- Scan time: 20-30 seconds (with retries)
- Success rate: 60-80%
- May encounter 429 errors

---

## Demo Duration

**Total demo runtime**: 2-3 minutes

Breakdown:
- Initialization: 5 seconds
- Protocol scanning: 10-30 seconds
- Optimizations: 5 seconds per demo (x6)
- Explanations: Text display only

---

## Understanding the Output

### Profitability Gates
When you see: **"❌ UNPROFITABLE"**
- Move was blocked by profitability gates
- Check which gate failed:
  - Gate 1: APY improvement too small
  - Gate 2: Net gain < $10/year
  - Gate 3: Break-even > 30 days
  - Gate 4: Costs > 1% of position

This is **good** - MAMMON is protecting you from bad moves!

### Risk Levels
When you see risk scores:
- **0-25 (LOW)**: Safe to proceed
- **26-50 (MEDIUM)**: Normal risk
- **51-75 (HIGH)**: Requires elevated approval
- **76-100 (CRITICAL)**: Blocked by default

Higher is riskier.

### Recommendations
When strategies generate recommendations:
- **Confidence**: 0-100 score
  - >80: High confidence
  - 60-80: Medium confidence
  - <60: Low confidence
- **Reason**: Human-readable explanation
- **Expected APY**: Target yield after move

---

## Next Steps After Demo

### 1. Review Configuration
See `docs/profitability_gates.md` for detailed configuration guide

### 2. Tune Parameters
Edit `.env`:
```bash
# Make more aggressive
MIN_APY_IMPROVEMENT=0.25
MIN_ANNUAL_GAIN_USD=5

# Make more conservative
MIN_APY_IMPROVEMENT=1.0
MIN_ANNUAL_GAIN_USD=25
```

### 3. Run Again
Test different configurations:
```bash
poetry run python scripts/demo_sprint3.py
```

### 4. Move to Phase 4
Ready for real transaction execution:
- Read `PHASE4_HANDOFF.md`
- Review `NEXT_SESSION_PHASE4.txt`
- Begin transaction execution implementation

---

## Advanced Usage

### Debug Mode
```bash
LOG_LEVEL=DEBUG poetry run python scripts/demo_sprint3.py
```

Shows detailed logs including:
- RPC requests
- Chainlink feed queries
- Profitability calculations
- Risk assessments

### Specific Protocol Testing
Edit `demo_sprint3.py` to test specific scenarios:
```python
# Test with different portfolio
current_positions = {
    "Morpho": Decimal("20000"),  # $20k in Morpho
    "Aave V3": Decimal("5000"),  # $5k in Aave
}
```

---

## Getting Help

### Documentation
- `PHASE3_SPRINT3_COMPLETE.md` - Complete Sprint 3 report
- `docs/profitability_gates.md` - Configuration guide
- `PHASE4_HANDOFF.md` - Phase 3→4 transition

### Common Questions
**Q: Why are some pools missing?**
A: Missing Chainlink feeds or low TVL filtered out

**Q: Can I run on testnet?**
A: This demo uses mainnet data (read-only). Phase 4 will add testnet execution.

**Q: How do I configure risk tolerance?**
A: Edit `.env`: `RISK_TOLERANCE=low|medium|high`

---

**Last Updated**: November 17, 2025
**Version**: Phase 3 Sprint 3
**Status**: Production Ready
