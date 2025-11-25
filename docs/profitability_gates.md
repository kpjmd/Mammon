# MAMMON Profitability Gates Guide

**Version**: Phase 3 Sprint 3
**Last Updated**: November 16, 2025

---

## Overview

MAMMON's **Profitability Gate System** is a 4-gate validation framework that mathematically proves every rebalancing decision is profitable before execution. This is MAMMON's competitive moat - preventing costly gas-burning on marginal gains that competitors ignore.

### The Problem

Most DeFi yield optimizers chase APY blindly:
- ❌ Move $100 for 0.1% APY improvement → lose money on gas
- ❌ Spend $10 gas to earn $5/year → 730 day break-even
- ❌ Pay 2% swap fees for 1% APY gain → net loss

### MAMMON's Solution

**4-Gate Validation**: Every move must pass ALL 4 profitability gates:

1. **APY Improvement** - Is the yield meaningfully better?
2. **Net Annual Gain** - Will we make real profit after costs?
3. **Break-Even Period** - How quickly do we recover costs?
4. **Cost Ratio** - Are costs reasonable relative to position size?

If ANY gate fails → **recommendation blocked** → save user money ✅

---

## The 4 Profitability Gates

### Gate 1: APY Improvement

**Question**: Is the target APY meaningfully better than current?

**Requirement**: `target_apy > current_apy + MIN_APY_IMPROVEMENT`

**Default Threshold**: 0.5% (configurable via `MIN_APY_IMPROVEMENT`)

**Example**:
```python
Current APY: 5.0%
Target APY: 5.4%
Improvement: 0.4%

MIN_APY_IMPROVEMENT = 0.5%

Result: ❌ FAIL (0.4% < 0.5% minimum)
Reason: "APY improvement too small"
```

**Why This Matters**:
Prevents chasing marginal improvements that don't justify transaction costs.

**Tuning Guide**:
- **Aggressive**: 0.25% (chase any small improvement)
- **Moderate**: 0.5% (default - balanced)
- **Conservative**: 1.0% (only big improvements)

---

### Gate 2: Net Annual Gain

**Question**: Will we make real profit after deducting ALL costs?

**Requirement**: `net_annual_gain >= MIN_ANNUAL_GAIN_USD`

**Default Threshold**: $10/year (configurable via `MIN_ANNUAL_GAIN_USD`)

**Calculation**:
```python
gross_annual_gain = (target_apy - current_apy) * position_size / 100
total_costs = gas_costs + slippage + protocol_fees
net_annual_gain = gross_annual_gain - total_costs

if net_annual_gain >= MIN_ANNUAL_GAIN_USD:
    ✅ PASS
else:
    ❌ FAIL
```

**Example**:
```python
Position: $1,000
Current APY: 5.0%
Target APY: 6.5%
Improvement: 1.5%

Gross Annual Gain = 1.5% × $1,000 = $15/year
Gas Costs = $3 (withdraw + approve + deposit)
Slippage = $0 (same token)
Protocol Fees = $2 (0.2% withdrawal fee)
Total Costs = $5

Net Annual Gain = $15 - $5 = $10/year

MIN_ANNUAL_GAIN_USD = $10

Result: ✅ PASS (exactly $10 net gain)
```

**Why This Matters**:
Ensures every move generates real profit, not just paper gains eaten by fees.

**Tuning Guide**:
- **Aggressive**: $5/year (accept small gains)
- **Moderate**: $10/year (default - reasonable threshold)
- **Conservative**: $25/year (only significant gains)
- **Whale**: $100+/year (for large portfolios)

---

### Gate 3: Break-Even Period

**Question**: How quickly do we recover the upfront costs?

**Requirement**: `break_even_days <= MAX_BREAK_EVEN_DAYS`

**Default Threshold**: 30 days (configurable via `MAX_BREAK_EVEN_DAYS`)

