# Off-droplet DB backup replication

`mammon-backup.timer` runs `mammon-backup.service` daily at 03:00 UTC:

1. `ExecStart` — `scripts/backup_db.py` writes a consistent online snapshot to
   `data/backups/mammon_<UTC stamp>.db.gz` and prunes to the newest 14.
2. `ExecStartPost` — `scripts/replicate_backups.py` copies `data/backups/` to the
   rclone remote named by `BACKUP_REMOTE` in `/root/mammon/.env`, then confirms the
   newest file is listed remotely.

The ledger (positions, transactions, decisions, rebalance intents) holds no keys,
but it does hold the wallet address and full trade history, so it is encrypted
client-side. **`BACKUP_REMOTE` must be an rclone `crypt` remote; the script
refuses to upload to anything else.** `rclone copy` (not `sync`) is used, so the
bucket keeps every daily file even after local pruning.

Any failure — `BACKUP_REMOTE` unset, remote missing or not `crypt`, rclone
missing, non-zero exit, timeout, newest file absent after copy — posts
`[ERROR] MAMMON: DB backup replication failed` to `ALERT_WEBHOOK` (via
`scripts/alert_webhook.py`), exits 1, and marks the unit failed
(`systemctl status mammon-backup.service`).

## Live deployment

| Piece | Value |
|---|---|
| Storage | Cloudflare R2, private bucket `mammon-backups` |
| Credentials | R2 API token, **Object Read & Write**, scoped to `mammon-backups` only |
| rclone | v1.75.2 from the official `.deb`, signature-verified (Ubuntu 22.04's apt package is 1.53, which predates R2 support) |
| Remotes | `r2` (type `s3`, provider `Cloudflare`) → `mammon-crypt` (type `crypt`, over `r2:mammon-backups`) |
| `.env` | `BACKUP_REMOTE=mammon-crypt:` (the trailing colon is required) |
| Secrets kept offline | R2 account ID, bucket name, crypt **password** and **salt** (`password2`) |

## One-time setup on the droplet

### 1. Cloudflare dashboard

1. **R2 Object Storage → Create bucket**: `mammon-backups`, location Automatic.
   (Cloudflare may ask for a payment method to enable R2, even on the free tier.)
2. **R2 → Manage API tokens → Create API token**: permission **Object Read &
   Write**, *specify bucket* → `mammon-backups` only, no expiry. Record the
   **Access Key ID**, **Secret Access Key** (shown once), and **Account ID**; the
   endpoint is `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.

### 2. Install rclone (verified)

```bash
cd /tmp
curl -fsSLO https://downloads.rclone.org/v1.75.2/rclone-v1.75.2-linux-amd64.deb
curl -fsSLO https://downloads.rclone.org/v1.75.2/SHA256SUMS
gpg --keyserver keyserver.ubuntu.com --receive-keys FBF737ECE9F8AB18604BD2AC93935E02FF3B54FA
gpg --verify SHA256SUMS            # expect "Good signature", fingerprint …FF3B 54FA
gpg --decrypt SHA256SUMS 2>/dev/null | sha256sum -c --ignore-missing   # must print: …deb: OK
apt install -y ./rclone-v1.75.2-linux-amd64.deb
rclone version
```

The "not certified with a trusted signature" gpg warning is normal; check the
fingerprint instead (see <https://rclone.org/release_signing/>). **Stop if the
checksum line is not `OK`.**

If apt shows a *"Daemons using outdated libraries — which services should be
restarted?"* dialog (needrestart), **untick everything and choose `<Ok>`**:
rclone changes no shared libraries, and restarting `dbus`/`systemd-logind` over
SSH can drop the session. Those daemons pick up library updates on the next
planned reboot.

### 3. Create the `r2` remote

The `read` prompts keep the secret out of shell history (run in one shell):

```bash
read -rp  "R2 account ID: " R2_ACCOUNT
read -rp  "R2 access key ID: " R2_KEY
read -rsp "R2 secret access key: " R2_SECRET; echo
rclone config create r2 s3 provider=Cloudflare env_auth=false \
  access_key_id="$R2_KEY" secret_access_key="$R2_SECRET" region=auto \
  endpoint="https://${R2_ACCOUNT}.r2.cloudflarestorage.com" acl=private no_check_bucket=true
unset R2_KEY R2_SECRET
rclone lsf r2:mammon-backups       # empty bucket → no output, no error
```

`no_check_bucket=true` is required: a bucket-scoped Object Read & Write token
cannot list or create buckets. `rclone config create` may echo the resulting
config (including the secret) to the terminal — don't paste that output anywhere.

### 4. Create the `mammon-crypt` remote

```bash
P1=$(openssl rand -hex 24); P2=$(openssl rand -hex 24)
printf 'crypt password: %s\ncrypt salt:     %s\n' "$P1" "$P2"
```

**Store both values in your password manager now** (with the account ID, bucket
name, and `filename_encryption=standard`). They are the only way to decrypt the
backups if the droplet is lost; an R2 token can be re-issued, these cannot, and
changing them later does not re-key files already uploaded.

```bash
rclone config create mammon-crypt crypt remote=r2:mammon-backups \
  filename_encryption=standard directory_name_encryption=true \
  password="$P1" password2="$P2" --obscure
unset P1 P2; clear
rclone listremotes --long          # expect  r2: s3   and   mammon-crypt: crypt
```

`--obscure` forces rclone to obscure both values in `rclone.conf`. Obscured is
*not* encrypted — anyone with root on the droplet can recover them — which is
why the offline copy above, not `rclone.conf`, is the source of truth.

### 5. Point MAMMON at it

Add `BACKUP_REMOTE=mammon-crypt:` to `/root/mammon/.env` (back up `.env` first;
use `printf '\nBACKUP_REMOTE=mammon-crypt:\n' >> .env` so a missing trailing
newline cannot join it onto the previous line). No service restart is needed:
the script reads `.env` on every run.

If `scripts/mammon-backup.service` changed, re-install it — the units in
`/etc/systemd/system/` are **copies**, not symlinks:

```bash
cd /root/mammon && git pull
cp scripts/mammon-backup.service /etc/systemd/system/
systemctl daemon-reload
```

### 6. Verify

```bash
systemctl start mammon-backup.service
journalctl -u mammon-backup -n 20 --no-pager   # "OK: wrote …" then "OK: replicated mammon_….db.gz to mammon-crypt:"
rclone lsf mammon-crypt:                       # readable mammon_….db.gz names
rclone lsf r2:mammon-backups                   # scrambled names only (encrypted at rest)
```

**Alert path** — point the script at the non-crypt remote for one run via the
environment (overrides `.env`, nothing is edited). It must refuse, exit 1,
upload nothing, and a Discord error must arrive:

```bash
cd /root/mammon && BACKUP_REMOTE=r2:mammon-backups python3 scripts/replicate_backups.py
```

Expected output: `ERROR: remote 'r2' is type 's3', not 'crypt' — refusing to
upload the ledger unencrypted`. If the Discord message does not arrive, check
`ALERT_WEBHOOK` in `.env`; the stdlib scripts log `Alert POST failed: …` to
stderr when a POST is rejected.

Optional: an R2 lifecycle rule (e.g. delete after 365 days) if unbounded daily
history is unwanted; the script never deletes remote files.

## Restore

```bash
d=$(mktemp -d)
rclone copy mammon-crypt:mammon_<stamp>.db.gz "$d/"
gunzip "$d/mammon_<stamp>.db.gz"
python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select count(*) from positions').fetchone())" "$d/mammon_<stamp>.db"
```

Stop `mammon.service` before swapping a restored file into `data/mammon.db`;
on restart the loop reconciles positions from on-chain state at cycle start.

### Disaster recovery (droplet lost)

On any machine: install rclone as in step 2, recreate `r2` with a fresh R2 token
(step 3), then recreate `mammon-crypt` with the **same password and salt** from
your password manager (`password=… password2=… --obscure`, same
`filename_encryption=standard`). `rclone lsf mammon-crypt:` should then list the
readable backup names, and the restore above works unchanged.
