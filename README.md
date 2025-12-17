# 💰 MAMMON - Autonomous DeFi Yield Optimizer

**Autonomous AI agent optimizing DeFi yields on Base network with x402 protocol integration**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/dependency-poetry-purple.svg)](https://python-poetry.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 🎯 Overview

MAMMON is an autonomous AI agent that:
- **Phase 1**: Optimizes YOUR DeFi yields across Base protocols
- **Phase 2**: Purchases premium data/strategies from other agents via x402
- **Phase 3**: Sells MAMMON's strategies to other agents via x402

Built for the emerging agent economy with security and autonomy as top priorities.

## ✨ Recent Achievements

### Phase 4 Sprint 5: Idle Capital Deployment ✅ COMPLETE (Dec 2025)

**Optimizer now detects and deploys idle capital automatically!** 💰

#### What's New
- ✅ **Idle Capital Detection**: Automatically detects USDC sitting idle in wallet
- ✅ **Best Yield Discovery**: Scans all protocols to find highest APY
- ✅ **Profitability Validation**: Checks deployment makes sense after gas costs
- ✅ **Autonomous Deployment**: Creates initial positions without manual intervention
- ✅ **Comprehensive Logging**: Full audit trail of deployment decisions

#### How It Works
1. **Detection**: Optimizer checks for idle USDC (minimum $10) when no positions exist
2. **Scanning**: Finds best yield opportunity across Aave, Moonwell, Morpho, Aerodrome
3. **Validation**: Profitability calculator ensures deployment beats gas costs
4. **Execution**: Creates deposit transaction (`from_protocol=None` → target protocol)
5. **Tracking**: Records new position in database for future rebalancing

#### Example Flow
```
💰 Detected idle capital: 100 USDC
📊 Best opportunity: Moonwell @ 4.48% APY
✅ Deployment profitable: $4.48/year, break-even in 40 days
🚀 Deploying 100 USDC → Moonwell
✅ Deployment successful! Gas: $0.50
```

#### Before vs After
| Before | After |
|--------|-------|
| ⚠️ No positions → exits early | 💰 No positions → checks for idle capital |
| Idle USDC earns 0% | Idle USDC deployed to best yield |
| Manual deployment required | Fully autonomous |

---

### Phase 4 Sprint 4: Tiered Wallet Security ✅ COMPLETE (Dec 2025)

**Production-ready three-tier wallet security architecture with attack detection!** 🔐

#### What's New
- ✅ **Three-Tier Wallets**: HOT (autonomous), WARM (manual approval), COLD (hardware)
- ✅ **Attack Detection**: EIP-7702 delegation and Permit2 hidden approval detection
- ✅ **Contract Whitelist**: 10+ Base protocols whitelisted (USDC, Aave, Moonwell, etc.)
- ✅ **Auto-Pause**: Hot wallet pauses itself on spending limit breach
- ✅ **Approval Server**: FastAPI dashboard for manual approval management
- ✅ **Event-Driven**: No polling - instant approval response

#### Wallet Tiers

| Tier | Max TX | Daily | Approval | Use Case |
|------|--------|-------|----------|----------|
| HOT | $500 | $1,000 | None (auto) | Day-to-day operations |
| WARM | $5,000 | $10,000 | 24h manual | Larger transactions |
| COLD | Unlimited | Unlimited | 168h hardware | Treasury operations |

#### Security Features
- **EIP-7702 Detection**: Blocks delegation authorization attacks
- **Permit2 Monitoring**: Detects hidden token approvals
- **Dangerous Functions**: Blocks selfdestruct, delegatecall, upgradeTo
- **Whitelist Enforcement**: Only known contracts allowed

#### Documentation
- [`docs/security.md`](docs/security.md) - Complete security architecture
- [`NEXT_SESSION_WALLET_SECURITY.md`](NEXT_SESSION_WALLET_SECURITY.md) - Implementation details

---

### Phase 3 Sprint 3: Complete Optimization Engine ✅ COMPLETE (Nov 2025)

**Production-ready decision-making system with profitability validation and risk assessment!** 🚀

#### What's New
- ✅ **Profitability Validation**: 4-gate system prevents unprofitable moves
- ✅ **Risk Assessment**: 7-factor risk scoring across protocols
- ✅ **Dual Strategies**: SimpleYield (aggressive) + RiskAdjusted (conservative)
- ✅ **OptimizerAgent**: Complete orchestration of optimization flow
- ✅ **81 Tests Passing**: >85% coverage on core components
- ✅ **Production Ready**: Mathematical proof of profitability before every move

#### The 4 Profitability Gates
Every rebalance must pass ALL 4 gates:
1. **APY Improvement** - Target APY > Current + 0.5% minimum
2. **Net Annual Gain** - Profit ≥ $10/year after all costs
3. **Break-Even Period** - Recover costs within 30 days
4. **Cost Ratio** - Total costs < 1% of position size

**Cost Components**: Gas (4 transactions) + Slippage + Protocol Fees

#### The 7 Risk Factors
1. Protocol Safety (0-40 pts) - Track record & security
2. TVL Adequacy (0-30 pts) - Pool depth
3. Utilization (0-30 pts) - Available liquidity
4. Position Size (0-30 pts) - Large position scrutiny
5. Swap Requirement (0-20 pts) - Token swap risk
6. Concentration (0-50 pts) - Portfolio concentration
7. Diversification (0-20 pts) - Protocol distribution

**Risk Levels**: LOW (0-25), MEDIUM (26-50), HIGH (51-75), CRITICAL (76-100)

#### Try the Demo
```bash
# See complete optimization engine in action
poetry run python scripts/demo_sprint3.py
```

**Demonstrates**:
- Multi-protocol yield scanning (real Base mainnet data)
- SimpleYield optimization (100% to best opportunity)
- RiskAdjusted optimization (diversified allocation)
- Profitability gates blocking unprofitable moves
- Risk assessment scores across protocols
- Strategy comparison (aggressive vs conservative)

#### Documentation
- [`PHASE3_SPRINT3_COMPLETE.md`](PHASE3_SPRINT3_COMPLETE.md) - Complete Sprint 3 report
- [`docs/profitability_gates.md`](docs/profitability_gates.md) - Profitability system guide
- [`.env.example`](.env.example) - Updated with profitability configuration

#### Test Results
```
ProfitabilityCalculator: 26 tests, 98% coverage ✅
RiskAssessorAgent:       27 tests, 98% coverage ✅
Strategies (both):       20 tests, 88% coverage ✅
OptimizerAgent:          8 tests,  77% coverage ✅
Total:                   81 tests passing in ~1.2s
```

---

## Phase 2A Achievements

### Sprint 4 Priority 2: Premium RPC Integration ✅ COMPLETE (Nov 2025)

**Production-ready RPC infrastructure deployed with excellent performance!** 🚀

#### What's New
- ✅ **Premium RPC Live**: Alchemy deployed at 50% with Alchemy + QuickNode backup
- ✅ **Excellent Latency**: 25-70ms p95 (< 100ms target exceeded)
- ✅ **100% Reliability**: 24+ hours monitoring, zero failures
- ✅ **Circuit Breaker**: Automatic failover prevents endpoint hammering
- ✅ **Rate Limiting**: Stays within provider limits, tracks costs
- ✅ **Security Hardened**: API keys never logged (URL sanitization)
- ✅ **Monitoring Tools**: Real-time usage tracking and health checks

#### Performance Results (Production at 50%)
```
Base Mainnet:     p95 = 27-33ms  ✅ Excellent
Arbitrum Sepolia: p95 = 12-159ms ✅ Good
Success Rate:     100% (100/100) ✅ Production Ready
Cost:             Free tier       ✅ Within limits
```

#### Try It Yourself
```bash
# Run performance tests
poetry run python scripts/test_rpc_performance.py

# Monitor RPC usage anytime
poetry run python scripts/monitor_rpc_usage.py
```

**Documentation**:
- [`docs/rpc_configuration.md`](docs/rpc_configuration.md) - RPC setup guide
- [`docs/monitoring_guide.md`](docs/monitoring_guide.md) - 24-48h monitoring schedule
- [`docs/sprint4_priority2_complete.md`](docs/sprint4_priority2_complete.md) - Full completion report
- [`docs/test_results_sprint4_priority2.md`](docs/test_results_sprint4_priority2.md) - Test results

---

### Sprint 4 Priority 1: Local Wallet ✅ COMPLETE (Nov 2025)

**First real transaction executed successfully!** 🎉

- ✅ **BIP-39 Seed Phrase Wallet** with thread-safe nonce management
- ✅ **Transaction Simulation** before execution (prevents failures)
- ✅ **EIP-1559 Gas Estimation** with tiered buffers
- ✅ **First Real TX**: `0xbe373fa11fdc600dc8c0741b5735709219081dee31efceae0cf68018aba09791`
- ✅ **Security**: All 6 security layers tested and passing

---

### Sprint 3: Real Protocol Integration ✅ COMPLETE (Nov 2025)

**Real blockchain protocol integration implemented!**

- ✅ **14,049 Live Pools**: Query real Aerodrome pools from Base mainnet
- ✅ **Multi-Network Support**: Web3 infrastructure for Base + Arbitrum Sepolia
- ✅ **Token Utilities**: ERC20 balance/metadata queries across networks
- ✅ **Production Data**: Real reserves, fees, and token data from blockchain
- ✅ **Read-Only Safety**: Zero risk queries, no transaction execution

### Try the Demo

See all Phase 1C features in action:
```bash
poetry run python scripts/demo_phase1c.py
```

This demonstrates:
- ✅ Multi-network connectivity (Base + Arbitrum)
- ✅ Real Aerodrome pool queries (14,049 pools available)
- ✅ ERC20 token utilities (USDC, WETH)
- ✅ Connection caching performance (~5x speedup)
- ✅ Safety features and warnings

### Code Examples

```python
# Query real Aerodrome pool data from Base mainnet
from src.protocols.aerodrome import AerodromeProtocol

protocol = AerodromeProtocol({"network": "base-mainnet", "dry_run_mode": False})
pools = await protocol.get_pools()  # Returns real pool data!
print(f"Found {len(pools)} pools with ${sum(p.tvl for p in pools):,.0f} TVL")
```

```python
# Query ERC20 token metadata
from src.tokens import ERC20Token

usdc = ERC20Token("base-mainnet", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
print(f"{usdc.get_name()}: {usdc.get_symbol()} ({usdc.get_decimals()} decimals)")
# Output: USD Coin: USDC (6 decimals)
```

### Performance Benchmarks

```bash
# Run cache performance benchmarks
poetry run python scripts/benchmark_cache_performance.py

# Run extended benchmarks (may hit rate limits)
poetry run python scripts/benchmark_extended.py
```

**See Sprint 3 Documentation**:
- [`docs/phase1c_sprint3_report.md`](docs/phase1c_sprint3_report.md) - Full Sprint 3 report
- [`docs/web3_integration_guide.md`](docs/web3_integration_guide.md) - Web3 usage guide
- [`docs/known_issues_sprint3.md`](docs/known_issues_sprint3.md) - Known issues & solutions

## 🏗️ Architecture

- **Orchestration**: LangGraph for stateful agent workflows
- **Blockchain**: Coinbase AgentKit (CDP SDK) for Base network
- **AI**: Claude API (Anthropic) for intelligent decision-making
- **Payments**: x402 protocol for agent-to-agent transactions
- **Database**: SQLite (MVP) → PostgreSQL (production)
- **Frontend**: Streamlit dashboard for monitoring and control

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Poetry package manager
- Coinbase CDP API credentials
- Anthropic API key
- Base network RPC access

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/kpjmd/Mammon.git
   cd Mammon
   ```

2. **Install Poetry** (if not already installed)
   ```bash
   pip install poetry
   ```

3. **Install dependencies**
   ```bash
   poetry install
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

5. **Run setup script**
   ```bash
   poetry run python scripts/setup.py
   ```

### Configuration

Edit `.env` with your credentials:

```bash
# Blockchain Configuration
CDP_API_KEY=your_coinbase_cdp_api_key
CDP_API_SECRET=your_coinbase_cdp_secret
WALLET_SEED=your_wallet_seed_phrase  # NEVER commit!
BASE_RPC_URL=https://sepolia.base.org  # Start with testnet

# AI Configuration
ANTHROPIC_API_KEY=your_anthropic_api_key

# Security Limits (USD values)
MAX_TRANSACTION_VALUE_USD=1000
DAILY_SPENDING_LIMIT_USD=5000
APPROVAL_THRESHOLD_USD=100
X402_DAILY_BUDGET_USD=50

# Environment
ENVIRONMENT=development  # development, staging, production
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

## 🏃 Running MAMMON

### Run the Dashboard

```bash
poetry run streamlit run dashboard/app.py
```

Visit http://localhost:8501 to view the dashboard.

### Run Tests

```bash
# All tests
poetry run pytest

# With coverage
poetry run pytest --cov=src --cov-report=html

# Specific test file
poetry run pytest tests/unit/test_validators.py
```

### Run Type Checking

```bash
poetry run mypy src/
```

### Run Linting

```bash
poetry run ruff check src/
poetry run black src/
```

## 🎬 First Run Experience

When you run tests for the first time, here's what to expect:

### Initial Test Run

```bash
$ poetry run pytest -v

============================= test session starts ==============================
platform darwin -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0
cachedir: .pytest_cache
rootdir: /Users/kpj/Agents/Mammon
configfile: pyproject.toml
testpaths: tests
plugins: asyncio-0.24.0, anyio-4.11.0, cov-6.3.0
asyncio: mode=Mode.STRICT
collecting ... collected 18 items

tests/integration/test_database.py::test_database_creation PASSED        [  5%]
tests/unit/test_config.py::test_settings_validation PASSED               [ 11%]
tests/unit/test_config.py::test_environment_validation PASSED            [ 16%]
tests/unit/test_config.py::test_wallet_seed_validation_required PASSED   [ 22%]
tests/unit/test_config.py::test_wallet_seed_validation_empty PASSED      [ 27%]
tests/unit/test_config.py::test_wallet_seed_validation_whitespace PASSED [ 33%]
tests/unit/test_config.py::test_wallet_seed_validation_placeholder PASSED [ 38%]
tests/unit/test_config.py::test_wallet_seed_validation_invalid_bip39 PASSED [ 44%]
tests/unit/test_config.py::test_wallet_seed_validation_wrong_word_count PASSED [ 50%]
tests/unit/test_config.py::test_wallet_seed_validation_valid_12_words PASSED [ 55%]
tests/unit/test_config.py::test_wallet_seed_validation_valid_24_words PASSED [ 61%]
tests/unit/test_config.py::test_wallet_seed_strips_whitespace PASSED     [ 66%]
tests/unit/test_validators.py::test_validate_ethereum_address_valid PASSED [ 72%]
tests/unit/test_validators.py::test_validate_ethereum_address_invalid_length PASSED [ 77%]
tests/unit/test_validators.py::test_validate_amount_positive PASSED      [ 83%]
tests/unit/test_validators.py::test_validate_amount_negative PASSED      [ 88%]
tests/unit/test_validators.py::test_validate_token_symbol_valid PASSED   [ 94%]
tests/unit/test_validators.py::test_validate_token_symbol_invalid PASSED [100%]

================================ tests coverage ================================
...
============================== 18 passed in 1.2s ===============================
```

### What This Means

- ✅ **18 tests passing**: Core infrastructure and security validations working
- 📊 **~20% coverage**: Normal for initial stub implementation (will increase with development)
- 🔒 **Config tests passing**: All security validations functioning correctly
- 🔐 **Wallet seed tests passing**: BIP39 validation working as expected
- 🏗️ **Integration test passing**: Database setup successful

### Common First-Run Issues

#### 1. Missing .env file
```
FileNotFoundError: .env file not found
```
**Solution:**
```bash
cp .env.example .env
# Then edit .env with your real credentials
```

#### 2. Invalid API Keys
```
ValidationError: cdp_api_key must be set to a real value, not a placeholder
```
**Solution:** Edit `.env` and replace placeholder values with real API keys:
- Get Coinbase CDP credentials at: https://portal.cdp.coinbase.com/
- Get Anthropic API key at: https://console.anthropic.com/

#### 3. Missing Wallet Seed
```
ValidationError: wallet_seed is required. Generate a BIP39 seed phrase
```
**Solution:** Generate a **testnet-only** seed phrase:
```python
# Generate 12-word seed (testnet only!)
python -c "from bip_utils import Bip39MnemonicGenerator; print(Bip39MnemonicGenerator().FromWordsNumber(12))"
```

⚠️ **CRITICAL SECURITY WARNINGS:**
- **NEVER use online generators** for real wallets with actual funds
- **NEVER commit your seed phrase** to version control
- **Start with testnet** (Base Sepolia) - configured by default
- **Keep backups** of your seed phrase in a secure location

#### 4. Invalid BIP39 Seed Phrase
```
ValidationError: Invalid BIP39 seed phrase: ...
  - Found 8 words (expected 12, 15, 18, 21, or 24)
```
**Solution:** Ensure your seed phrase:
- Has exactly 12, 15, 18, 21, or 24 words
- Uses only words from the [BIP39 wordlist](https://github.com/bitcoin/bips/blob/master/bip-0039/english.txt)
- Has no typos or extra spaces
- Has valid checksum (automatically checked)

#### 5. Import Errors
```
ModuleNotFoundError: No module named 'pydantic_settings'
```
**Solution:**
```bash
poetry install
```

### Next Steps After First Run

Once all tests pass:

1. **Verify Configuration**
   ```bash
   poetry run python -c "from src.utils.config import get_settings; print('✅ Config loaded successfully')"
   ```

2. **Start the Dashboard**
   ```bash
   poetry run streamlit run dashboard/app.py
   ```
   Visit http://localhost:8501

3. **Begin Development**
   - Follow `TODO.MD` for implementation roadmap
   - Start with blockchain integration (CDP wallet)
   - Test everything on Base Sepolia testnet
   - Never skip security checks!

## 📁 Project Structure

```
mammon/
├── src/                    # Source code
│   ├── agents/            # LangGraph agent definitions
│   ├── protocols/         # Protocol integrations (Aerodrome, Morpho, etc.)
│   ├── blockchain/        # Blockchain interactions (CDP SDK)
│   ├── x402/             # x402 protocol integration
│   ├── data/             # Database models and ORM
│   ├── strategies/        # Yield optimization strategies
│   ├── security/         # Security components (limits, approval, audit)
│   ├── utils/            # Utilities (config, logging, validation)
│   └── api/              # API clients (Claude, protocols)
├── dashboard/             # Streamlit dashboard
├── tests/                # Test suite
├── scripts/              # Utility scripts
├── docs/                 # Documentation
├── .env.example          # Environment template
├── pyproject.toml        # Poetry dependencies
├── CLAUDE.MD             # Project context for Claude
└── TODO.MD               # Development roadmap
```

## 🔒 Security

MAMMON is built with security as the **top priority**:

### Multi-Layered Protection
1. **Configuration Security**: Pydantic validation of all settings
2. **Input Validation**: All external data validated
3. **Spending Limits**: Per-transaction, daily, weekly, monthly limits
4. **Approval Workflows**: Manual approval for transactions above threshold
5. **Audit Logging**: Immutable audit trail of all operations

### Security Rules

**NEVER**:
- ❌ Commit secrets or .env files
- ❌ Run on mainnet without extensive testnet testing
- ❌ Skip input validation
- ❌ Ignore security warnings

**ALWAYS**:
- ✅ Test on Base Sepolia testnet first
- ✅ Review approval requests carefully
- ✅ Monitor audit logs
- ✅ Keep spending limits conservative

See [docs/security.md](docs/security.md) for complete security documentation.

## 📊 Supported Protocols (Phase 1)

1. **Aerodrome Finance** - Primary DEX on Base ($602M TVL)
2. **Morpho** - Coinbase-promoted lending protocol
3. **Moonwell** - Multi-chain lending (Base/Moonbeam/Moonriver)
4. **Aave V3** - Battle-tested lending protocol
5. **Beefy Finance** - Auto-compounding yield aggregator

## 🛣️ Roadmap

### ✅ Phase 0: Setup & Infrastructure (Current)
- [x] Project structure
- [x] Configuration system
- [x] Security foundation
- [x] Database models
- [x] Basic dashboard
- [ ] Protocol integrations
- [ ] Agent implementation

### 🔄 Phase 1: Core Yield Optimizer
- [ ] CDP wallet integration
- [ ] Protocol yield scanning
- [ ] Risk assessment
- [ ] Rebalancing execution
- [ ] Approval workflows
- [ ] Performance tracking
- [ ] Full testnet testing

### 🔮 Phase 2: x402 Client
- [ ] Service discovery
- [ ] Payment execution
- [ ] Premium data integration
- [ ] ROI tracking

### 🌟 Phase 3: x402 Server
- [ ] Service registration
- [ ] Strategy packaging
- [ ] Revenue tracking
- [ ] Pricing optimization

## 📚 Documentation

- [Architecture](docs/architecture.md) - System design and components
- [Security](docs/security.md) - Security model and best practices
- [API](docs/api.md) - Internal APIs and interfaces
- [TODO](TODO.MD) - Detailed development roadmap

## 🧪 Development

### Adding a New Protocol

1. Create protocol integration in `src/protocols/`
2. Inherit from `BaseProtocol`
3. Implement all required methods
4. Add tests in `tests/unit/protocols/`
5. Update documentation

See [docs/api.md](docs/api.md) for interface specifications.

### Adding a New Strategy

1. Create strategy in `src/strategies/`
2. Inherit from `BaseStrategy`
3. Implement analysis and allocation logic
4. Add tests
5. Register in orchestrator

## 🤝 Contributing

This is a personal project, but feedback and suggestions are welcome!

### Development Workflow

1. Read `CLAUDE.MD` for project context
2. Check `TODO.MD` for current phase objectives
3. Write tests first (TDD)
4. Implement with security in mind
5. Run full test suite
6. Update documentation

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

## 📖 Resources

- [Coinbase AgentKit Docs](https://docs.cdp.coinbase.com/agentkit/docs/welcome)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [x402 Protocol](https://github.com/coinbase/x402)
- [Base Network](https://docs.base.org/)
- [Anthropic Claude](https://docs.anthropic.com/)

## ⚠️ Disclaimer

MAMMON is experimental software under active development. Use at your own risk.

- **Not Financial Advice**: MAMMON does not provide financial advice
- **No Guarantees**: Yields and performance are not guaranteed
- **Smart Contract Risk**: Protocols may have bugs or exploits
- **Market Risk**: DeFi markets are volatile and risky
- **Test First**: Always test thoroughly on testnet before mainnet

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- Coinbase for AgentKit and Base network
- Anthropic for Claude API
- The DeFi protocol teams building on Base
- The emerging agent economy ecosystem

---

**Built for the Agent Economy** 🤖💰

*Remember: We're not just building a tool, we're building an autonomous economic actor in the agent economy. Code accordingly.*