**Calculation**:
```python
daily_gain = net_annual_gain / 365
break_even_days = total_costs / daily_gain

if break_even_days <= MAX_BREAK_EVEN_DAYS:
    ✅ PASS
else:
    ❌ FAIL
```

**Example**:
```python
Total Costs = $10
Net Annual Gain = $50/year
Daily Gain = $50 / 365 = $0.137/day

Break-Even Days = $10 / $0.137 = 73 days

MAX_BREAK_EVEN_DAYS = 30

Result: ❌ FAIL (73 days > 30 day limit)
Reason: "Break-even period too long"
```

**Why This Matters**:
Prevents locking capital in moves that take forever to become profitable. Market conditions can change in 73 days!

**Tuning Guide**:
- **Aggressive**: 60 days (patient approach)
- **Moderate**: 30 days (default - 1 month)
- **Conservative**: 14 days (2 weeks max)
- **Day Trader**: 7 days (1 week max)

---

### Gate 4: Cost Ratio

**Question**: Are costs reasonable relative to position size?

**Requirement**: `total_costs / position_size <= MAX_REBALANCE_COST_PCT`

**Default Threshold**: 1% (configurable via `MAX_REBALANCE_COST_PCT`)

**Calculation**:
```python
cost_pct = (total_costs / position_size) * 100

if cost_pct <= MAX_REBALANCE_COST_PCT:
    ✅ PASS
else:
    ❌ FAIL
```

**Example**:
```python
Position Size = $500
Total Costs = $8 (gas + fees)

Cost Percentage = ($8 / $500) × 100 = 1.6%

MAX_REBALANCE_COST_PCT = 1.0%

Result: ❌ FAIL (1.6% > 1.0% limit)
Reason: "Costs exceed 1% of position"
```

**Why This Matters**:
Prevents disproportionate costs on small positions. Spending $10 to move $100 is a 10% cost ratio - absurd!

**Tuning Guide**:
- **Aggressive**: 2.0% (accept higher costs)
- **Moderate**: 1.0% (default - reasonable limit)
- **Conservative**: 0.5% (minimize costs)
- **Institutional**: 0.25% (enterprise standards)

---

## Cost Components

The profitability calculator considers ALL rebalancing costs:

### 1. Gas Costs (Blockchain Fees)

Typical rebalance requires 4 transactions:
1. **Withdraw** from source protocol (~50,000 gas)
2. **Approve** token for destination (~50,000 gas)
3. **Swap** (if different token) (~120,000 gas)
4. **Deposit** into destination protocol (~80,000 gas)

**Total Gas**: ~180,000 - 300,000 gas depending on path

**Cost Calculation**:
```python
gas_price = 0.05 gwei (Base network)
eth_price = $3,500
gas_used = 250,000

gas_cost_eth = 250,000 × 0.05 / 1e9 = 0.0000125 ETH
gas_cost_usd = 0.0000125 × $3,500 = $0.04

Typical Base gas cost: $0.04 - $0.15 per rebalance
```

**Note**: MAMMON uses `GasEstimator` for real-time estimates.

### 2. Slippage (Price Impact)

When swapping tokens (e.g., USDC → WETH → Protocol Token):

**Calculation**:
```python
# Example: Swap $5,000 USDC for WETH
slippage_bps = 50  # 0.5% default
swap_amount = $5,000

slippage_cost = $5,000 × (50 / 10000) = $25
```

**Note**: MAMMON uses `SlippageCalculator` based on pool liquidity.

**Typical Ranges**:
- **Stable → Stable**: 0.01% - 0.05% (minimal)
- **Major Token**: 0.1% - 0.3% (low)
- **Minor Token**: 0.5% - 2.0% (moderate)
- **Illiquid**: 2% - 10% (high)

### 3. Protocol Fees

Withdrawal and deposit fees vary by protocol:

| Protocol | Withdrawal Fee | Deposit Fee | Notes |
|----------|----------------|-------------|-------|
| **Aave V3** | 0% | 0% | No fees |
| **Morpho** | 0% | 0% | No fees |
| **Moonwell** | ~0.1% | 0% | Redemption slippage |
| **Aerodrome** | 0.01% - 0.05% | 0% | LP exit fees |

