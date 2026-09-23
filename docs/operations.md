# Mailhub Operations Guide

This guide covers deploying, monitoring, backing up, and recovering Mailhub.

---

## Systemd Deployment

Mailhub provides systemd user units for the REST API and weekly credential health checks.

### Install User Units

```bash
mkdir -p ~/.config/systemd/user
cp deploy/mailhub.service ~/.config/systemd/user/
cp deploy/mailhub-doctor.service ~/.config/systemd/user/
cp deploy/mailhub-doctor.timer ~/.config/systemd/user/
systemctl --user daemon-reload
```

### Enable and Start the REST API

```bash
systemctl --user enable --now mailhub.service
```

The service runs `mailhub serve` bound to `127.0.0.1:8787`. It restarts on failure with a 3-second delay.

Check status:

```bash
systemctl --user status mailhub.service
```

View logs:

```bash
journalctl --user -u mailhub.service -f
```

### Enable Weekly Doctor Checks

```bash
systemctl --user enable --now mailhub-doctor.timer
```

The timer runs `mailhub doctor` every Monday at 04:17 AM (with a random delay up to 15 minutes). `Persistent=true` ensures it runs if the system was off at the scheduled time.

Check timer status:

```bash
systemctl --user list-timers mailhub-doctor.timer
```

Run doctor manually:

```bash
systemctl --user start mailhub-doctor.service
```

View doctor logs:

```bash
journalctl --user -u mailhub-doctor.service -f
```

---

## Doctor Command

The `mailhub doctor` command checks configured accounts and refreshes tokens as needed.

### Usage

```bash
mailhub doctor
```

### Output Interpretation

Each account produces one line:

```
<alias>: <provider> <status>  (<hint>)  <detail>
```

**Status values:**

| Status | Meaning |
|--------|---------|
| `ok` | Account healthy; access token valid or successfully refreshed. |
| `needs_reauth` | Refresh token expired or revoked; run `mailhub reauth`. |
| `error` | Unexpected failure (network, provider error, misconfiguration). |

**Hint values:**

| Hint | Action |
|------|--------|
| `refresh_ok` | Token was refreshed successfully. |
| `reauth_required` | Refresh token invalid; user must re-authorize. |
| `no_credentials` | No tokens stored; run `mailhub auth`. |
| `config_error` | Account misconfigured (missing client_id/secret). |

Exit code is `0` if all accounts are `ok`, `1` otherwise.

---

## Backup Strategy

### What to Back Up

| File | Location | Contains Secrets? | Backup Frequency |
|------|----------|-------------------|------------------|
| `config.toml` | `~/.config/mailhub/config.toml` | No | On change / weekly |
| `credentials.json` | `~/.local/state/mailhub/credentials.json` | **Yes** (refresh tokens, client secrets) | On change / weekly |
| `audit.jsonl` | `~/.local/state/mailhub/audit.jsonl` | No (sanitized) | Weekly / on mutation |

### Where to Store Backups

- **Local encrypted disk** (LUKS, FileVault, BitLocker) — preferred.
- **Offline media** (USB drive stored securely).
- **Encrypted cloud backup** (e.g., restic, borg, age-encrypted to S3) — only if you accept the risk.

**Do NOT store backups in:**
- Synced directories (Dropbox, Google Drive, OneDrive, iCloud, Syncthing) — these are not encrypted at rest by default.
- Git repositories (even private ones).
- Unencrypted network shares.

### How Often

| Scenario | Frequency |
|----------|-----------|
| After initial setup / adding accounts | Immediately |
| After `mailhub auth` / `mailhub reauth` | Immediately |
| Routine | Weekly (align with doctor timer) |
| Before system upgrades / migrations | Before |

### Using `mailhub.backup` Module

The `mailhub.backup` module provides programmatic backup/restore:

```python
from mailhub.backup import backup_all, backup_config, backup_state, backup_audit
from pathlib import Path

# Full timestamped archive (includes secrets!)
archive = backup_all(Path("/path/to/backup/dir"))

# Individual files
backup_config(Path("/path/to/backup/config.toml"))
backup_state(Path("/path/to/backup/credentials.json"))  # WARNING: contains secrets
backup_audit(Path("/path/to/backup/audit.jsonl"))
```

All outputs are created with owner-only permissions (0600 for files, 0700 for directories).

### CLI Access (if wrapped)

```bash
# Not yet exposed as CLI; use Python or copy files manually
python -c "from mailhub.backup import backup_all; from pathlib import Path; print(backup_all(Path('/tmp/mailhub-backups')))"
```

---

## Recovery Procedures

### Lost `config.toml`

1. Restore from backup:
   ```bash
   python -c "from mailhub.backup import restore_config; from pathlib import Path; restore_config(Path('/path/to/backup/config.toml'))"
   ```
   Or manually:
   ```bash
   cp /path/to/backup/config.toml ~/.config/mailhub/config.toml
   chmod 600 ~/.config/mailhub/config.toml
   ```

2. Verify:
   ```bash
   mailhub status
   ```

### Lost `credentials.json` (Tokens)

