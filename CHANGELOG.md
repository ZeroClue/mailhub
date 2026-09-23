# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-09-23

### Added
- **Health endpoints**: `GET /health` (basic) and `GET /health/detailed` (per-adapter status)
- **Graceful shutdown**: SIGTERM/SIGINT handling with adapter cleanup and flush time
- **Docker support**: Multi-stage Dockerfile, docker-compose.yml, .dockerignore
- **Docker security hardening**: non-root user, multi-stage build, no secrets in image
- **MCP server info**: `server_name`, `server_version`, `instructions` in initialize response
- **MCP capabilities**: Proper `tools` capability exposure in initialize response
- **README**: MCP configuration examples for all major AI clients (Claude Desktop, Cursor, VS Code, Windsurf, Continue, Zed, Cody)

### Fixed
- CI/CD: Added `[project.optional-dependencies]` for `dev` extra (pytest, pytest-asyncio)

## [0.1.0] - 2026-09-23

### Added

#### M1 - Foundation
- `mailhub init` — initialize configuration and credential state files with secure permissions
- `mailhub status` — list configured accounts without contacting providers
- `mailhub mcp --mode ro` — read-only stdio MCP server for AI agents
- `mailhub config` — configuration management with validation
- Configuration system with XDG paths (`~/.config/mailhub`, `~/.local/state/mailhub`)
- Credential store with atomic writes, 0600 permissions, fcntl cross-process lock
- TOML configuration with provider capability validation
- Owner-only file permissions (0600/0700) and atomic writes via tempfile + os.replace

#### M2 - Mail
- **Gmail adapter** — labels, search, get, send, draft, move, trash, attachments
- **Microsoft Graph adapter** — folders, search, get, send, draft, move, trash (returns new ID on move)
- **Core policy engine** — allowlist enforcement, `confirm=true` gate, audit logging, retry logic
- **OAuth PKCE flow** — Google (gmail.modify scope) and Microsoft Graph (offline_access, Mail.ReadWrite, Mail.Send, MailboxSettings.ReadWrite, User.Read)
- **CLI mail commands** — `mail send`, `mail search`, `mail get`, `mail folders`, `mail draft`
- **REST API** — FastAPI server binding 127.0.0.1 only, bearer token auth (ro/full scopes)
- Send allowlist with glob patterns, `allow_anywhere` override
- Audit logging (never records tokens/bodies, sanitizes sensitive fields)
- Retry logic with bounded attempts, exponential backoff, Retry-After header support
- IMAP/SMTP adapter stub (read-only)

#### M3 - Calendar
- **Google Calendar adapter** — calendars, events, search, free/busy, create/update/delete events
- **Microsoft Graph Calendar adapter** — calendars, events, free/busy, create/update/delete
- **CalDAV adapter** — read-only calendar discovery and event listing
- Free/busy queries for both providers
- Event recurrence support
- Event attendee management (creation/cancellation notifications)

#### M4 - Contacts & Tasks
- **Google People adapter** — contacts CRUD, contact groups, search
- **Microsoft Graph People adapter** — contacts, contact folders, CRUD
- **CardDAV adapter** — read-only contact listing
- **Microsoft Graph Tasks/To Do adapter** — task lists, tasks CRUD, recurrence, due dates
- **CalDAV VTODO adapter** — read-only task listing
- Task lists with color coding, priorities, due dates, recurrence

#### M5 - Operations
- **Backup/Restore** — `mailhub backup config|state|audit|all`, `mailhub restore config|state|audit`
- **Systemd integration** — `deploy/mailhub.service`, `mailhub-doctor.service`, `mailhub-doctor.timer`
- **Backup/Restore utilities** — atomic, owner-only permissions, tar.gz archives
- **Systemd user units** — `mailhub.service` (REST API), `mailhub-doctor.timer` (weekly Mon 04:17)
- `mailhub doctor` — health checks, token refresh, provider connectivity
- `mailhub config` — `list`, `add-account`, `validate`, `doctor`, `setup-google`, `setup-microsoft`, `remove-account`
- Audit logging (sanitized, never records tokens/bodies)
- Systemd user units with `loginctl enable-linger` support

### Security
- REST server binds exclusively to 127.0.0.1 (never 0.0.0.0)
- No hard-delete — only trash/cancel operations
- All mutations require `confirm=true` + recipient allowlist
- Audit logging sanitizes sensitive fields (tokens, secrets, passwords)
- Credentials stored with 0600 permissions, atomic writes, fcntl cross-process lock
- OAuth PKCE with random state, proper scopes (Google: gmail.modify; Graph: offline_access, Mail.ReadWrite, Mail.Send, MailboxSettings.ReadWrite, User.Read)
- Token refresh on 401 with forced refresh, refresh tokens stored securely

### Developer Experience
- `mail` CLI — thin HTTP client to REST API (`mail send`, `search`, `get`, `folders`, `draft`)
- `mailhub --generate-completion bash|zsh|fish` — shell completions for both `mailhub` and `mail`
- Man pages: `man mailhub`, `man mail` (installable via `docs/man/`)
- Systemd service files in `deploy/`
- Comprehensive test suite (267 tests, mocked HTTP, no live provider calls)
- MCP server with read-only (`ro`) and full modes via stdio

### Documentation
- Comprehensive README with quick start, configuration, security, architecture
- Man pages: `docs/man/mailhub.1`, `docs/man/mail.1`
- Architecture docs in `docs/decisions/` (ADR style)
- Milestone specs in `docs/milestones/`
- Architecture decision records in `docs/decisions/`

## [Unreleased]

### Planned
- Homebrew tap formula
- Arch/AUR package (PKGBUILD)
- CalDAV/CardDAV write support (create/update/delete)
- SSE/Streamable HTTP transport for MCP

---

**Full Changelog**: https://github.com/ZeroClue/mailhub/commits/main
