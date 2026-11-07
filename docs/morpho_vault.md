# Morpho vault venue (Gauntlet USDC Prime)

MAMMON can trade a third USDC lending venue: one allowlisted **MetaMorpho
(ERC-4626) vault** on Base, exposed to the optimizer as the protocol `"Morpho"`.
A vault pools deposits and its curator allocates them across isolated Morpho
Blue markets. To MAMMON it behaves like a single lending pool:

| | |
|---|---|
| Yield | allocation-weighted Morpho Blue supply APR over the vault's markets, minus the vault fee (computed on-chain each scan) |
| Balance | `convertToAssets(balanceOf(wallet))` |
| Deposit | exact-amount USDC `approve(vault)` → `deposit(assets, wallet)` |
| Withdraw | `withdraw(assets, wallet, wallet)`; a request covering (nearly) the whole position does `redeem(allShares, wallet, wallet)` |

**It ships disabled.** `SUPPORTED_PROTOCOLS` defaults to `Aave V3,Moonwell`, so
merging and deploying changes nothing about live trading until you opt in (see
[Enable runbook](#enable-runbook)). Scans, reconcile and `verify_positions.py`
read the vault either way.

Raw Morpho Blue markets (`src/protocols/morpho.py`) are no longer scanned. They
needed per-market parameters, were never executable, and their API query
failed every cycle.

## What is pinned, and why

Code: `src/protocols/morpho_vault.py` (`MORPHO_VAULTS`). These are constants,
not `.env` values, so a typo can't redirect funds. Verified on-chain
2026-10-24:

| Field | Value |
|---|---|
| Vault | `0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61` (Gauntlet USDC Prime, gtUSDCp, MetaMorpho v1.0) |
| Asset | USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| Morpho Blue core | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb` |
| Curator | `0x9E33faAE38ff641094fa68c65c2cE600b3410585` (Gauntlet) |
| Owner | `0x5a4E19842e09000a582c20A4f524C26Fb48Dd4D0` |
| At pin time | fee 0%, timelock 7 days, ~$411M TVL, ~91% in cbBTC/USDC 86% LLTV |

Why this vault: every large Base USDC vault lends into the same few blue-chip
markets, so gross APY is about the same everywhere and the vault fee decides
the net. Gauntlet Prime charges 0% (Steakhouse USDC, the vault behind
Coinbase's in-app lending, charges 25%), has a 7-day timelock, and uses the
standard V1 interface, where `maxWithdraw`/`maxDeposit` are meaningful
(Vaults V2 return 0 for both).

The vault is also on the contract whitelist
(`src/security/contract_whitelist.py`), without which `WalletManager` blocks
any transaction to it. Its risk-table score is 85: Morpho Blue core plus a
curator layer, so one notch below the core.

## Guards (fail closed)

Every scan, and again right before every deposit, MAMMON checks:

1. `asset()`, `MORPHO()`, `curator()` and `owner()` equal the pinned values.
2. `timelock() >= MORPHO_VAULT_MIN_TIMELOCK_SECONDS` (default 604800 = 7 days).
3. `fee() <= MORPHO_VAULT_MAX_FEE` (default 0.05).
4. **Share price tripwire.** MetaMorpho v1.0 realizes bad debt by lowering the
   share price. If `convertToAssets(1e24)` drops more than 1bp below the
   highest value ever recorded, the vault is **latched**. The 1bp tolerance
   absorbs a lagging RPC replica, since 2h of interest is about 0.1bp.
   - The latch and the high-water share price are persisted in
     `data/morpho_vault_guard.json` (atomic writes, like the cycle circuit
     breaker), so they survive restarts, the monthly duration rollover and the
     exit procedure below. A post-loss price never becomes the new baseline.
   - An unreadable state file fails **closed**: every vault reads as tripped.
   - Only an operator reset clears a latch (see [Reset](#reset-after-investigating)).

If any check fails:

- The scan raises, so the vault drops out of the cycle and gets no new
  deposits. The executor re-runs checks 1–4 right before any deposit, so a
  latched vault is refused even on a path the scan never vetted.
- A **critical Discord alert** (`Morpho vault guard tripped`) goes out once per
  distinct reason. The dedupe survives restarts and resets when the guard
  passes again. An ERROR log line and a CRITICAL `risk_alert` audit event are
  written as well.
- **The strategy never treats the vault as 0%.** A venue with no yield data
  this cycle (guard trip, RPC error, timeout) is held, not exited, and a
  rejected `rebalance` decision ("no yield data") is recorded. The same applies
  to Aave V3 and Moonwell if their scans fail. Whether the vault is then
  exited depends on the trip kind (next section).
- Any vault position stays tracked; reconcile never closes a row it couldn't
  read.
- **Withdrawals are never gated.** You can always get out.

Deposits also refuse amounts above `maxDeposit` (vault supply caps full).
Withdrawals refuse amounts above `maxWithdraw`, which is the vault's
withdrawable liquidity, before broadcasting anything.

## What happens automatically

| Trip | Latched? | Automatic action |
|---|---|---|
| **Share price drop** (bad debt) | yes (`trip_kind: share_price`) | **Auto-exit** (below) |
| Governance drift (asset/core/curator/owner, timelock, fee) | no, re-checked each scan | Hold + alert; exit manually |
| Operator latch (a manual `morpho_vault_exit.py --live`) | yes (`trip_kind: operator`) | Hold; nothing left to exit |
| Guard state file unreadable | treated as tripped | Deposits blocked; **no** auto-exit (cause unknown); critical alert `Morpho vault auto-exit suppressed`; exit manually |

**Auto-exit on a share-price latch.** Each cycle, right after the scan and
before reconcile and the strategy, the scheduler checks every latched vault.
If the latch is `share_price` and the wallet holds a position on-chain, it
withdraws to the wallet:

- It calls `execute_withdraw(..., emergency=True)` directly. This is a
  withdrawal to our own wallet, not a rebalance, so the per-day rebalance cap
  and the profitability/APY gates don't apply. The wallet's gas-price cap and
  `DRY_RUN_MODE` still do; in dry run it only logs what it would do.
- It withdraws `min(position, maxWithdraw)`:
  - Enough liquidity: every share is redeemed.
  - Partial: whatever cash the vault has comes out, the alert reports the
    amount still stuck, and the remainder is retried every cycle.
  - `maxWithdraw == 0`: nothing is sent; it alerts and retries next cycle.
- Each withdrawal sends a critical `Morpho vault emergency exit` alert with the
  tx hash, the amount out and anything still stuck. It also writes an
  `emergency_exit` decision row, a transaction row and an audit event. Then
  the vault's position row is reconciled against chain (closed or reduced).
- A failed or reverted withdraw alerts and the cycle continues; it's retried
  next cycle. A repeating identical outcome (no liquidity, the same failure, a
  revert) alerts only once.
- Nothing is redeposited in the same cycle. The freed USDC is idle capital,
  and next cycle's idle-deploy picks Aave V3 or Moonwell. The latched vault
  stays excluded (its scan raises, and the executor refuses the deposit).

The latch stays after the exit. **A reset remains the only way to re-enable
deposits** (see [Reset](#reset-after-investigating)).

## Manual exit

For governance drift, an unreadable state file, or whenever you'd rather not
wait for the next cycle, exit manually when the alert arrives:

```bash
sudo systemctl stop mammon.service
cd /root/mammon
/root/.local/bin/poetry run python scripts/morpho_vault_exit.py          # dry run: shows position + simulates
/root/.local/bin/poetry run python scripts/morpho_vault_exit.py --live   # full redeem; asks for a typed confirmation
sudo systemctl start mammon.service
```

- `--live` refuses to broadcast while `mammon.service` is active (the two
  processes would race on the wallet nonce); `--force` overrides.
- A successful live exit **latches** the vault guard, even when the trip was a
  non-latching check such as a curator change. The restarted loop therefore
  won't redeposit into the vault.

The next cycle reconciles the latched vault's row (closing it) and idle-deploy
puts the USDC into Aave V3 or Moonwell.

### Reset after investigating

```bash
/root/.local/bin/poetry run python scripts/reset_morpho_vault_guard.py            # show state
/root/.local/bin/poetry run python scripts/reset_morpho_vault_guard.py --confirm  # clear the latch
```

Resetting also drops the stored high-water share price, so the next scan
adopts the current price as its baseline. Do it only once you've decided the
vault is healthy enough to use again. To keep the vault out permanently,
remove `Morpho` from `SUPPORTED_PROTOCOLS` instead.

## APY convention

Rates are linear APR (rate per second × seconds per year), the same as the
Moonwell integration. This reads about 0.1pt below Morpho's UI, which
compounds; at pin time it was 4.43% on-chain vs 4.53% from the API. That's
conservative for the newcomer.

## Enable runbook

Do this only after the post-2026-10-24 soak ends, and not during it.

1. Merge the PR and `git pull` in `/root/mammon`.
2. Restart `mammon.service`. Check that the first cycle logs
   `✅ [MORPHO] Gauntlet USDC Prime Vault: x.xx% net APY` and no
   `Vault guard tripped`. Morpho now shows up in `available_yields` but is
   still not a trade target.
3. Optional dry check: `scripts/morpho_vault_exit.py` (no `--live`) reads the
   vault through the real wallet config without sending anything.
4. Opt in by adding `Morpho` to the droplet `.env`:
   ```
   SUPPORTED_PROTOCOLS=Aave V3,Moonwell,Morpho
   ```
   Then `sudo systemctl restart mammon.service`.
5. Watch the next cycles. The vault becomes a target only when it beats the
   current venue by `MIN_APY_IMPROVEMENT` and passes the profitability gate.
   Today (Moonwell ~15%, vault ~4.4%) it won't trade.

To back out, remove `Morpho` from `SUPPORTED_PROTOCOLS` and restart. Any
existing vault position stays tracked and verified; exit it with the script
above if you want it gone.

## Testing

- Unit: `tests/unit/protocols/test_morpho_vault.py`,
  `tests/unit/blockchain/test_protocol_action_executor_morpho_vault.py`,
  `tests/unit/test_morpho_vault_wiring.py`, `tests/unit/test_morpho_vault_exit_script.py`,
  `tests/unit/protocols/test_morpho_vault_guard.py` (persisted latch, alert
  dedupe, non-blocking scan), `tests/unit/strategies/test_missing_venue_yield.py`,
  `tests/unit/test_reset_morpho_vault_guard.py`,
  `tests/unit/agents/test_vault_emergency_exit.py` (auto-exit).
- Fork E2E against real vault state (deposit → balance → partial withdraw →
  full redeem, a full `RebalanceExecutor` idle→vault→Moonwell round trip, and
  a share-price-latch auto-exit through the scheduler):
  ```bash
  anvil --fork-url https://mainnet.base.org --port 8546
  MAMMON_FORK_RPC_URL=http://127.0.0.1:8546 \
    poetry run pytest tests/integration/test_morpho_vault_fork.py -o addopts="" -v
  ```
