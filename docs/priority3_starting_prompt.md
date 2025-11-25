# Sprint 4 Priority 3: Starting Prompt

Use this prompt to begin Priority 3 in a fresh chat session.

---

## 🚀 Starting Prompt

```
I'm ready to begin Sprint 4 Priority 3: Real DEX Swap with Price Oracle Integration.

**Current Status:**
- ✅ Priority 1 Complete: Local wallet working, first TX successful
- ✅ Priority 2 Complete: Premium RPC at 50%, 25-70ms latency, 100% reliability
- 🎯 Priority 3: Ready to begin - PIVOTED TO BASE SEPOLIA

**Network Change:**
Changed from Arbitrum Sepolia to Base Sepolia because:
- ✅ All Uniswap V3 contracts officially verified on Basescan
- ✅ Circle official USDC testnet deployment
- ✅ L2 native ETH is ERC-20 compliant (no WETH wrapping needed!)
- ✅ Universal Router handles native ETH directly
- ✅ Better testnet ecosystem and liquidity

**Priority 3 Target:**
Direct ETH → USDC swap on Base Sepolia using Uniswap V3 Universal Router
(Much simpler than WETH wrap/unwrap approach!)

**Priority 3 Scope (4 Phases):**

**Phase 1: Chainlink Price Oracle Integration** (resolves Sprint 3 Issue #2)
- Complete ChainlinkPriceOracle implementation
- Configure price feeds for Base Sepolia & Base Mainnet
- Update TVL calculations to use real prices
- Integration tests

**Phase 2: Gas Estimation** (resolves Sprint 3 Issue #3)
- Implement gas estimation utilities (eth_estimateGas)
- Validate estimates within 10% of actual gas
- Add gas cost to approval requests

**Phase 3: Uniswap V3 Integration**
- Verify Uniswap V3 contracts on Base Sepolia Basescan
- Query ETH/USDC pool liquidity
- Build swap parameter calculator
- Test read-only contract interactions

**Phase 4: First ETH→USDC Swap**
- Pre-swap validation (balances, prices, liquidity)
- Build swap transaction (Universal Router execute())
- Execute with approval workflow
- Post-swap validation and monitoring

**Verified Contract Addresses (Base Sepolia):**
Already added to src/utils/contracts.py:
- Universal Router: 0x5d08bB547e5A1B8C110d7967963A0e7914713E8D ✅
- USDC (Circle): 0x036CbD53842c5426634e7929541eC2318f3dCF7e ✅
- V3 Factory: 0x33128a8fC17869897dcE68Ed026d694621f6FDfD ✅
- SwapRouter02: 0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4 ✅
- WETH: 0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14 (reference only)

**Simplified Swap Flow (No WETH wrapping!):**
Old plan: ETH → WETH (wrap) → Token (swap) → WETH → ETH (unwrap)
New plan: ETH → USDC (one swap via Universal Router) ✅ MUCH SIMPLER

**Key Files to Review:**
- TODO.md - Priority 3 plan (lines 114-227) - UPDATED with Base Sepolia
- src/data/oracles.py - ChainlinkPriceOracle stub (needs completion)
- src/utils/contracts.py - UPDATED with Base Sepolia addresses & ABIs
- src/utils/networks.py - Base Sepolia already configured
- src/tokens/erc20.py - ERC20Token class (working)

**Current Environment:**
- Wallet: 0x81A2933C185e45f72755B35110174D57b5E1FC88
- Tests: 286 passing
- Chainlink: Enabled in .env (CHAINLINK_ENABLED=true)
- Premium RPC: Alchemy at 50%, working perfectly

**Request:**
Let's start with Phase 1: Chainlink Price Oracle Integration. Please:
1. Review the current ChainlinkPriceOracle stub implementation in src/data/oracles.py
2. Research Chainlink price feed addresses for:
   - Base Sepolia (testnet): ETH/USD, USDC/USD if available
   - Base Mainnet: ETH/USD, USDC/USD, USDT/USD, DAI/USD
3. Implement the complete price oracle with:
   - AggregatorV3Interface ABI (5 functions)
   - Price staleness validation (< 1 hour)
   - Fallback to mock oracle
   - Integration tests on Base Mainnet (read-only)
4. Update Aerodrome TVL calculations to use real prices

After Phase 1 is complete and tested, we'll move to Phase 2 (gas estimation), then Phase 3 (Uniswap V3 liquidity), then Phase 4 (first swap).
```

