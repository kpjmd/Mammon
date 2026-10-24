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
`[ERROR] MAMMON: DB backup replication failed` to `ALERT_WEBHOOK`, exits 1, and
marks the unit failed (`systemctl status mammon-backup.service`).

## One-time setup on the droplet

1. **Bucket + scoped key.** Create a private bucket (e.g. DigitalOcean Spaces
   `mammon-backups`) and an access key limited to that one bucket
   (read/write/list). Do not reuse an account-wide key.
2. **Install rclone:** `apt install -y rclone` (any version with
   `listremotes --long`).
3. **`rclone config`** (interactive, so no secrets land in shell history):
   - `n` → name `spaces` → type `s3` → provider `DigitalOcean` (or your
     provider) → access key / secret → endpoint `<region>.digitaloceanspaces.com`.
   - `n` → name `mammon-crypt` → type `crypt` → remote `spaces:mammon-backups`
     → filename encryption `standard` → let rclone **generate** both passwords.
4. **Store the crypt passwords offline** with the CDP secrets. Also copy
   `/root/.config/rclone/rclone.conf` off the droplet: without it (or the two
   passwords) the backups cannot be decrypted after losing the droplet.
5. **Point MAMMON at it:** add `BACKUP_REMOTE=mammon-crypt:` to
   `/root/mammon/.env`.
6. **Pick up the unit change:**
   ```bash
   cd /root/mammon && git pull
   ls -l /etc/systemd/system/mammon-backup.service   # symlink → repo, or a copy?
   cp scripts/mammon-backup.service /etc/systemd/system/   # only if it is a copy
   systemctl daemon-reload
   ```
7. **Test it now** rather than waiting for 03:00:
   ```bash
   systemctl start mammon-backup.service
   journalctl -u mammon-backup -n 20 --no-pager   # expect "OK: replicated mammon_….db.gz"
   rclone lsf mammon-crypt:                       # decrypted names
   rclone lsf spaces:mammon-backups               # encrypted names only
   ```
8. **Prove the alert path:** temporarily set `BACKUP_REMOTE=spaces:` (a non-crypt
   remote), `systemctl start mammon-backup.service`, confirm the Discord error
   arrives and nothing was uploaded, then restore `mammon-crypt:`.

Optional: add a bucket lifecycle rule (e.g. expire after 365 days) if unbounded
daily history is unwanted; the script never deletes remote files.

## Restore

```bash
mkdir -p /tmp/restore
rclone copy mammon-crypt:mammon_<stamp>.db.gz /tmp/restore/
gunzip /tmp/restore/mammon_<stamp>.db.gz
python3 -c "import sqlite3; print(sqlite3.connect('/tmp/restore/mammon_<stamp>.db').execute('select count(*) from positions').fetchone())"
```

Stop `mammon.service` before swapping a restored file into `data/mammon.db`;
on restart the loop reconciles positions from on-chain state at cycle start.