1. Restore from backup:
   ```bash
   python -c "from mailhub.backup import restore_state; from pathlib import Path; restore_state(Path('/path/to/backup/credentials.json'))"
   ```

2. If no backup exists, re-authorize each account:
   ```bash
   mailhub auth gmail personal
   mailhub auth graph work
   ```

3. Verify:
   ```bash
   mailhub doctor
   ```

### Revoked / Expired Refresh Tokens

Doctor will report `needs_reauth` with hint `reauth_required`.

1. Force re-authorization (generates new consent screen):
   ```bash
   mailhub reauth gmail personal
   # Follow the printed URL, then:
   mailhub auth gmail personal --code '<pasted-redirect-url>'
   ```

2. Verify:
   ```bash
   mailhub doctor
   ```

### Corrupted `audit.jsonl`

1. Restore from backup:
   ```bash
   python -c "from mailhub.backup import restore_audit; from pathlib import Path; restore_audit(Path('/path/to/backup/audit.jsonl'))"
   ```

2. If no backup, remove the corrupted file (audit history lost, but service continues):
   ```bash
   rm ~/.local/state/mailhub/audit.jsonl
   ```

   New audit entries will be appended on next mutation.

### Full Disaster Recovery

1. Reinstall Mailhub (same version):
   ```bash
   uv sync
   ```

2. Restore all three files from a `backup_all` archive:
   ```bash
   tar -xzf mailhub-backup-20250115-041700.tar.gz
   python -c "
   from mailhub.backup import restore_config, restore_state, restore_audit
   from pathlib import Path
   restore_config(Path('config.toml'))
   restore_state(Path('credentials.json'))
   restore_audit(Path('audit.jsonl'))
   "
   ```

3. Verify:
   ```bash
   mailhub status
   mailhub doctor
   ```

---

## Log Locations

| Log Type | Location | Access |
|----------|----------|--------|
| REST API service logs | `journalctl --user -u mailhub.service` | Systemd journal |
| Doctor service logs | `journalctl --user -u mailhub-doctor.service` | Systemd journal |
| Audit log (mutations) | `~/.local/state/mailhub/audit.jsonl` | JSONL file |

### Audit Log Format

Each line is a JSON object:

```json
{
  "timestamp": "2025-01-15T04:17:00.123456+00:00",
  "account": "personal",
  "operation": "send",
  "details": {
    "to": ["recipient@example.com"],
    "subject": "Hello",
    "message_id": "msg-123"
  }
}
```

Sensitive fields (tokens, secrets, passwords, bodies) are **never** recorded — they are redacted to `"[REDACTED]"`.

Monitor audit log size:

```bash
wc -l ~/.local/state/mailhub/audit.jsonl
du -h ~/.local/state/mailhub/audit.jsonl
```

Consider log rotation if it grows large (not built-in; use `logrotate` or similar).

---

## Credential Rotation

### When to Rotate

- Refresh token revoked (doctor shows `needs_reauth`).
- Suspected token compromise.
- Provider forces re-consent (scope changes, policy updates).
- Periodic rotation (e.g., annually) as security hygiene.

### Reauth Flow

```bash
# 1. Initiate forced consent
mailhub reauth gmail personal

# 2. Open the printed URL in browser, complete consent

# 3. Exchange the redirect URL for new tokens
mailhub auth gmail personal --code '<full-redirect-url-from-browser>'

# 4. Verify
mailhub doctor
```

The `reauth` command generates an authorization URL with `prompt=consent` (Google) or equivalent, forcing the provider to show the consent screen and issue a new refresh token.

---

## Monitoring Checklist

### Daily (Automated)

- [ ] `mailhub-doctor.timer` ran successfully (check `systemctl --user list-timers`).
- [ ] No `error` or `needs_reauth` statuses in doctor output.

### Weekly

- [ ] Run `mailhub doctor` manually and review output.
- [ ] Create backup via `backup_all()` or manual copy.
- [ ] Check audit log size (`wc -l ~/.local/state/mailhub/audit.jsonl`).

### Monthly

- [ ] Verify backup integrity (test restore to temporary location).
- [ ] Review `journalctl --user -u mailhub.service --since="1 month ago"` for errors.
- [ ] Confirm systemd services are enabled and active.

### On Alert / Incident

- [ ] Check `journalctl --user -u mailhub.service -n 100` for recent errors.
- [ ] Run `mailhub doctor` to diagnose account health.
- [ ] Check audit log for unexpected mutations.
- [ ] If tokens compromised: revoke at provider, run `mailhub reauth`, restore from clean backup.

---

## Security Notes

- **`~/.config/mailhub/` and `~/.local/state/mailhub/` are NOT for synced backup.** They contain live credentials and should be treated as runtime state.
- Backup files containing `credentials.json` **must** be stored with 0600 permissions on encrypted media.
- Never log or print secrets during backup/restore operations. The backup module uses `warnings.warn()` for caller awareness, not logging.
- Restore operations use `CredentialStore` for atomic writes, preventing partial/corrupted state.
- The REST API binds only to `127.0.0.1` — no network exposure.
