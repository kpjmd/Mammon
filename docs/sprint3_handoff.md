# Phase 1C Sprint 3 - Handoff Document

**Date**: 2025-11-04
**From**: Phase 1C Sprint 2 (Complete)
**To**: Phase 1C Sprint 3 (Arbitrum Sepolia Integration)

---

## Executive Summary

Sprint 2 successfully delivered architectural foundations with 90%+ test coverage on new code. Sprint 3 will implement **real Aerodrome protocol integration on Arbitrum Sepolia testnet**, replacing mock data with actual on-chain queries.

---

## Sprint 2 Achievements (Context)

### What Was Delivered
1. ✅ **Multi-network configuration** - 4 networks (Base + Arbitrum, mainnet + testnet)
2. ✅ **Price oracle interface** - Flexible, swappable price sources
3. ✅ **Approval workflow** - Manual authorization for high-value transactions
4. ✅ **Comprehensive testing** - 193 passing tests (up from 53)

### Key Metrics
- **48% overall coverage** (31% → 48%)
- **90%+ coverage on Sprint 2 modules**
- **193/193 tests passing**
- **Zero regressions**
- **100% backward compatible**

### Critical Files
- `src/utils/networks.py` - Network registry (95% coverage)
- `src/data/oracles.py` - Price oracle interface (95% coverage)
- `src/security/approval.py` - Approval workflow (80% coverage)
- `src/protocols/aerodrome.py` - Ready for real integration

---

## Sprint 3 Objective

**Goal**: Implement real Aerodrome protocol integration on Arbitrum Sepolia, replacing mock pool data with actual on-chain queries.

**Why Arbitrum Sepolia?**
- Aerodrome has testnet deployment (needs verification)
- Free testnet ETH available from faucets
- Safe environment for testing real protocol interaction
- Multi-network architecture already supports it

---

## Sprint 3 Tasks

### Phase 1: Research (2-4 hours)

**Aerodrome Protocol Investigation**:
1. Search for Aerodrome deployment on Arbitrum Sepolia
   - Check Aerodrome official docs
   - Search GitHub for testnet addresses
   - Check Arbitrum Sepolia block explorers
2. Find key contract addresses:
   - Router contract (for swaps)
   - Factory contract (for pool creation)
   - Example pool addresses
3. Locate testnet resources:
   - Arbitrum Sepolia faucet (for ETH)
   - Test token faucets (USDC, WETH, etc.)
   - Aerodrome documentation/SDK

**Expected Outcome**: Document with:
- Contract addresses (if testnet deployment exists)
- OR alternative approach if no testnet deployment
- Faucet links
- Setup instructions

### Phase 2: Implementation (4-6 hours)

**Add Web3 Integration**:
1. Add dependencies to `pyproject.toml`:
   ```toml
   [tool.poetry.dependencies]
   web3 = "^6.11.0"  # For contract interaction
   eth-abi = "^4.0.0"  # For ABI encoding/decoding
   ```

2. Create Web3 provider utility:
   ```python
   # src/utils/web3_provider.py
   from web3 import Web3
   from src.utils.networks import get_network

   def get_web3_provider(network_id: str) -> Web3:
       network = get_network(network_id)
       return Web3(Web3.HTTPProvider(network.rpc_url))
   ```

**Implement Real Pool Queries**:
1. Update `src/protocols/aerodrome.py`:
   - Add contract ABI (Router, Factory, Pool)
   - Implement real `get_pools()` using Web3
   - Query actual TVL and APY from contracts
   - Handle RPC errors gracefully

2. Example implementation:
   ```python
   async def get_pools(self) -> List[ProtocolPool]:
       if self.dry_run_mode or not self._has_real_deployment():
           return self._get_mock_pools()  # Fallback to mock

       web3 = get_web3_provider(self.network)
       factory = web3.eth.contract(address=self.factory_address, abi=FACTORY_ABI)

       # Query real pools from factory
       pool_count = factory.functions.allPoolsLength().call()
       pools = []

       for i in range(min(pool_count, 10)):  # Limit to first 10 pools
           pool_address = factory.functions.allPools(i).call()
           pool_data = await self._query_pool_data(web3, pool_address)
           pools.append(pool_data)

       return pools
   ```

**Add Transaction Simulation**:
- Use `eth_call` to simulate transactions (no execution)
- Test swap building without sending transactions
- Validate gas estimation

### Phase 3: Testing (3-4 hours)

**Create Integration Tests**:
1. Create `tests/integration/test_arbitrum_sepolia.py`:
   ```python
   @pytest.mark.integration
   @pytest.mark.skipif(not os.getenv("RUN_INTEGRATION_TESTS"), reason="Integration tests disabled")
   class TestArbitrumSepoliaIntegration:
       async def test_query_real_pools(self):
           """Test querying actual pools from Arbitrum Sepolia"""

       async def test_pool_data_accuracy(self):
           """Verify pool data matches blockchain state"""

       async def test_transaction_simulation(self):
           """Test transaction building with eth_call"""
   ```

