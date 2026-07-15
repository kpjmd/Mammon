# MAMMON — State Briefing

Prepared as ground-truth context for a strategic-direction review (intended for a separate Fable 5 session). Everything below is based on direct code inspection, on-chain verification (BaseScan), and SQL queries against `data/mammon.db` — not on the project's own prose reports, several of which overstate results (see "Still aspirational" below).

## What's verified real

- **Profitability gate**: 4 real gates (APY improvement, min $ annual gain, break-even days, cost %) with real cost accounting (gas, slippage, protocol fees). Genuinely enforced in the default autonomous path. `src/strategies/profitability_calculator.py`
- **Security controls**: spending limits, an approval workflow, and EIP-7702/Permit2/dangerous-selector transaction validation backed by a contract whitelist are all genuinely implemented and wired into every outgoing transaction. `src/security/`, `src/blockchain/wallet.py`
- **Tiered wallet security** (hot/warm/cold): built after a real incident — see below.
- **One real on-chain rebalance**: executed and BaseScan-confirmed (Dec 1, 2025, Aave V3 → Moonwell, $200.05 USDC). This contradicts a "zero rebalances ever executed" framing — though the same run had 5 consecutive failures immediately after, and the wallet that executed it was drained the next day.

**Security incident (handled)**: the wallet from the Dec 1 rebalance was drained on Dec 2, 2025 — its seed phrase was stored in plaintext, world-readable files. The tiered hot/warm/cold wallet architecture, contract whitelist, and EIP-7702/Permit2 detection appear to be the direct remediation for this. Already confirmed remediated as of this session — not an open item.

## Fixed this session (correctness bugs that undermined the "profitability moat" claim)

1. `current_apy` was a **hardcoded placeholder** (`Decimal("3.5")`) feeding the live profitability gate, regardless of the position's actual APY. Now uses the recommendation's real current APY.
2. `requires_swap` was a **self-comparison** (`token != token`), always `False` by accident rather than by design. Made explicit: the system only supports same-token rebalances (swaps raise `NotImplementedError` everywhere), so this is now honest rather than coincidentally-correct.
3. Yield comparison **wasn't token-aware** — a protocol's APY could be its WETH-pool rate while being compared against a USDC position. Now filtered to a single `target_token` (USDC by default) end-to-end.
4. The `Transaction` and `Decision` SQL tables were defined but **never written to** — `scripts/daily_check.py`'s "4-gate blocks" stat always reported 0/0/0/0. Now populated on every real transaction and every gate decision (accept/reject, with rationale and risk score).
5. `RiskAssessorAgent`'s CRITICAL/HIGH-risk blocking was **dead code** on the default autonomous path. Now wired into both the rebalance cycle and idle-capital deployment.
6. Morpho was scanned and dispatchable for idle-capital deployment despite its deposit/withdraw raising `NotImplementedError` — a live failure trap. Now excluded via a protocol allowlist.
7. Deleted two fully-stubbed, orphaned agent classes (`OrchestratorAgent`, `ExecutorAgent`) superseded by `ScheduledOptimizer` / `RebalanceExecutor`.

None of this has been re-validated live yet — the fixes are verified by unit/integration tests and a local end-to-end dry run, not by a fresh extended live run on the droplet.

## Still aspirational / not started

- **x402** (client/server/discovery): 100% `NotImplementedError` stubs. No SDK dependency in `pyproject.toml`. Not wired into any decision flow. `docs/architecture.md` itself labels it "Future Architecture."
- **ERC-8004, "agentic wallet," "agent registry"**: zero references anywhere in the codebase — nothing started.
- Several root-level report docs (`14_DAY_VALIDATION_REPORT.md`, `COMPETITIVE_PROOF.md`) frame "0 rebalances attempted during the validation window" as "100% profitability rate" / "335 opportunities correctly avoided" — a vacuous-truth framing, since nothing was actually exercised. Not evidence of a validated moat.

## Current stack

- LangGraph orchestration, Coinbase CDP SDK (Base network), Claude API for decisions, SQLite via SQLAlchemy ORM, Streamlit dashboard.
- `coinbase-agentkit` is a pinned dependency but not actually imported/used anywhere in `src/` — worth confirming before assuming any AgentKit-based capability already exists.
- Autonomous loop runs on a DigitalOcean droplet (178.62.235.178); `scripts/daily_check.py` is a read-only health-check script, now meaningful post-fix since it reads real data.

## Open strategic questions

1. Does a hand-rolled DeFi yield optimizer remain a defensible product now that far more capable general-purpose models are broadly available? Does the differentiator shift entirely to reliability/execution-safety/track record rather than "smarter yield picking"?
2. Does Coinbase's Agentic Wallet (gasless transactions, built-in spending limits, native x402 integration) replace the hand-rolled tiered-wallet-security system just built, or complement it? What's the realistic migration cost/benefit?
3. With x402 and ERC-8004 both at zero, what's a realistic sequencing — is marketplace participation (selling MAMMON's strategy signal to other agents) still Phase 2/3 material, or should near-term focus stay on proving the yield-optimization core works reliably over an extended live window before expanding scope?
4. Given the one real rebalance to date was followed by a wallet compromise, what would "production ready" actually require before deploying with meaningful capital again?