**Total Protocol Fees**: Usually < $2 on typical rebalance

---

## Real-World Examples

### Example 1: ✅ PROFITABLE MOVE

**Scenario**: Move $10,000 from Aave (5.0% APY) to Morpho (7.5% APY)

**Gate 1: APY Improvement**
- Current: 5.0%, Target: 7.5%
- Improvement: 2.5% ✅ (> 0.5% minimum)

**Gate 2: Net Annual Gain**
- Gross gain: 2.5% × $10,000 = $250/year
- Gas costs: $0.10
- Slippage: $0 (same USDC)
- Protocol fees: $0
- **Net gain: $249.90/year** ✅ (> $10 minimum)

**Gate 3: Break-Even**
- Daily gain: $249.90 / 365 = $0.68/day
- Break-even: $0.10 / $0.68 = **0.15 days** ✅ (< 30 days)

**Gate 4: Cost Ratio**
- Cost: $0.10 / $10,000 = **0.001%** ✅ (< 1%)

**Result**: ✅ ALL GATES PASS - Recommendation approved

**ROI**: 249,900% on costs (earn $249.90 for $0.10 spent)

---

### Example 2: ❌ UNPROFITABLE MOVE (Small Position)

**Scenario**: Move $100 from Aave (5.0% APY) to Morpho (7.0% APY)

**Gate 1: APY Improvement**
- Improvement: 2.0% ✅ (> 0.5%)

**Gate 2: Net Annual Gain**
- Gross gain: 2.0% × $100 = $2/year
- Gas costs: $0.08
- Total costs: $0.08
- **Net gain: $1.92/year** ❌ (< $10 minimum)

**Result**: ❌ GATE 2 FAIL - Blocked

**Why**: Position too small to justify transaction costs

---

### Example 3: ❌ UNPROFITABLE MOVE (Long Break-Even)

**Scenario**: Move $2,000 from Moonwell (6.0% APY) to Aerodrome (6.8% APY)

**Gate 1: APY Improvement**
- Improvement: 0.8% ✅ (> 0.5%)

**Gate 2: Net Annual Gain**
- Gross gain: 0.8% × $2,000 = $16/year
- Gas costs: $0.10
- Slippage: $4 (USDC → WETH → LP token)
- Protocol fees: $1
- Total costs: $5.10
- **Net gain: $10.90/year** ✅ (> $10)

**Gate 3: Break-Even**
- Daily gain: $10.90 / 365 = $0.03/day
- **Break-even: 170 days** ❌ (> 30 days)

**Result**: ❌ GATE 3 FAIL - Blocked

**Why**: Takes too long to recover swap costs

---

### Example 4: ❌ UNPROFITABLE MOVE (High Cost Ratio)

**Scenario**: Move $200 from Aave (5.0% APY) to Morpho (8.0% APY)

**Gate 1: APY Improvement**
- Improvement: 3.0% ✅ (> 0.5%)

**Gate 2: Net Annual Gain**
- Gross gain: 3.0% × $200 = $6/year
- Total costs: $0.08
- **Net gain: $5.92/year** ❌ (< $10)

**Gate 4: Cost Ratio**
- Cost: $0.08 / $200 = **0.04%** ✅ (< 1%)

**Result**: ❌ GATE 2 FAIL - Blocked

**Why**: Absolute gain too small even though cost ratio is fine

---

## Configuration Guide

### Quick Start Profiles

#### Profile 1: Aggressive (High Frequency)
```bash
MIN_APY_IMPROVEMENT=0.25
MIN_ANNUAL_GAIN_USD=5
MAX_BREAK_EVEN_DAYS=60
MAX_REBALANCE_COST_PCT=2.0
MIN_REBALANCE_AMOUNT=50
```
**Use Case**: Active management, frequent rebalancing, accept higher costs

