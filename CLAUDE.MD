# MAMMON - Autonomous DeFi Yield Optimizer

## Project Overview
MAMMON is an autonomous AI agent that optimizes DeFi yields on Base network, with x402 protocol integration for participating in the emerging agent economy. Built for personal use initially, architected to sell services to other agents.

**Repository**: https://github.com/kpjmd/Mammon.git
**Primary Chain**: Base (Coinbase L2)
**Sister Agent**: Rake (future)

## Core Mission
1. **Phase 1**: Optimize YOUR DeFi yields across Base protocols
2. **Phase 2**: Purchase premium data/strategies from other agents via x402
3. **Phase 3**: Sell MAMMON's strategies to other agents via x402

## Technology Stack

### Core Framework
- **Orchestration**: LangGraph (stateful agent workflows)
- **Blockchain**: Coinbase AgentKit (CDP SDK for Base)
- **AI**: Claude API (Anthropic) for decision-making
- **Payments**: x402 client library for agent-to-agent transactions
- **Database**: SQLite for state/history (Postgres later for production)
- **Frontend**: Streamlit (MVP dashboard)

### Supported Protocols (Phase 1)
1. **Aerodrome Finance** - Primary DEX on Base ($602M TVL)
2. **Morpho** - Coinbase-promoted lending protocol
3. **Moonwell** - Multi-chain lending (Base/Moonbeam/Moonriver)
4. **Aave V3** - Battle-tested lending
5. **Beefy Finance** - Auto-compounding yield aggregator

### Language & Environment
- **Language**: Python 3.11+
- **Package Manager**: Poetry
- **Environment**: .env for secrets (NEVER commit)
- **Testing**: pytest with >80% coverage requirement
- **Linting**: ruff + black for code formatting
- **Type Checking**: mypy (strict mode)

## Architecture Principles

### Security First (NON-NEGOTIABLE)
```
CRITICAL SECURITY RULES:
1. NEVER store private keys in code or version control
2. ALL wallet operations require explicit user approval above threshold
3. Spending limits enforced at multiple layers
4. Input validation on ALL external data
5. Rate limiting on API calls
6. Audit trail for every transaction decision
7. Fail-safe defaults (deny by default)
8. Regular security reviews before each phase
```

### Code Quality Standards
- **DRY**: Don't Repeat Yourself - abstract common patterns
- **SOLID**: Single responsibility, Open/closed, Liskov substitution, Interface segregation, Dependency inversion
- **Clean Code**: Self-documenting with minimal comments needed
- **Type Safety**: Full type hints, mypy strict mode
- **Error Handling**: Explicit exception handling, no silent failures
- **Logging**: Structured logging with appropriate levels
- **Testing**: Unit tests for business logic, integration tests for blockchain interactions

### Project Structure
```
mammon/
├── src/
│   ├── agents/              # LangGraph agent definitions
│   │   ├── orchestrator.py  # Main agent coordinator
│   │   ├── yield_scanner.py # Protocol yield monitoring
│   │   ├── risk_assessor.py # Position risk analysis
│   │   └── executor.py      # Transaction execution
│   ├── protocols/           # Protocol integrations
│   │   ├── base.py          # Abstract protocol interface
│   │   ├── aerodrome.py
│   │   ├── morpho.py
│   │   ├── moonwell.py
│   │   ├── aave.py
│   │   └── beefy.py
│   ├── blockchain/          # Blockchain interactions
│   │   ├── wallet.py        # CDP wallet management
│   │   ├── transactions.py  # Transaction builder/signer
│   │   └── monitor.py       # Chain monitoring
│   ├── x402/                # x402 protocol integration
│   │   ├── client.py        # x402 payment client
│   │   ├── server.py        # x402 service provider (Phase 3)
│   │   └── discovery.py     # Service discovery
│   ├── data/                # Data management
│   │   ├── database.py      # SQLite ORM
│   │   ├── cache.py         # Response caching
│   │   └── models.py        # Data models
│   ├── strategies/          # Yield strategies
│   │   ├── base_strategy.py # Abstract strategy
│   │   ├── simple_yield.py  # APY-based strategy
│   │   └── risk_adjusted.py # Risk-adjusted returns
│   ├── security/            # Security components
│   │   ├── approval.py      # Transaction approval logic
│   │   ├── limits.py        # Spending limits
│   │   └── audit.py         # Audit logging
│   ├── utils/               # Utilities
│   │   ├── config.py        # Configuration management
│   │   ├── logger.py        # Structured logging
│   │   └── validators.py    # Input validation
│   └── api/                 # API interfaces
│       ├── claude_client.py # Claude API wrapper
│       └── protocol_apis.py # External API clients
├── dashboard/               # Streamlit dashboard
│   └── app.py
├── tests/                   # Test suite
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── scripts/                 # Utility scripts
│   ├── setup.py            # First-time setup
│   └── deploy.py           # Deployment scripts
├── docs/                    # Documentation
│   ├── architecture.md
│   ├── security.md
│   └── api.md
├── .env.example            # Environment template
├── .gitignore
├── pyproject.toml          # Poetry dependencies
├── claude.md               # This file
├── todo.md                 # Development roadmap
└── README.md
```

