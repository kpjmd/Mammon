# Phase 3: Yield Optimization - Implementation Guide

**Date**: November 14, 2025
**Status**: Ready to Begin
**Duration**: 9-15 days (6 sprints)
**Objective**: Build autonomous yield optimization across lending protocols

---

## Mission Statement

Transform Mammon from a swap executor into an autonomous yield optimization agent that:
1. Monitors yields across multiple lending protocols
2. Calculates net returns after all costs
3. Executes profitable rebalancing automatically
4. Maximizes user returns while minimizing risk

---

## Current Status: What's Ready

### ✅ Foundation Complete (Phases 1-3)
- **Wallet Management**: Local BIP-39 wallet with transaction signing
- **Swap Execution**: Uniswap V3 integration with 8-layer security
- **Price Oracles**: Chainlink + mock fallback
- **Gas Estimation**: Accurate cost prediction
- **Security Framework**: Approval thresholds, spending limits, simulation
- **First Real Swap**: Successfully executed on Base Sepolia

### 🎯 What We're Building

```
Current: Mammon can swap tokens
Target:  Mammon autonomously optimizes yields

Flow: Monitor Yields → Calculate Net Returns → Execute Rebalancing
```

---

## Architecture Overview

### Phase 3A: Protocol Scanning (Sprint 1-2)
```
src/protocols/
├── base_protocol.py          # Abstract protocol interface
├── morpho.py                  # Morpho lending protocol
├── aave_v3.py                # Aave V3 lending protocol
└── moonwell.py               # Moonwell lending protocol

src/agents/
└── yield_scanner.py          # Scans protocols for yields

src/data/
├── yield_tracker.py          # Historical yield tracking
└── position_manager.py       # Track active positions
```

### Phase 3B: Optimization Logic (Sprint 3-4)
```
src/strategies/
├── allocation_calculator.py  # Optimal allocation logic
├── rebalancing_engine.py     # When/how to rebalance
└── risk_assessor.py          # Protocol safety scoring

src/blockchain/
└── transaction_sequencer.py  # Multi-step transaction handling
```

### Phase 3C: Autonomous Agent (Sprint 5-6)
```
src/agents/
└── yield_optimizer.py        # LangGraph orchestration

src/monitoring/
├── performance_tracker.py    # Track returns
└── reporting.py              # Performance reports
```

---

## Sprint Breakdown

### Sprint 1: Protocol Integration Foundation (1-2 days)

**Objectives:**
1. Create BaseProtocol abstract class
2. Implement Morpho protocol (read-only first)
3. Build protocol data models
4. Add position tracking to database

**Deliverables:**
```python
# src/protocols/base_protocol.py
class BaseProtocol(ABC):
    @abstractmethod
    async def get_supply_apy(self, token: str) -> Decimal: ...

    @abstractmethod
    async def get_borrow_apy(self, token: str) -> Decimal: ...

    @abstractmethod
    async def get_position(self, wallet: str) -> Position: ...

    @abstractmethod
    async def build_supply_tx(self, token: str, amount: Decimal) -> dict: ...

    @abstractmethod
    async def build_withdraw_tx(self, token: str, amount: Decimal) -> dict: ...

    @property
    @abstractmethod
    def safety_score(self) -> int: ...

# src/protocols/morpho.py
class MorphoProtocol(BaseProtocol):
    # Implementation for Morpho
```

**Success Criteria:**
- [ ] Can query Morpho APYs for ETH/USDC
- [ ] Can read existing positions
- [ ] Integration tests passing
- [ ] Documentation complete

---

### Sprint 2: Multi-Protocol Scanning (1-2 days)

**Objectives:**
1. Integrate Aave V3
2. Integrate Moonwell
3. Build YieldScanner agent
4. Create yield comparison logic

**Deliverables:**
```python
# src/agents/yield_scanner.py
class YieldScanner:
    def __init__(self, protocols: List[BaseProtocol]):
        self.protocols = protocols

    async def scan_yields(self, tokens: List[str]) -> Dict[str, ProtocolYield]:
        """Scan all protocols for yields"""
        results = {}
        for protocol in self.protocols:
            for token in tokens:
                apy = await protocol.get_supply_apy(token)
                results[f"{protocol.name}:{token}"] = ProtocolYield(
                    protocol=protocol.name,
                    token=token,
                    supply_apy=apy,
                    timestamp=datetime.now()
                )
        return results

    async def get_best_yield(self, token: str) -> ProtocolYield:
        """Find highest yield for a token"""
```