#### Profile 2: Moderate (Default)
```bash
MIN_APY_IMPROVEMENT=0.5
MIN_ANNUAL_GAIN_USD=10
MAX_BREAK_EVEN_DAYS=30
MAX_REBALANCE_COST_PCT=1.0
MIN_REBALANCE_AMOUNT=100
```
**Use Case**: Balanced approach, most users, recommended starting point

#### Profile 3: Conservative (Low Frequency)
```bash
MIN_APY_IMPROVEMENT=1.0
MIN_ANNUAL_GAIN_USD=25
MAX_BREAK_EVEN_DAYS=14
MAX_REBALANCE_COST_PCT=0.5
MIN_REBALANCE_AMOUNT=500
```
**Use Case**: Minimize transactions, only high-confidence moves

#### Profile 4: Whale (Large Positions)
```bash
MIN_APY_IMPROVEMENT=0.25
MIN_ANNUAL_GAIN_USD=100
MAX_BREAK_EVEN_DAYS=7
MAX_REBALANCE_COST_PCT=0.25
MIN_REBALANCE_AMOUNT=5000
```
**Use Case**: $100k+ portfolios, optimize for absolute returns

---

## Tuning for Your Portfolio

### Small Portfolio ($1k - $10k)
- **Focus**: Minimize transaction count
- **Key Setting**: Increase `MIN_REBALANCE_AMOUNT` to $200-$500
- **Rationale**: Gas costs eat larger % of returns

### Medium Portfolio ($10k - $100k)
- **Focus**: Balance frequency and returns
- **Key Setting**: Use default settings
- **Rationale**: Costs are 0.01% - 0.1% of portfolio

### Large Portfolio ($100k+)
- **Focus**: Maximize absolute returns
- **Key Setting**: Lower `MIN_APY_IMPROVEMENT` to 0.25%
- **Rationale**: Even 0.25% on $100k = $250/year

### Gas Price Sensitivity

**High Base Gas Periods (>2 gwei)**:
- Increase `MAX_BREAK_EVEN_DAYS` to 45-60
- Increase `MAX_REBALANCE_COST_PCT` to 1.5%
- Wait for gas to drop

**Low Base Gas Periods (<0.05 gwei)**:
- Decrease `MIN_APY_IMPROVEMENT` to 0.3%
- Decrease `MAX_BREAK_EVEN_DAYS` to 14
- Rebalance more aggressively

---

## FAQ

### Q: Why was my rebalance blocked?

**A**: Check which gate failed in the logs. Common reasons:
1. **Position too small** → Gate 2 fail (net gain < $10)
2. **Marginal APY improvement** → Gate 1 fail (< 0.5% improvement)
3. **High swap costs** → Gate 3 fail (long break-even)
4. **Small position, high gas** → Gate 4 fail (cost ratio > 1%)

### Q: How do I make MAMMON more aggressive?

**A**: Lower the thresholds:
```bash
MIN_APY_IMPROVEMENT=0.25  # Accept smaller improvements
MIN_ANNUAL_GAIN_USD=5     # Accept smaller gains
MAX_BREAK_EVEN_DAYS=60    # Allow longer break-even
```

### Q: How do I make MAMMON more conservative?

**A**: Raise the thresholds:
```bash
MIN_APY_IMPROVEMENT=1.0   # Only big improvements
MIN_ANNUAL_GAIN_USD=25    # Meaningful gains only
MAX_BREAK_EVEN_DAYS=14    # Quick payback required
```

### Q: Can I disable profitability gates?

**A**: No. This is MAMMON's core protection. You can set very low thresholds (e.g., $1 min gain), but gates cannot be disabled.

### Q: Do all strategies use profitability gates?

**A**: Yes. Both `SimpleYieldStrategy` and `RiskAdjustedStrategy` use profitability gates. The difference:
- **SimpleYield**: Profitability gate only
- **RiskAdjusted**: Profitability gate AND risk gate (dual validation)

### Q: What happens if gas prices spike mid-rebalance?

