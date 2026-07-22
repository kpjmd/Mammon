# MAMMON Security Documentation

## Security Principles

MAMMON is built with security as the top priority. This document outlines our security architecture and practices.

## Critical Security Rules

### NEVER
1. ❌ Store private keys in code or version control
2. ❌ Commit .env files or secrets
3. ❌ Skip input validation on external data
4. ❌ Allow transactions without limits
5. ❌ Ignore error conditions
6. ❌ Run on mainnet without extensive testing
7. ❌ Send transactions to unknown contracts
8. ❌ Approve unlimited token allowances

### ALWAYS
1. ✅ Validate all inputs
2. ✅ Enforce spending limits
3. ✅ Require approval for large transactions
4. ✅ Log all critical operations
5. ✅ Use type hints and validation
6. ✅ Test on testnet first
7. ✅ Use contract whitelist for all transactions
8. ✅ Detect and block malicious transaction patterns

---

## Three-Tier Wallet Architecture

MAMMON uses a three-tier wallet system to balance autonomy with security:

### Tier 1: HOT Wallet (Autonomous)
**Purpose**: Day-to-day autonomous operations
**File**: `src/wallet/hot_wallet_provider.py`

| Setting | Value |
|---------|-------|
| Max Transaction | $500 USD |
| Daily Limit | $1,000 USD |
| Max Balance | $2,000 USD |
| Approval | None (autonomous) |
| Risk Levels | LOW only |
| Auto-Pause | Yes (on limit breach) |

**Features**:
- Fully autonomous operation
- Automatic pause on spending limit breach
- Only interacts with LOW-risk whitelisted contracts
- Seed phrase injected at runtime (never stored on disk)

### Tier 2: WARM Wallet (Manual Approval)
**Purpose**: Larger transactions requiring human oversight
**File**: `src/wallet/warm_wallet_provider.py`

| Setting | Value |
|---------|-------|
| Max Transaction | $5,000 USD |
| Daily Limit | $10,000 USD |
| Max Balance | $50,000 USD |
| Approval | 24-hour timeout |
| Risk Levels | LOW, MEDIUM |
| Auto-Pause | No |

**Features**:
- All transactions require manual approval via web dashboard
- Event-driven approval (no polling)
- 24-hour approval timeout
- Interacts with LOW and MEDIUM risk contracts

### Tier 3: COLD Wallet (Hardware)
**Purpose**: Large holdings and high-value operations
**File**: `src/wallet/cold_wallet_stub.py`

| Setting | Value |
|---------|-------|
| Max Transaction | Unlimited |
| Daily Limit | Unlimited |
| Max Balance | Unlimited |
| Approval | 168-hour (7 days) |
| Risk Levels | LOW, MEDIUM, HIGH |
| Hardware | Ledger required |

**Features**:
- Hardware wallet signature required
- Extended approval period for review
- Can interact with higher-risk contracts
- Used for treasury operations

---

## Transaction Security Validator

**File**: `src/security/transaction_validator.py`

### Threat Detection

The validator scans all transactions for:

1. **EIP-7702 Delegation Attacks**
   - Detects `0xef0100` authorization prefix
   - Blocks delegation to unknown contracts
   - Severity: CRITICAL (blocks transaction)

2. **Permit2 Hidden Approvals**
   - Warns on direct Permit2 interactions
   - Detects hidden Permit2 address in calldata
   - Monitors function selectors (permit, permitTransferFrom)
   - Severity: WARNING to CRITICAL

3. **Dangerous Function Calls**
   - selfdestruct
   - delegatecall
   - setCode (EIP-7702)
   - upgradeTo / upgradeToAndCall
   - Severity: CRITICAL

4. **Excessive Token Approvals**
   - Detects `type(uint256).max` approvals
   - Flags approvals > 10^30 tokens
   - Severity: WARNING

5. **Unknown Contracts**
   - Strict mode blocks transactions to non-whitelisted addresses
   - Logs unknown contract interactions
   - Severity: CRITICAL in strict mode

### Validation Flow

