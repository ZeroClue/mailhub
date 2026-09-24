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

---

## Docker Deployment

Mailhub provides official Docker images via GitHub Container Registry for containerized deployments.

### Quick Start

```bash
# Pull the image
docker pull ghcr.io/zeroclue/zc-mailhub:v0.1.2

# Run with docker-compose (recommended)
docker compose up -d

# Or run directly
docker run -d \
  -p 8787:8787 \
  -v mailhub-config:/home/mailhub/.config/mailhub \
  -v mailhub-state:/home/mailhub/.local/state/mailhub \
  -e MAILHUB_ALLOW_NON_LOOPBACK=1 \
  ghcr.io/zeroclue/zc-mailhub:v0.1.2 \
  serve --host 0.0.0.0
```

### docker-compose.yml

The provided `docker-compose.yml` runs two services:

| Service | Description | Port | Command |
|---------|-------------|------|---------|
| `mailhub` | REST API server | 8787 | `mailhub serve --host 0.0.0.0` |
| `mailhub-mcp` | MCP server (full mode) | stdio | `mailhub mcp --mode full` |

```yaml
version: '3.8'

services:
  mailhub:
    image: ghcr.io/zeroclue/zc-mailhub:v0.1.2
    container_name: mailhub
    command: ["mailhub", "serve", "--host", "0.0.0.0"]
    ports:
      - "8787:8787"
    environment:
      - MAILHUB_CONFIG=/home/mailhub/.config/mailhub/config.toml
      - MAILHUB_ALLOW_NON_LOOPBACK=1
    volumes:
      - mailhub-config:/home/mailhub/.config/mailhub
      - mailhub-state:/home/mailhub/.local/state/mailhub
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8787/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  mailhub-mcp:
    image: ghcr.io/zeroclue/zc-mailhub:v0.1.2
    container_name: mailhub-mcp
    entrypoint: ["mailhub", "mcp", "--mode", "full"]
    volumes:
      - mailhub-config:/home/mailhub/.config/mailhub
      - mailhub-state:/home/mailhub/.local/state/mailhub
    restart: unless-stopped

volumes:
  mailhub-config:
  mailhub-state:
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MAILHUB_CONFIG` | No | `/home/mailhub/.config/mailhub/config.toml` | Config file path |
| `MAILHUB_ALLOW_NON_LOOPBACK` | For Docker | `0` | Set to `1` to allow binding to `0.0.0.0` |

**Important**: In Docker, the server must bind to `0.0.0.0` to accept connections from outside the container. Set `MAILHUB_ALLOW_NON_LOOPBACK=1` and use `--host 0.0.0.0`.

### Configuration in Docker

Configuration and state are persisted via Docker volumes:

```yaml
volumes:
  mailhub-config:
  mailhub-state:
```

These correspond to:
- `mailhub-config` → `~/.config/mailhub/` (config.toml)
- `mailhub-state` → `~/.local/state/mailhub/` (credentials.json, audit.jsonl)

### Initial Setup in Docker

```bash
# 1. Start empty volumes
docker compose up -d

# 2. Run init inside the container
docker compose exec mailhub mailhub init

# 3. Configure providers (interactive or flags)
docker compose exec mailhub mailhub config setup-google
docker compose exec mailhub mailhub config setup-microsoft

# 4. Add accounts
docker compose exec mailhub mailhub config add-account --alias me --provider gmail --capabilities mail --email me@gmail.com

# 5. Authorize accounts (paste redirect URL)
docker compose exec mailhub mailhub auth gmail me --code '<pasted-redirect-url>'

# 6. Verify health
docker compose exec mailhub mailhub doctor

# 7. View logs
docker compose logs -f mailhub
```

### MCP Server in Docker

To run the MCP server over stdio for AI clients:

```bash
# One-off run
docker compose run --rm mailhub-mcp

# Or with docker run
docker run -it --rm \
  -v mailhub-config:/home/mailhub/.config/mailhub \
  -v mailhub-state:/home/mailhub/.local/state/mailhub \
  ghcr.io/zeroclue/zc-mailhub:v0.1.2 \
  mcp --mode full
```

### AI Client Configuration (Docker)

For MCP clients using Docker:

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "docker",
      "args": ["run", "-i", "--rm", 
        "-v", "mailhub-config:/home/mailhub/.config/mailhub",
        "-v", "mailhub-state:/home/mailhub/.local/state/mailhub",
        "ghcr.io/zeroclue/zc-mailhub:v0.1.2",
        "mcp", "--mode", "full"]
    }
  }
}
```

### Health Checks

Docker healthcheck uses the built-in `/health` endpoint:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8787/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

Detailed health via `/health/detailed`:
```bash
curl http://localhost:8787/health/detailed
```

### Security Hardening

The Docker image follows security best practices:

- **Multi-stage build** — builder stage for dependencies, minimal runtime image
- **Non-root user** — runs as `mailhub` user (UID/GID 999)
- **No secrets in image** — configuration and credentials mounted as volumes
- **Read-only root filesystem** — add `read_only: true` to docker-compose
- **Dropped capabilities** — `cap_drop: ["ALL"]`, `no-new-privileges: true`

To enable read-only root filesystem:
```yaml
services:
  mailhub:
    read_only: true
    tmpfs:
      - /tmp
      - /run
```

### Logs in Docker

```bash
# View all logs
docker compose logs -f

# View specific service
docker compose logs -f mailhub
docker compose logs -f mailhub-mcp

# Timestamps
docker compose logs -t mailhub
```

### Backup in Docker

Volumes are backed up using Docker volume commands:

```bash
# Backup volumes
docker run --rm \
  -v mailhub-config:/source \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/mailhub-config-$(date +%Y%m%d).tar.gz -C /source .

docker run --rm \
  -v mailhub-state:/source \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/mailhub-state-$(date +%Y%m%d).tar.gz -C /source .

# Restore volumes
docker run --rm \
  -v mailhub-config:/target \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/mailhub-config-20260924.tar.gz -C /target
```

### Updating

```bash
# Pull latest image
docker compose pull

# Recreate containers
docker compose up -d

# Or specific version
docker pull ghcr.io/zeroclue/zc-mailhub:v0.1.3
docker compose up -d
```

### Troubleshooting Docker

| Issue | Solution |
|-------|----------|
| Health check fails | Check `docker compose logs mailhub` |
| Port 8787 in use | Change host port in `docker-compose.yml` |
| Permission denied on volumes | Ensure volumes owned by UID 999 |
| Config not found | Verify `MAILHUB_CONFIG` path matches volume mount |
| Tokens not persisting | Check `mailhub-state` volume is mounted |
| MCP not working | Use `-i` flag for interactive stdio |