**Success Criteria:**
- [ ] Can query yields from 3 protocols
- [ ] Yield comparison logic working
- [ ] Historical yield tracking implemented
- [ ] Performance < 5 seconds for full scan

---

### Sprint 3: Allocation Logic (2-3 days)

**Objectives:**
1. Build AllocationCalculator
2. Implement net yield calculation (gross APY - gas costs)
3. Add risk-adjusted optimization
4. Create rebalancing threshold logic

**Deliverables:**
```python
# src/strategies/allocation_calculator.py
class AllocationCalculator:
    async def calculate_net_yield(
        self,
        protocol: BaseProtocol,
        token: str,
        amount: Decimal,
        time_horizon_days: int = 30,
    ) -> NetYieldProjection:
        """Calculate net yield after all costs"""

        # Gross APY
        gross_apy = await protocol.get_supply_apy(token)

        # Gas costs
        entry_gas_cost = await self.estimate_entry_gas(protocol, token, amount)
        exit_gas_cost = await self.estimate_exit_gas(protocol, token, amount)
        total_gas_cost = entry_gas_cost + exit_gas_cost

        # Amortize gas over time horizon
        daily_gas_cost = total_gas_cost / time_horizon_days

        # Calculate net daily yield
        daily_gross_yield = (gross_apy / 365) * amount
        daily_net_yield = daily_gross_yield - daily_gas_cost

        # Annualized net APY
        net_apy = (daily_net_yield * 365) / amount

        return NetYieldProjection(
            gross_apy=gross_apy,
            net_apy=net_apy,
            total_gas_cost=total_gas_cost,
            break_even_days=total_gas_cost / daily_gross_yield,
            projected_30d_profit=daily_net_yield * 30,
        )
```

**Success Criteria:**
- [ ] Net yield calculation accurate
- [ ] Gas cost estimation working
- [ ] Risk scoring implemented
- [ ] Comprehensive unit tests

---

### Sprint 4: Transaction Sequencing (2-3 days)

**Objectives:**
1. Build TransactionSequenceBuilder
2. Implement multi-step execution with checkpoints
3. Add rollback handling
4. End-to-end rebalancing test

**Deliverables:**
```python
# src/blockchain/transaction_sequencer.py
class TransactionSequencer:
    async def execute_rebalance(
        self,
        from_protocol: BaseProtocol,
        to_protocol: BaseProtocol,
        amount: Decimal,
        token: str,
    ) -> RebalanceResult:
        """Execute multi-step rebalance with rollback capability"""

        # Build sequence
        steps = [
            ("withdraw", from_protocol.build_withdraw_tx),
            ("approve", to_protocol.build_approve_tx),
            ("supply", to_protocol.build_supply_tx),
        ]

        # Simulate entire sequence first
        simulation = await self.simulate_sequence(steps, amount, token)
        if not simulation.success:
            return RebalanceResult(executed=False, reason=simulation.failure_reason)

        # Check profitability
        if simulation.total_gas_cost > amount * Decimal("0.05"):  # 5% threshold
            return RebalanceResult(executed=False, reason="Gas cost too high")

        # Execute with checkpoints
        for step_name, build_tx_func in steps:
            tx = await build_tx_func(token, amount)

            # Use existing swap_executor security framework
            result = await self.wallet_manager.execute_transaction(tx)

            if not result["success"]:
                await self.rollback_previous_steps()
                return RebalanceResult(executed=False, reason=f"Failed at {step_name}")

        return RebalanceResult(executed=True, gas_used=simulation.total_gas_cost)
```

**Success Criteria:**
- [ ] Multi-step rebalance working
- [ ] Simulation prevents bad transactions
- [ ] Rollback logic tested
- [ ] Integration test on testnet

---

### Sprint 5: LangGraph Agent Orchestration (2-3 days)

**Objectives:**
1. Design agent workflow state machine
2. Implement scanning loop
3. Add decision logic
4. Build execution engine