```
Transaction Request
       ↓
┌──────────────────────┐
│  Whitelist Check     │ → BLOCKED if unknown
└──────────────────────┘
       ↓
┌──────────────────────┐
│  Tier Risk Check     │ → BLOCKED if risk too high
└──────────────────────┘
       ↓
┌──────────────────────┐
│  EIP-7702 Detection  │ → BLOCKED if delegation attack
└──────────────────────┘
       ↓
┌──────────────────────┐
│  Permit2 Analysis    │ → WARNING or BLOCKED
└──────────────────────┘
       ↓
┌──────────────────────┐
│  Dangerous Functions │ → BLOCKED if dangerous
└──────────────────────┘
       ↓
┌──────────────────────┐
│  Approval Limits     │ → WARNING if excessive
└──────────────────────┘
       ↓
    APPROVED
```

---

## Contract Whitelist

**File**: `src/security/contract_whitelist.py`

### Whitelisted Protocols (Base Network)

| Protocol | Contract Type | Risk Level |
|----------|---------------|------------|
| USDC | Token | LOW |
| WETH | Wrapper | LOW |
| DAI | Token | LOW |
| USDbC | Token | LOW |
| Aave V3 Pool | Lending Pool | LOW |
| Aave Data Provider | Oracle | LOW |
| Moonwell Comptroller | Lending Pool | LOW |
| Moonwell mUSDC/mWETH | Lending Pool | LOW |
| Morpho Blue | Lending Pool | MEDIUM |
| Aerodrome Router | DEX Router | LOW |
| Uniswap V3 Router | DEX Router | LOW |
| Permit2 | Approval | MEDIUM |

### Risk Levels

- **LOW**: Well-audited, high TVL, long track record
- **MEDIUM**: Audited but newer or more complex
- **HIGH**: New or experimental protocols
- **CRITICAL**: Requires extra scrutiny

### Adding New Contracts

```python
from src.security.contract_whitelist import get_contract_whitelist

whitelist = get_contract_whitelist("base-mainnet")

# Check if contract is allowed
allowed, reason, info = whitelist.validate_transaction_target(
    address="0x...",
    strict_mode=True
)

if not allowed:
    raise SecurityError(reason)
```

---

## Key Custody

MAMMON supports two custody modes, selected by `USE_LOCAL_WALLET`.

### CDP MPC Server Wallet (recommended, `USE_LOCAL_WALLET=false`)

Private keys are generated and held inside Coinbase's Trusted Execution
Environment and **never exist on this machine** — not in a file, not in the
process environment, not in memory. Signing happens inside the TEE; MAMMON
sends a transaction request and receives a hash.

Because there is no seed to leak, this eliminates an entire class of
compromise — including the one MAMMON actually suffered (see below).

Persistence works by **stable account name**, not by a stored address:

```
CDP_ACCOUNT_NAME=mammon-hot        # same name -> same address, every run
CDP_EXPECTED_ADDRESS=0x...         # optional, strongly recommended once funded
```

`CDP_EXPECTED_ADDRESS` is a safety interlock: if the resolved address does not
match it, startup **fails** rather than proceeding. Without it, a typo in the
account name silently resolves to a different, empty account.

Implementation: `src/wallet/cdp_mpc_provider.py`. It talks to `cdp-sdk`
directly and deliberately does **not** use `coinbase-agentkit`'s
`CdpEvmWalletProvider`, which drops EIP-1559 fee fields on send and would
silently void the gas-price cap (see Layer 4).

Key export is intentionally unimplemented. Extracting a key from TEE custody
would reintroduce exactly the exposure this mode exists to prevent.

### Local seed phrase (`USE_LOCAL_WALLET=true`, current default)

Derives a key from `WALLET_SEED` (BIP-39, path `m/44'/60'/0'/0/0`) on this
machine. Required when local custody is selected; MAMMON refuses to start in
this mode without a valid seed.

**This mode carries a realized, not theoretical, risk.** On 2025-12-02 a MAMMON
wallet was drained because its seed phrase was stored in plaintext, world-
readable files. Prefer CDP MPC custody.

If you must use it:
- Inject `WALLET_SEED` at runtime only (see `scripts/vps_start.sh`); never write
  it to disk, never commit it.