2. Add marker to `pytest.ini`:
   ```ini
   markers =
       integration: integration tests (run with RUN_INTEGRATION_TESTS=1)
       arbitrum: Arbitrum network tests
       sepolia: Sepolia testnet tests
   ```

**Manual Testing Checklist**:
- [ ] Can query pools from Arbitrum Sepolia RPC
- [ ] Pool TVL matches block explorer
- [ ] APY calculations are reasonable
- [ ] Transaction simulation works (eth_call)
- [ ] Gas estimates are realistic
- [ ] Error handling works (bad RPC, timeout, etc.)

### Phase 4: Documentation (1-2 hours)

**Update Documentation**:
1. Create `docs/arbitrum_sepolia_setup.md`:
   - How to get Arbitrum Sepolia ETH
   - Contract addresses found
   - How to run integration tests
   - Troubleshooting guide

2. Update `README.md`:
   - Add Arbitrum Sepolia to supported networks
   - Update .env.example with Arbitrum settings
   - Add testing section

3. Create Sprint 3 report:
   - Implementation summary
   - Test results
   - Known issues
   - Next steps

---

## Technical Context

### Current Architecture

**Network Configuration** (`src/utils/networks.py`):
```python
NETWORKS = {
    "arbitrum-sepolia": NetworkConfig(
        network_id="arbitrum-sepolia",
        chain_id=421614,
        rpc_url="https://sepolia-rollup.arbitrum.io/rpc",
        explorer_url="https://sepolia.arbiscan.io",
        native_token="ETH",
        is_testnet=True,
        description="Arbitrum Sepolia Testnet",
    ),
}
```

**Current Aerodrome Integration** (`src/protocols/aerodrome.py`):
```python
AERODROME_CONTRACTS = {
    "arbitrum-sepolia": {
        "router": "0x0000000000000000000000000000000000000000",  # TODO Sprint 3
        "factory": "0x0000000000000000000000000000000000000000",  # TODO Sprint 3
    },
}

async def get_pools(self) -> List[ProtocolPool]:
    # Currently returns MOCK DATA
    # Sprint 3: Replace with real contract queries
    return mock_pools
```

### Dependencies to Add

```toml
[tool.poetry.dependencies]
python = "^3.11"
# ... existing dependencies ...
web3 = "^6.11.0"  # NEW for Sprint 3
eth-abi = "^4.0.0"  # NEW for Sprint 3

[tool.poetry.group.dev.dependencies]
# ... existing dev dependencies ...
```

### Environment Variables Needed

```bash
# .env additions for Sprint 3
ARBITRUM_SEPOLIA_RPC_URL=https://sepolia-rollup.arbitrum.io/rpc  # Optional custom RPC
RUN_INTEGRATION_TESTS=1  # To enable integration tests
```

---

## Known Issues & Constraints

### From Sprint 2

1. **Approval workflow uses polling** (not event-driven)
   - Impact: Test timeouts in integration tests
   - Status: Documented, defer to Phase 2A
   - File: `src/security/approval.py`

2. **MockPriceOracle default** (not Chainlink)
   - Impact: Using $3000/ETH assumption
   - Status: Acceptable for Phase 1C
   - Phase 2A: Implement Chainlink oracle

3. **No database persistence for approvals**
   - Impact: In-memory only
   - Status: Fine for testing
   - Phase 2A: Add database storage

### Potential Sprint 3 Issues

1. **Aerodrome may not have Arbitrum Sepolia deployment**
   - Mitigation: Fall back to mock data if no deployment
   - Alternative: Use Arbitrum Sepolia Uniswap V3 for testing

2. **RPC rate limits**
   - Public RPCs may have rate limits
   - Consider adding retry logic with exponential backoff

3. **Testnet instability**
   - Testnets can be unreliable
   - Implement fallback to mock data

---

## Success Criteria

Sprint 3 is complete when:

- [ ] **Real contract addresses found** for Aerodrome on Arbitrum Sepolia (or documented why not available)
- [ ] **Can query actual pool data** from blockchain
- [ ] **Pool TVL/APY match reality** (verified against block explorer)
- [ ] **Transaction simulation works** (eth_call for swaps)
- [ ] **Integration tests pass** with real testnet
- [ ] **Documentation complete** (setup guide, troubleshooting)
- [ ] **All existing tests still pass** (193/193 maintained)
- [ ] **No regressions** in existing functionality

**Stretch Goals**:
- [ ] Add automatic RPC endpoint health checking
- [ ] Implement RPC retry logic with backoff
- [ ] Add caching for pool queries (reduce RPC calls)
- [ ] Create helper script for testnet setup

---

## File Checklist

### Files to Create
- [ ] `src/utils/web3_provider.py` - Web3 provider factory
- [ ] `tests/integration/test_arbitrum_sepolia.py` - Integration tests
- [ ] `docs/arbitrum_sepolia_setup.md` - Setup guide
- [ ] `docs/phase1c_sprint3_report.md` - Sprint report

### Files to Modify
- [ ] `pyproject.toml` - Add web3, eth-abi dependencies
- [ ] `src/protocols/aerodrome.py` - Replace mock with real queries
- [ ] `pytest.ini` - Add arbitrum/sepolia markers
- [ ] `README.md` - Update with Arbitrum Sepolia info
- [ ] `.env.example` - Add Arbitrum settings
- [ ] `todo.md` - Update Sprint 3 status