**Deliverables:**
```python
# src/agents/yield_optimizer.py
from langgraph.graph import StateGraph, END

class YieldOptimizer:
    def __init__(
        self,
        protocols: List[BaseProtocol],
        wallet_manager: WalletManager,
        min_yield_improvement_bps: int = 100,  # 1%
    ):
        self.protocols = protocols
        self.wallet_manager = wallet_manager
        self.min_improvement = Decimal(min_yield_improvement_bps) / 10000

        # Build LangGraph workflow
        self.workflow = self.build_workflow()

    def build_workflow(self) -> StateGraph:
        workflow = StateGraph()

        # Define states
        workflow.add_node("scan", self.scan_yields)
        workflow.add_node("analyze", self.analyze_positions)
        workflow.add_node("decide", self.decide_rebalance)
        workflow.add_node("execute", self.execute_rebalance)
        workflow.add_node("report", self.generate_report)

        # Define edges
        workflow.add_edge("scan", "analyze")
        workflow.add_edge("analyze", "decide")
        workflow.add_conditional_edges(
            "decide",
            lambda state: "execute" if state.should_rebalance else "report"
        )
        workflow.add_edge("execute", "report")
        workflow.add_edge("report", END)

        workflow.set_entry_point("scan")

        return workflow.compile()

    async def run_optimization_cycle(self):
        """Run one complete optimization cycle"""
        result = await self.workflow.ainvoke({
            "timestamp": datetime.now(),
            "wallet_address": await self.wallet_manager.get_address(),
        })
        return result
```

**Success Criteria:**
- [ ] LangGraph workflow operational
- [ ] State transitions working
- [ ] Decision logic sound
- [ ] Error recovery implemented

---

### Sprint 6: Production Readiness (1-2 days)

**Objectives:**
1. Performance monitoring
2. Reporting dashboard
3. Documentation
4. First autonomous yield optimization run

**Deliverables:**
```python
# src/monitoring/performance_tracker.py
@dataclass
class PerformanceMetrics:
    total_yield_generated: Decimal
    average_net_apy: Decimal
    rebalances_executed: int
    gas_efficiency_ratio: Decimal  # yield / gas spent
    best_protocol: str
    diversification_score: float
```

**Success Criteria:**
- [ ] 48-hour autonomous operation successful
- [ ] All monitoring in place
- [ ] Documentation complete
- [ ] Positive net yield achieved

---

## Security Framework

### Reuse Existing Security (Phase 3)
Every transaction in yield optimization goes through:
1. ✅ Price validation (oracle check)
2. ✅ Gas estimation
3. ✅ Approval threshold check
4. ✅ Transaction simulation
5. ✅ Spending limit enforcement

### New Security Requirements

#### 1. Protocol Risk Scoring
```python
class ProtocolRiskAssessor:
    def calculate_risk_score(self, protocol: BaseProtocol) -> int:
        score = 100

        # Audit status (-40 if unaudited)
        if not protocol.is_audited:
            score -= 40

        # TVL assessment (-20 if < $10M)
        if protocol.tvl < 10_000_000:
            score -= 20

        # Age (-20 if < 30 days)
        if protocol.days_live < 30:
            score -= 20

        # Exploit history (-20 if exploited)
        if protocol.has_been_exploited:
            score -= 20

        return max(0, score)
```

#### 2. Position Limits
```python
# Conservative limits for Phase 3
MAX_POSITION_PER_PROTOCOL = Decimal("1000")  # $1k max
MAX_PROTOCOL_CONCENTRATION = Decimal("0.4")  # 40% of portfolio
MIN_POSITION_SIZE = Decimal("10")  # $10 minimum
MAX_DAILY_REBALANCES = 5  # Prevent over-trading
```

#### 3. Approval Management
```python
# CRITICAL: Never leave unlimited approvals
async def safe_approve_and_supply(protocol, token, amount):
    # Approve exact amount
    await protocol.approve(token, amount)

    try:
        # Supply funds
        await protocol.supply(token, amount)
    finally:
        # ALWAYS revoke remaining approval
        await protocol.approve(token, 0)
```

#### 4. Emergency Controls
```python
class EmergencyControls:
    paused: bool = False
    max_gas_price: int = 100  # gwei

    async def emergency_withdraw_all(self):
        """Withdraw from all protocols immediately"""
        for protocol in self.protocols:
            position = await protocol.get_position(self.wallet_address)
            if position.amount > 0:
                await protocol.withdraw(position.token, position.amount)
```

---

## Key Technical Patterns

### 1. Protocol Abstraction
All protocols implement the same interface, enabling:
- Easy addition of new protocols
- Consistent yield comparison
- Unified testing approach