- Note that the current VPS flow passes the seed on an `ssh` command line,
  exposing it to the remote process table and local shell history. Treat any
  seed handled that way as compromised if the host is.

### Switching to MPC custody

```
poetry run python scripts/cdp_show_account.py   # prints the persistent address
poetry run python scripts/cdp_show_account.py   # run twice - MUST match
```

Fund that address, set `CDP_EXPECTED_ADDRESS` to it, then set
`USE_LOCAL_WALLET=false` and remove `WALLET_SEED` from the environment.

## Multi-Layered Security

### Layer 1: Configuration Security
- Pydantic validation of all environment variables
- Rejection of placeholder values
- Type checking on all settings
- No hardcoded secrets

### Layer 2: Input Validation
- All addresses validated (checksummed Ethereum format)
- All amounts validated (positive, reasonable decimals)
- All protocol names sanitized
- All URLs validated (HTTPS required)

### Layer 3: Spending Limits
- Per-transaction maximum (tier-specific)
- Daily spending limit (tier-specific)
- Weekly spending limit
- Monthly spending limit
- Auto-pause on breach (HOT wallet)

### Layer 4: Transaction Validation
- Contract whitelist enforcement
- EIP-7702 delegation detection
- Permit2 hidden approval detection
- Dangerous function blocking
- Excessive approval warnings

### Layer 5: Approval Workflows
- Tier-based approval requirements
- Event-driven approval (no polling)
- Configurable timeout per tier
- Web dashboard for manual review

### Layer 6: Audit Logging
- Immutable audit log
- All transactions logged
- All security events logged
- Threat detection logged
- Approval decisions logged

## Threat Model

### Threats We Protect Against
1. **Accidental Loss**: Spending limits prevent mistakes
2. **Configuration Errors**: Validation catches bad config
3. **Malicious Input**: Input validation prevents injection
4. **Unauthorized Transactions**: Approval workflows add oversight
5. **Protocol Risks**: Risk assessment evaluates safety

### Threats Outside Scope (Phase 1)
1. **Smart Contract Exploits**: Rely on protocol security audits
2. **Market Manipulation**: Not attempting MEV protection yet
3. **Network Attacks**: Rely on RPC provider security
4. **Compromised Dependencies**: Trust Poetry lock file

## Security Checklist

### Before Testnet
- [ ] All secrets in .env, not code
- [ ] Spending limits configured
- [ ] Approval threshold set
- [ ] Input validation complete
- [ ] Audit logging working
- [ ] Tests passing

### Before Mainnet
- [ ] Extensive testnet testing
- [ ] Security review completed
- [ ] All limits verified
- [ ] Approval workflow tested
- [ ] Database backups configured
- [ ] Monitoring alerts set up

## Incident Response

### If Private Key Compromised
1. Immediately transfer all funds to new wallet
2. Revoke all API keys
3. Review audit logs
4. Generate new wallet
5. Update configuration

### If Unauthorized Transaction Detected
1. Check audit logs for source
2. Review approval history
3. Verify spending limits enforced
4. If loss occurred, document and analyze
5. Implement additional safeguards

## Best Practices

### For Developers
- Review security docs before changes
- Never skip validation
- Test security features
- Log security-relevant events
- Ask when unsure

### For Operators
- Use strong API keys
- Rotate keys regularly
- Monitor audit logs
- Review approvals carefully
- Keep secrets secure

### For Testing
- Use testnet first
- Test with small amounts
- Verify all limits work
- Test approval workflows
- Simulate error conditions

## Security Roadmap

### Phase 1 (Current)
- Basic security controls
- Spending limits
- Approval workflows
- Audit logging

### Phase 2
- Enhanced monitoring
- Automated alerts
- Advanced risk models
- Multi-sig support (maybe)

### Phase 3
- Formal security audit
- Bug bounty program
- Security certifications
- Insurance integration (if available)

## Responsible Disclosure

If you discover a security vulnerability:
1. Do NOT open a public issue
2. Email: [your-email]
3. Allow 90 days for fix
4. Disclosure after fix deployed

## Resources

- [Coinbase CDP Security](https://docs.cdp.coinbase.com/agentkit/docs/security)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Smart Contract Security](https://consensys.github.io/smart-contract-best-practices/)
