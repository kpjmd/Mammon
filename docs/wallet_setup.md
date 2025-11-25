# Wallet Setup Guide

## Overview

MAMMON supports two wallet modes:
1. **Local Wallet (Recommended)**: Uses BIP-39 seed phrase with full control
2. **CDP Wallet**: Uses Coinbase Developer Platform's managed wallet service

## CRITICAL: Always Use WalletManager

**⚠️ SECURITY REQUIREMENT**: Never call `wallet_provider.send_transaction()` directly.

```python
# ❌ WRONG - Bypasses security layers
wallet_provider.send_transaction(tx)  # No spending limits! No approval!

# ✅ CORRECT - Through WalletManager
await wallet_manager.execute_transaction(...)  # Full security stack
```

**Why?** LocalWalletProvider is a low-level component that only handles:
- Account derivation
- Transaction signing
- Basic simulation

WalletManager adds the critical security layers:
- Spending limit enforcement
- Approval workflow (for large transactions)
- Audit logging
- USD conversion via price oracle
- Dry-run mode support

## Local Wallet Setup (Recommended)

### Why Local Wallet?

- ✅ **Persistence**: Same address every time
- ✅ **Control**: You own the private keys
- ✅ **Lower Gas**: Standard EOA vs smart contract
- ✅ **No vendor lock-in**: Works without CDP service
- ✅ **Battle-tested**: Standard BIP-44 derivation path

### Initial Setup

#### Option 1: Generate New Wallet

```bash
# Generate new seed phrase
poetry run python scripts/generate_seed.py

# Save the output securely (write on paper!)
# Add to .env:
WALLET_SEED="your twelve words here"
```

#### Option 2: Import Existing Wallet

If you have an existing MetaMask or hardware wallet seed phrase:

```bash
# Add to .env:
WALLET_SEED="your existing twelve or twenty-four words"
```

**Important**: The derivation path is `m/44'/60'/0'/0/0` (Ethereum account 1).
This will derive the same address as MetaMask account 1.

### Configuration

Add to `.env`:

```bash
# Wallet Mode
USE_LOCAL_WALLET=true

# Seed Phrase (NEVER commit to git!)
WALLET_SEED="your twelve words here"

# Gas Configuration (optional, has defaults)
MAX_PRIORITY_FEE_GWEI=2
GAS_BUFFER_SIMPLE=1.5
GAS_BUFFER_MODERATE=1.3
GAS_BUFFER_COMPLEX=1.2
```

### Funding Your Wallet

```bash
# 1. Display your wallet address
poetry run python scripts/show_wallet_address.py

# 2. Send ETH to the displayed address
#    Network: arbitrum-sepolia (transaction execution network)
#    Minimum: 0.002 ETH
#    Recommended: 0.05 ETH

# 3. Verify balance
poetry run python scripts/check_wallet_balance.py
```

**Network Architecture**:
- **Arbitrum Sepolia**: Transaction execution (use local wallet here)
- **Base Mainnet**: Read-only for Chainlink price feeds

### Wallet Address Derivation

**Derivation Path**: `m/44'/60'/0'/0/0`

- `44'` = BIP-44 (multi-coin hierarchy)
- `60'` = Ethereum coin type
- `0'`  = Account 0 (hardened)
- `0`   = External chain (receiving addresses)
- `0`   = Address index 0

This is the **same path used by MetaMask** for account 1.

Your wallet address: `0x81A2933C185e45f72755B35110174D57b5E1FC88`

## CDP Wallet Setup (Alternative)

### Configuration

Add to `.env`:

```bash
# Wallet Mode
USE_LOCAL_WALLET=false

# CDP Credentials
CDP_API_KEY=your_api_key
CDP_API_SECRET=your_api_secret
CDP_WALLET_SECRET=your_wallet_secret
```

**Note**: CDP wallets may create ephemeral addresses. See `docs/cdp_wallet_persistence_issue.md`.

## Security Best Practices

### Seed Phrase Security

1. **Never commit to version control**
   - `.env` is gitignored
   - Double-check before committing

2. **Secure offline backup**
   - Write on paper and store securely
   - Consider metal backup for long-term

3. **Test with small amounts first**
   - Use testnet initially
   - Send small amount first on mainnet

4. **Anyone with seed = full access**
   - Treat like bank password
   - Never share, never screenshot

### Transaction Security

MAMMON includes 6 security layers:

1. **Spending Limits**: Daily and per-transaction caps
2. **Gas Price Caps**: Maximum gas price protection
3. **Transaction Simulation**: Test before execution
4. **Approval Requirements**: Manual approval above threshold
5. **Audit Logging**: Complete transaction history
6. **Network Validation**: Prevent wrong-network transactions

## Troubleshooting

### Issue: "WALLET_SEED not found"

```bash
# Check .env file exists and contains WALLET_SEED
cat .env | grep WALLET_SEED

# If missing, generate new or add existing:
poetry run python scripts/generate_seed.py
```

### Issue: "Invalid seed phrase"

- Must be 12 or 24 words
- Must be space-separated
- Must be valid BIP-39 words
- Check for typos

### Issue: "Insufficient balance"

```bash
# Check current balance
poetry run python scripts/check_wallet_balance.py

# Fund wallet if needed
# Send to address shown in output
```

### Issue: Different address than expected

The derivation path `m/44'/60'/0'/0/0` should match:
- MetaMask account 1
- Ledger/Trezor account 1, address 1

If using different path, wallet will have different address.

## Recovery Procedures

### If You Lose .env File

If you have seed phrase backup:

1. Create new `.env` from `.env.example`
2. Add your seed phrase back
3. Verify address matches: `poetry run python scripts/show_wallet_address.py`
4. Should see: `0x81A2933C185e45f72755B35110174D57b5E1FC88`

### If You Lose Seed Phrase

**You cannot recover the wallet**. This is why offline backup is critical.

Options:
1. Generate new wallet (new address, lose old funds)
2. If funds are still in old wallet, they're lost

### If Wallet is Compromised

1. **Immediately** transfer all funds to new wallet
2. Generate new seed phrase
3. Update `.env` with new seed
4. Never use old seed again

## Testing

### Verify Wallet Setup

```bash
# 1. Show address (should be consistent)
poetry run python scripts/show_wallet_address.py

# 2. Check balance
poetry run python scripts/check_wallet_balance.py

# 3. Run test transaction (dry-run mode)
DRY_RUN_MODE=true poetry run python scripts/execute_first_wrap_simple.py

# 4. Execute real transaction
DRY_RUN_MODE=false poetry run python scripts/execute_first_wrap_simple.py
```

### Verify Persistence

The wallet address should be the same every time:

```bash
# Run multiple times - should show same address
poetry run python scripts/show_wallet_address.py
poetry run python scripts/show_wallet_address.py
poetry run python scripts/show_wallet_address.py
```

All three should output: `0x81A2933C185e45f72755B35110174D57b5E1FC88`

## Migration

### From CDP Wallet to Local Wallet

1. Transfer funds from CDP wallet to local wallet address
2. Update `.env`: `USE_LOCAL_WALLET=true`
3. Verify: `poetry run python scripts/show_wallet_address.py`
4. Test with small transaction

### From Local Wallet to CDP Wallet

1. Update `.env`: `USE_LOCAL_WALLET=false`
2. Add CDP credentials
3. Get new CDP wallet address
4. Transfer funds to new address

## Support

For issues:
- See `docs/cdp_wallet_persistence_issue.md` for CDP issues
- Check `docs/local_wallet_security.md` for security details
- Review `CLAUDE.md` for architecture
