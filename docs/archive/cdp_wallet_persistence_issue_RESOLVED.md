# CDP Wallet Persistence Issue & Solutions

**Date**: 2025-01-09
**Status**: ✅ **RESOLVED (WS7)** — see correction below

---

> ## ⚠️ CORRECTION (WS7, CDP MPC custody migration)
>
> **The "Root Cause" section below is wrong.** It is preserved for history, but
> do not act on it.
>
> **What it claimed:** the CDP API cannot load a wallet by address, only by
> wallet ID.
>
> **What is actually true**, verified against the installed
> `coinbase-agentkit` 0.7.4 and `cdp-sdk` 1.33.2:
>
> 1. `cdp.evm.get_account(address=...)` **does** exist, and AgentKit already
>    calls it (`cdp_evm_wallet_provider.py:67-73`).
> 2. AgentKit branches on its optional `CdpEvmWalletProviderConfig.address`
>    field. When that field is **unset**, it calls `create_account()` — minting
>    a brand-new EOA on every run.
> 3. MAMMON never populated that field. **That** is the real cause of the 16+
>    wallets and the stranded funds — a missing config value, not an API
>    limitation.
> 4. Better still, `cdp.evm.get_or_create_account(name=...)`
>    (`evm_client.py:420`) resolves a stable account by **name**, so nothing
>    has to be persisted locally at all. AgentKit never calls it.
>
> **Resolution:** WS7 added `src/wallet/cdp_mpc_provider.py`, a first-party
> provider built directly on `cdp-sdk` that resolves the account by name via
> `get_or_create_account`. Same name → same address, every run. It bypasses
> AgentKit entirely, because AgentKit's `send_transaction` drops the EIP-1559
> fee fields and would silently void MAMMON's gas-price cap.
>
> **The interim fix recorded in `RESOLUTION_NOTE.md` ("Solution A: local wallet
> with seed phrase") was a workaround, not a fix.** It put a plaintext seed on
> the machine, which led to the 2025-12-02 wallet drain. Persistent MPC custody
> supersedes it.
>
> To verify persistence yourself: `poetry run python scripts/cdp_show_account.py`
> twice — the address must be identical.

---

## Problem Summary

CDP AgentKit with `CdpEvmWalletProvider` creates **ephemeral Externally Owned Accounts (EOAs)** that are different on each script run, even with the same `CDP_WALLET_SECRET`. This prevents using a persistent, funded wallet.

### Evidence
- Multiple wallet addresses created: 16+ wallets in CDP dashboard
- Persistence test FAILED: Different addresses on sequential runs
  - Run 1: `0xd803Ee866bA6Af7536bACdA1b404fe4B08cDB96F`
  - Run 2: `0xEc282069814Ed78c48FcBeFcFf6020D2871A7c03`
- Funded wallets cannot be reliably loaded

### Funded Wallets (Currently Unusable)
- `0x448a8502Cc51204662AafD9ac22ECaB794C2eB28` - 0.05 ETH
- `0xf05DE660025dE90eFD1E394868a1f541825Ae56D` - 0.05 ETH

---

## Root Cause

According to [CDP Server Wallets documentation](https://docs.cdp.coinbase.com/server-wallets/v2/introduction/accounts):

**EOAs (Externally Owned Accounts)**:
- Created by CDP API
- Ephemeral by default
- Not persistent across API calls unless explicitly imported

**Smart Accounts**:
- CDP's recommended approach for persistent wallets
- Managed by CDP infrastructure
- Referenced by wallet ID, not private key

**Our current implementation uses EOAs without proper import/export**, causing the persistence issue.

---

## Attempted Solutions

### ❌ Solution 1: Use `CDP_WALLET_SECRET`
- **Status**: Failed
- **Issue**: CDP doesn't use this for persistence, creates new wallets each time

### ❌ Solution 2: Export/Import Wallet
- **Status**: Failed
- **Issue**: CDP AgentKit doesn't expose wallet listing/export APIs needed
- **Requirement**: Would need Export scope on API key + direct CDP REST API calls

### ❌ Solution 3: Load Wallet by Address
- **Status**: Not Possible
- **Issue**: CDP API doesn't support "load wallet by address" - only by wallet ID

---

## Viable Solutions

### ✅ Solution A: Use Local Wallet with Seed Phrase (RECOMMENDED)

**Approach**: Switch from CDP-managed wallets to local wallet derived from `WALLET_SEED`

**Pros**:
- Full control over wallet
- Guaranteed persistence
- Simpler implementation
- No CDP wallet management issues

**Cons**:
- Need to manage private keys locally
- Must implement signing logic
- Loses CDP's wallet management features

**Implementation**:
1. Generate or import BIP39 mnemonic
2. Derive wallet from seed phrase
3. Use Web3.py Account for signing
4. Update `WalletManager` to support local wallet mode

**Status**: Not yet implemented

---

### ✅ Solution B: Create CDP Smart Account

**Approach**: Use CDP Smart Accounts instead of EOAs

**Pros**:
- Persistent by design
- CDP-managed infrastructure
- Proper wallet ID for reference

**Cons**:
- Requires different CDP setup
- May have different gas costs
- Need to transfer funds to new Smart Account

**Implementation**:
1. Create Smart Account via CDP API
2. Get wallet ID from response
3. Store wallet ID in `.env` as `CDP_WALLET_ID`
4. Update `WalletManager` to load by wallet ID

**Status**: Requires CDP API integration work

---

### ✅ Solution C: Manual Wallet Funding Workflow

**Approach**: Accept ephemeral wallets, fund before each transaction

**Pros**:
- Works with current implementation
- No code changes needed
- Simple to understand

**Cons**:
- Manual process each time
- Wastes gas on transfers
- Poor user experience

**Implementation**:
1. Run `scripts/show_wallet_address.py`
2. See which wallet CDP created
3. Transfer 0.05 ETH to that wallet
4. Run transaction script immediately
5. Repeat for next transaction

**Status**: Available now (workaround)

---

## Recommended Path Forward

**Short-term (Sprint 3)**:
Use **Solution C** to complete first transaction:
```bash
poetry run python scripts/show_wallet_address.py  # Get wallet address
# Transfer ETH to displayed address
poetry run python scripts/execute_first_wrap.py   # Execute immediately
```

**Long-term (Sprint 4+)**:
Implement **Solution A** (local wallet with seed phrase):
- Modify `WalletManager` to support local wallet mode
- Add `USE_LOCAL_WALLET=true` config option
- Generate/import seed phrase
- Use Web3.py Account for signing

This provides full control and guaranteed persistence.

---

## Implementation Status

### Completed
- ✅ Diagnostic scripts created
- ✅ Wallet persistence testing
- ✅ CDP documentation research
- ✅ `CDP_WALLET_ID` added to config

### Pending
- ⏳ Local wallet implementation (Solution A)
- ⏳ CDP Smart Account integration (Solution B)
- ⏳ Update WalletManager for wallet ID loading

---

## Lessons Learned

1. **CDP AgentKit != CDP Server Wallets API**: AgentKit is simplified wrapper, doesn't expose full wallet management
2. **Wallet Secret ≠ Persistence**: The secret doesn't guarantee same wallet on reload
3. **EOAs are ephemeral by default**: Need explicit import/export or Smart Account approach
4. **Documentation matters**: CDP docs clearly explain EOA vs Smart Account distinction

---

## References

- [CDP Server Wallets - Account Types](https://docs.cdp.coinbase.com/server-wallets/v2/introduction/accounts)
- [CDP Server Wallets - Export Accounts](https://docs.cdp.coinbase.com/server-wallets/v2/using-the-wallet-api/export-accounts)
- [CDP Server Wallets - Import Accounts](https://docs.cdp.coinbase.com/server-wallets/v2/using-the-wallet-api/import-accounts)

---

**Next Action**: Choose solution and implement before executing Sprint 3 first transaction.