---

## 📋 Important Context

### Why This Pivot is Better

**Technical Advantages:**
1. **Native ETH on L2** - Base Sepolia native ETH is ERC-20 compliant
2. **No WETH Wrapper Needed** - Universal Router handles ETH directly
3. **Verified Contracts** - All addresses officially verified on Basescan
4. **Gas Efficient** - One swap instead of wrap + swap + unwrap
5. **Future Proof** - Uniswap V3 is the current standard

### Workflow Comparison

**Old WETH Plan (Complex):**
```
1. ETH → WETH (deposit/wrap transaction)
2. WETH → Token (swap transaction)
3. Token → WETH (swap back transaction)
4. WETH → ETH (withdraw/unwrap transaction)
Total: 4 transactions, 2-3 approvals needed
```

**New Direct Plan (Simple):**
```
1. ETH → USDC (Universal Router execute() - handles everything)
Total: 1 transaction, 1 approval
```

### Key Resources

**Chainlink Price Feeds:**
- Base Sepolia: https://docs.chain.link/data-feeds/price-feeds/addresses?network=base&page=1#base-sepolia
- Base Mainnet: https://docs.chain.link/data-feeds/price-feeds/addresses?network=base&page=1

**Uniswap V3 Documentation:**
- Universal Router: https://docs.uniswap.org/contracts/universal-router/overview
- Native ETH Support: https://docs.uniswap.org/contracts/universal-router/technical-reference#command-codes

**Contract Verification:**
- Base Sepolia Explorer: https://sepolia.basescan.org/
- Verify Universal Router: 0x5d08bB547e5A1B8C110d7967963A0e7914713E8D
- Verify USDC: 0x036CbD53842c5426634e7929541eC2318f3dCF7e

---

## ✅ Success Criteria for Priority 3

**Phase 1 Complete:**
- [ ] ChainlinkPriceOracle fully implemented with AggregatorV3Interface
- [ ] Price feeds configured for Base Sepolia & Base Mainnet
- [ ] Integration tests passing on Base Mainnet (read-only)
- [ ] Aerodrome TVL calculations using real Chainlink prices
- [ ] Sprint 3 Issue #2 (Simplified TVL) RESOLVED

**Phase 2 Complete:**
- [ ] Gas estimation utilities implemented using eth_estimateGas
- [ ] Estimates validated within 10% of actual gas used
- [ ] Gas cost displayed in approval requests
- [ ] Sprint 3 Issue #3 (Gas Estimation) RESOLVED

**Phase 3 Complete:**
- [ ] Uniswap V3 contracts verified on Base Sepolia Basescan
- [ ] ETH/USDC pool found with sufficient liquidity
- [ ] Pool price and parameters queryable
- [ ] Swap calculator working (amountOutMinimum, deadline, etc.)

**Phase 4 Complete:**
- [ ] First successful ETH→USDC swap executed on Base Sepolia
- [ ] Pre-swap validation working (balances, prices, liquidity)
- [ ] Transaction simulation working (eth_call)
- [ ] Slippage validation with Chainlink price
- [ ] Post-swap monitoring working (actual vs expected USDC)
- [ ] Full swap details logged to audit trail

---

## 🎯 Next Steps

1. **Copy the starting prompt above** into a fresh Claude Code chat
2. **Begin with Phase 1** (Chainlink integration)
3. **Test thoroughly** after each phase before moving to next
4. **Celebrate** when you execute your first real DEX swap! 🎉

Good luck! You've built an incredible foundation with Priorities 1 & 2. This final priority will tie it all together with real price data and your first DeFi interaction.
