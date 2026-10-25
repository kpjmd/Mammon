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
   highest value seen by this process, the vault stays blocked until the
   service restarts. The 1bp tolerance absorbs a lagging RPC replica, since 2h
   of interest is about 0.1bp.

If any check fails:

- The scan raises, so the vault drops out of the cycle and gets no new
  deposits.
- An ERROR is logged with `Vault guard tripped`, plus a CRITICAL `risk_alert`
  audit event.
- Any vault position stays tracked; reconcile never closes a row it couldn't
  read.
- **Withdrawals are never gated.** You can always get out.

Deposits also refuse amounts above `maxDeposit` (vault supply caps full).
Withdrawals refuse amounts above `maxWithdraw`, which is the vault's
withdrawable liquidity, before broadcasting anything.

The optimizer will **not** exit the vault on its own when a guard trips,
because the vault vanishes from the scan. Exit manually:

```bash
sudo systemctl stop mammon.service
cd /root/mammon
/root/.local/bin/poetry run python scripts/morpho_vault_exit.py          # dry run: shows position + simulates
/root/.local/bin/poetry run python scripts/morpho_vault_exit.py --live   # full redeem; asks for a typed confirmation
sudo systemctl start mammon.service
```

The next cycle's reconcile closes the vault row and idle-deploy picks up the
USDC.

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
  `tests/unit/test_morpho_vault_wiring.py`, `tests/unit/test_morpho_vault_exit_script.py`.
- Fork E2E against real vault state (deposit → balance → partial withdraw →
  full redeem, plus a full `RebalanceExecutor` idle→vault→Moonwell round
  trip):
  ```bash
  anvil --fork-url https://mainnet.base.org --port 8546
  MAMMON_FORK_RPC_URL=http://127.0.0.1:8546 \
    poetry run pytest tests/integration/test_morpho_vault_fork.py -o addopts="" -v
  ```