**A**: Transaction simulation catches this before submission. If gas exceeds `MAX_GAS_PRICE_GWEI`, transaction is blocked.

### Q: How accurate are the profitability estimates?

**A**: Very accurate for same-token moves (±5%). Swap-based moves depend on slippage estimates (±10-20% in volatile markets).

---

## Integration with Risk Assessment

Profitability gates work alongside MAMMON's **7-Factor Risk Assessment**:

### Dual-Gate System

**RiskAdjustedStrategy** requires BOTH gates:
1. **Profitability Gate**: Must be profitable (4 gates)
2. **Risk Gate**: Must be safe enough (7 factors)

**Example Decision Flow**:
```
Move: Aave → Morpho, $10k USDC

Step 1: Check Profitability
├─ Gate 1 (APY): ✅ 2.5% improvement
├─ Gate 2 (Net Gain): ✅ $250/year
├─ Gate 3 (Break-Even): ✅ 0.15 days
└─ Gate 4 (Cost Ratio): ✅ 0.001%
Result: ✅ PROFITABLE

Step 2: Check Risk (RiskAdjusted only)
├─ Protocol Risk: ✅ Morpho = 90/100 (HIGH SAFETY)
├─ TVL: ✅ $45M (adequate)
├─ Utilization: ✅ 65% (safe)
├─ Position Size: ✅ $10k (normal)
├─ Swap Required: ✅ No (same USDC)
├─ Concentration: ✅ Won't exceed 40% limit
└─ Diversification: ✅ Maintains 3 protocols
Result: ✅ LOW RISK (score: 18/100)

Final Decision: ✅ RECOMMEND (profitable + safe)
```

---

## Monitoring & Optimization

### Recommended Metrics to Track

1. **Rejection Rate**: % of moves blocked by profitability gates
   - **Target**: 20-40% (gates doing their job)
   - **Too High (>60%)**: Thresholds too strict, loosen settings
   - **Too Low (<10%)**: Thresholds too loose, tighten settings

2. **Average Net Gain**: Typical profit per rebalance
   - **Target**: $50-$200 for moderate portfolio
   - Track over time to validate profitability

3. **Average Break-Even**: How fast moves become profitable
   - **Target**: 5-10 days
   - Shorter is better

4. **ROI on Costs**: Return on transaction costs
   - **Target**: >1000% (earn $10 for every $1 spent)
   - **Minimum**: 200% (earn $2 per $1 spent)

---

## Appendix: Profitability Calculator API

### Basic Usage

```python
from src.strategies.profitability_calculator import ProfitabilityCalculator
from decimal import Decimal

# Initialize with thresholds
calc = ProfitabilityCalculator(
    min_annual_gain_usd=Decimal("10"),
    max_break_even_days=30,
    max_cost_pct=Decimal("0.01"),  # 1%
)

# Calculate profitability
profitability = await calc.calculate_profitability(
    current_apy=Decimal("5.0"),
    target_apy=Decimal("7.5"),
    position_size_usd=Decimal("10000"),
    requires_swap=False,
    protocol_fee_pct=Decimal("0"),
)

# Check result
if profitability.is_profitable:
    print(f"✅ Profitable!")
    print(f"   Net Gain: ${profitability.net_gain_first_year}/year")
    print(f"   Break-Even: {profitability.break_even_days} days")
    print(f"   ROI: {profitability.roi_on_costs}%")
else:
    print(f"❌ Not Profitable")
    print(f"   Reasons: {profitability.rejection_reasons}")
```

### Output Structure

```python
@dataclass
class MoveProfitability:
    is_profitable: bool
    annual_gain_usd: Decimal
    total_cost_usd: Decimal
    net_gain_first_year: Decimal
    break_even_days: int
    roi_on_costs: Decimal
    profitability_breakdown: str
    rejection_reasons: List[str]
```

---

**Last Updated**: November 16, 2025
**Version**: Phase 3 Sprint 3
**Status**: Production Ready