### Files to Review (No Changes Expected)
- `src/utils/networks.py` - Already has Arbitrum Sepolia config
- `src/utils/config.py` - Network validation already works
- `src/blockchain/wallet.py` - Network-agnostic, should work as-is
- `src/data/oracles.py` - Price oracle ready for use

---

## Testing Strategy

### Unit Tests (Maintain 193 passing)
- All existing tests should continue to pass
- Mock protocol behavior for unit tests
- No actual RPC calls in unit tests

### Integration Tests (New)
- **Gated behind environment variable**: `RUN_INTEGRATION_TESTS=1`
- **Marked with pytest markers**: `@pytest.mark.integration @pytest.mark.arbitrum`
- **Skipped by default** in CI/CD
- **Run manually** for verification

### Manual Testing
1. Get Arbitrum Sepolia ETH from faucet
2. Run integration tests with real RPC
3. Verify pool data in block explorer
4. Test transaction simulation
5. Check gas estimates

---

## Risk Assessment

### Low Risk
✅ Network configuration already complete
✅ Existing tests provide safety net
✅ Backward compatible (mock fallback)
✅ Well-documented architecture

### Medium Risk
⚠️ Aerodrome testnet deployment may not exist
⚠️ RPC reliability (public endpoint)
⚠️ Testnet ETH availability
⚠️ Contract ABI compatibility

### High Risk (None Identified)
✅ No breaking changes planned
✅ No critical path dependencies
✅ Fallback strategies in place

---

## Resources

### Aerodrome Protocol
- Main site: https://aerodrome.finance/
- Docs: https://docs.aerodrome.finance/ (check for testnet info)
- GitHub: https://github.com/aerodrome-finance (search for testnet contracts)
- Discord: Check for testnet support

### Arbitrum Sepolia
- RPC: https://sepolia-rollup.arbitrum.io/rpc
- Explorer: https://sepolia.arbiscan.io
- Faucet: https://faucet.quicknode.com/arbitrum/sepolia (and others)
- Docs: https://docs.arbitrum.io/

### Web3.py Documentation
- Main docs: https://web3py.readthedocs.io/
- Contract interaction: https://web3py.readthedocs.io/en/stable/web3.contract.html
- Async patterns: https://web3py.readthedocs.io/en/stable/providers.html#async-providers

---

## Questions for Research Phase

1. **Does Aerodrome have an Arbitrum Sepolia deployment?**
   - If yes: What are the contract addresses?
   - If no: Should we use a different DEX (Uniswap V3) or different testnet?

2. **What is the Aerodrome contract ABI structure?**
   - Router functions needed: `getPool()`, `swapExactTokensForTokens()`, etc.
   - Factory functions needed: `allPools()`, `allPoolsLength()`, etc.
   - Pool functions needed: `getReserves()`, `token0()`, `token1()`, etc.

3. **How to get test tokens on Arbitrum Sepolia?**
   - Are there faucets for USDC, WETH, etc?
   - Or should we use native ETH only for testing?

4. **What is the expected pool data structure?**
   - How are TVL and APY calculated on-chain?
   - Do we need to query multiple contracts?
   - Is there a subgraph for easier querying?

---

## Context for New Claude Session

### Project State
- **Current Phase**: 1C Sprint 3 (Arbitrum Sepolia Integration)
- **Previous Sprint**: Sprint 2 complete (193/193 tests, 48% coverage, 90%+ on new code)
- **Working Directory**: `/Users/kpj/Agents/Mammon`
- **Git Repo**: https://github.com/kpjmd/Mammon.git

### Key Files Location
- Protocol implementation: `src/protocols/aerodrome.py`
- Network config: `src/utils/networks.py`
- Tests: `tests/unit/protocols/test_aerodrome.py`
- Documentation: `docs/`

### Commands to Run
```bash
# Install dependencies (after adding web3)
poetry install

# Run tests
poetry run pytest

# Run integration tests (when ready)
RUN_INTEGRATION_TESTS=1 poetry run pytest -m integration

# Check coverage
poetry run pytest --cov=src --cov-report=html
```

### Architecture Decisions
1. **Multi-network support**: Use `src/utils/networks.py` registry
2. **Price oracle**: Use `src/data/oracles.py` interface (MockPriceOracle for now)
3. **Approval workflow**: Optional via `src/security/approval.py` (has polling issue, defer to Phase 2A)
4. **Testing**: 90%+ coverage on new code, maintain 193/193 passing tests

---

## Ready for Sprint 3

✅ Sprint 2 foundations complete
✅ Architecture documented
✅ Test infrastructure in place
✅ Multi-network support ready
✅ Clear objectives and success criteria

**Next Steps**:
1. Start new Claude chat session
2. Share this handoff document
3. Begin research phase (Aerodrome on Arbitrum Sepolia)
4. Document findings
5. Implement real protocol integration
6. Test thoroughly
7. Document results

**Good luck with Sprint 3!** 🚀