### 2. Net Yield Focus
Always calculate returns after costs:
```
Net Yield = Gross APY - (Gas Costs / Position Size / Time)
```

### 3. Simulation Before Execution
Never execute without simulating:
```python
simulation = await sequencer.simulate_sequence(steps)
if simulation.success and simulation.profitable:
    result = await sequencer.execute_sequence(steps)
```

### 4. Rebalancing Thresholds
Only rebalance when:
- Yield improvement > 100 bps (1%)
- Expected profit > 3x gas cost
- Time since last rebalance > 24 hours

---

## Success Metrics

Track these KPIs from Day 1:

### Yield Performance
- Total yield generated (USD)
- Average net APY achieved
- Best performing protocol
- Yield vs benchmark (holding ETH)

### Operational Efficiency
- Rebalances executed
- Rebalances aborted (and why)
- Average gas per rebalance
- Gas efficiency ratio (yield/gas)

### Risk Management
- Max protocol exposure
- Diversification score
- Emergency withdrawals triggered
- Protocol incidents detected

### System Health
- Uptime percentage
- Error rate
- Average decision time
- Agent loop frequency

---

## Definition of Done

Phase 3 is complete when Mammon can:

1. ✅ Monitor yields across 3+ protocols autonomously
2. ✅ Calculate net returns including all costs accurately
3. ✅ Execute profitable rebalancing automatically
4. ✅ Track performance with full attribution
5. ✅ Operate safely for 48 hours without intervention
6. ✅ Generate positive net yield after all costs
7. ✅ Pass all security checks
8. ✅ Have comprehensive documentation

---

## Pre-Sprint Checklist

Before starting Sprint 1:

### Environment
- [ ] Create `phase3-yield-optimization` branch
- [ ] Set up yield tracking database tables
- [ ] Configure protocol RPC endpoints
- [ ] Update .env with protocol configs

### Research
- [ ] Document Morpho contract addresses (Base)
- [ ] Map Morpho lending pool structure
- [ ] Understand Morpho interest rate model
- [ ] Review Morpho security audits

### Safety
- [ ] Set initial position limits ($100 max)
- [ ] Configure emergency withdrawal procedures
- [ ] Set up monitoring alerts
- [ ] Create rollback procedures

### Testing
- [ ] Set up protocol mocking framework
- [ ] Create yield simulation tools
- [ ] Prepare integration test scenarios
- [ ] Build performance benchmarks

---

## Resources

### Protocol Documentation
- **Morpho**: https://docs.morpho.org/
- **Aave V3**: https://docs.aave.com/
- **Moonwell**: https://docs.moonwell.fi/

### Contract Addresses (Base Mainnet)
- Morpho: [To be researched in Sprint 1]
- Aave V3: [To be researched in Sprint 2]
- Moonwell: [To be researched in Sprint 2]

### Existing Codebase References
- Swap execution: `src/blockchain/swap_executor.py`
- Wallet management: `src/blockchain/wallet.py`
- Security framework: `src/security/`
- Gas estimation: `src/blockchain/gas_estimator.py`

---

## Phase 3 Timeline

**Total Duration**: 9-15 days

```
Week 1:
├── Sprint 1: Protocol foundation (1-2 days)
└── Sprint 2: Multi-protocol scanning (1-2 days)

Week 2:
├── Sprint 3: Allocation logic (2-3 days)
└── Sprint 4: Transaction sequencing (2-3 days)

Week 3:
├── Sprint 5: LangGraph orchestration (2-3 days)
└── Sprint 6: Production readiness (1-2 days)
```

**First Autonomous Yield Optimization**: Day 15 (end of Sprint 6)

---

## Next Steps

1. **Create Phase 3 branch**: `git checkout -b phase3-yield-optimization`
2. **Start Sprint 1**: Begin with BaseProtocol abstraction
3. **Daily commits**: Commit working code at end of each day
4. **Test thoroughly**: Write tests before implementation
5. **Document decisions**: Update this doc with learnings

---

**Ready to make Mammon a true yield optimization agent! 🚀**

**Status**: Phase 3 ready to begin
**Foundation**: Phases 1-3 complete (wallet, swaps, security)
**Objective**: Autonomous yield optimization across lending protocols
**Timeline**: 9-15 days to first autonomous operation