## Development Workflow

### Before Starting Any Feature
1. Read todo.md for current phase objectives
2. Review relevant architecture docs
3. Write tests FIRST (TDD approach)
4. Implement with security in mind
5. Run full test suite
6. Update documentation
7. Commit with clear message

### Git Commit Convention
```
feat: Add new feature
fix: Bug fix
sec: Security improvement
refactor: Code refactoring
test: Add/update tests
docs: Documentation update
chore: Maintenance tasks
```

### Environment Variables (Never Commit)
```
# Blockchain
CDP_API_KEY=
CDP_API_SECRET=
WALLET_SEED=
BASE_RPC_URL=

# AI
ANTHROPIC_API_KEY=

# Limits (Safety Rails)
MAX_TRANSACTION_VALUE_USD=
DAILY_SPENDING_LIMIT_USD=
APPROVAL_THRESHOLD_USD=

# x402
X402_SERVICE_WALLET=
X402_PRICING_CONFIG=

# Monitoring
LOG_LEVEL=
ALERT_WEBHOOK=
```

## Decision-Making Framework for Claude Code

When building features, Claude Code should:

1. **Security First**: Before implementing ANY financial logic, ask:
   - Can this lose user funds?
   - Are all inputs validated?
   - Is there an approval mechanism?
   - Are there spending limits?

2. **Scalability**: Design for future:
   - Easy to add new protocols
   - Easy to add new strategies
   - Easy to add new x402 services
   - Database schema supports growth

3. **Observability**: Every important action should:
   - Log with context
   - Update state in database
   - Be auditable later
   - Provide user visibility

4. **Fail Gracefully**: 
   - Network errors? Retry with backoff
   - API limits? Queue and rate limit
   - Insufficient funds? Alert user
   - Unexpected state? Safe mode

## Testing Requirements

### Unit Tests (>80% coverage)
- All business logic functions
- Strategy calculations
- Risk assessment algorithms
- Input validators

### Integration Tests
- Protocol API interactions (use testnet)
- Wallet operations (use test wallet)
- Database operations
- x402 transactions (mock initially)

### Security Tests
- Spending limit enforcement
- Approval requirement validation
- Input sanitization
- Rate limiting

## Phase 1 Success Criteria

MAMMON Phase 1 is complete when:
- [ ] Can connect to Base network (testnet first)
- [ ] Can check wallet balance
- [ ] Can query yields from all 5 protocols
- [ ] Can calculate optimal rebalance
- [ ] Can execute ONE test transaction with approval
- [ ] Has spending limits enforced
- [ ] Logs all decisions to database
- [ ] Has working Streamlit dashboard
- [ ] Sends daily summary report
- [ ] Has >80% test coverage
- [ ] All security checks pass
- [ ] Documentation is complete

## Key Principles for Claude Code

1. **Ask Before Risky Changes**: If unsure about security implications, ASK
2. **No Shortcuts**: Write proper tests, handle errors, validate inputs
3. **Document Decisions**: Complex logic needs comments explaining WHY
4. **Use Type Hints**: Every function needs proper type annotations
5. **Small Commits**: Atomic changes that can be reviewed
6. **Think Future**: Will this work when we add 20 more protocols?

## Common Pitfalls to Avoid

❌ Hardcoding values that should be config
❌ Ignoring error cases
❌ Missing input validation
❌ Forgetting to log important events
❌ Not testing edge cases
❌ Committing secrets
❌ Skipping type hints
❌ Writing functions >50 lines
❌ Not handling async/await properly
❌ Missing database migrations

## Resources

- **Coinbase AgentKit**: https://docs.cdp.coinbase.com/agentkit/docs/welcome
- **LangGraph**: https://langchain-ai.github.io/langgraph/
- **x402 Protocol**: https://github.com/coinbase/x402
- **Base Network**: https://docs.base.org/
- **Protocol Docs**: (Add as we integrate)

## Notes for Future Phases

### Phase 2 (x402 Client)
- Implement service discovery
- Add budget management for x402 purchases
- Track ROI of paid services
- Build service evaluation system

### Phase 3 (x402 Server)
- Expose MAMMON strategies as paid service
- Implement pricing engine
- Add revenue tracking
- Build reputation system

### Sister Agent: RAKE
- Separate repo: github.com/kpjmd/Rake
- Complementary strategies
- Shared infrastructure
- Cross-agent communication

---

**Remember**: We're not just building a tool, we're building an autonomous economic actor in the agent economy. Code accordingly.
