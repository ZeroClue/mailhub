## [0.1.16] - 2026-09-27

### Fixed
- **IMAP folder listing** — Fixed folder name parsing regex to handle both quoted and unquoted folder names in IMAP LIST responses
- **IMAP get/message operations** — Fixed `get`, `move`, `trash` methods to search across common folders (INBOX, Sent, Drafts, Archive, Junk, Trash) since message folder is unknown
- **IMAP send** — Fixed missing `confirm` parameter in adapter call and added `timeout` field to IMAPConfig
- **Send policy** — Added `send_policy` configuration with `allow_anywhere` and `allowlist` support, parsed from config.toml and passed to Core
- **CLI endpoints** — Fixed CLI to use correct API endpoints: `/search` (was `/messages`), `/messages` (was `/send`), `/drafts` (was `/draft`)
- **Config persistence** — IMAP/SMTP settings now properly saved to config.toml via Account serialization

### Changed
- **Version bump to 0.1.16** — All version references synchronized across pyproject.toml, mailhub/__init__.py, mailhub/app.py

## [0.1.15] - 2026-09-27

### Fixed
- **IMAP folder listing** — Fixed folder name parsing regex to handle both quoted and unquoted folder names in IMAP LIST responses. Previously only folders with special characters (quoted names) were shown.

## [0.1.14] - 2026-09-27

### Fixed
- **PyPI version conflict resolved** — Version bump to 0.1.14 after 0.1.13 already existed on PyPI from failed publish attempt
- **Version synchronization** — All version references updated consistently across pyproject.toml, mailhub/__init__.py, and mailhub/app.py

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.13] - 2026-09-27

### Fixed
- **Docker test compatibility** — Token generation now handles missing config gracefully for test environments
- **PyPI version bump** — Version 0.1.13 to resolve duplicate version on PyPI

## [0.1.12] - 2026-09-27

### Fixed
- **Docker test compatibility** — Token generation now handles missing config gracefully for test environments

## [0.1.11] - 2026-09-27

### Added
- **Auto-generated auth tokens** — `ro_token` and `full_token` are now auto-generated on `mailhub serve` startup
- **Updated README** — Documented auto-token generation, updated config examples to show tokens are optional

## [0.1.10] - 2026-09-27

### Fixed
- **Dev extra missing dependencies** — Added fastapi, uvicorn, pydantic, pydantic-settings, python-dotenv to `[dev]` extra for `mailhub serve`

## [0.1.9] - 2026-09-27

### Added
- **Per-account OAuth credentials** — Gmail/Graph accounts can now use different Google Cloud projects or Entra ID app registrations
- **Config fallback** — Provider-level `[gmail]`, `[graph]` sections serve as shared fallback

## [0.1.8] - 2026-09-27

### Added
- **Integrated IMAP wizard in `auth imap`** — Auto-detects missing IMAP/SMTP settings and runs interactive wizard
- **Per-account IMAP/SMTP config** — Settings saved to config.toml with full field serialization
- **Config template with IMAP comments** — Comprehensive commented examples in generated config

### Fixed
- **IMAP config persistence** — Settings now properly saved to config.toml via Account serialization
- **Account dataclass extended** — Added IMAP/SMTP fields (host, port, SSL, auth_method, etc.)

## [0.1.7] - 2026-09-27

### Added
- **Per-account OAuth credentials** — Gmail/Graph accounts can now use different Google Cloud projects or Entra ID app registrations
- **Config fallback** — Provider-level `[gmail]`, `[graph]` sections serve as shared fallback

## [0.1.6] - 2026-09-27

### Fixed
- **Auth command** — Added missing `--state` argument to `mailhub auth` command

## [0.1.5] - 2026-09-27

### Fixed
- **IMAP auth bug** — `Account` dataclass missing `email` field caused `AttributeError` during `mailhub auth imap`

## [0.1.4] - 2026-09-24

### Added
- **Per-account OAuth credentials** — Gmail/Graph accounts can now use different Google Cloud projects or Entra ID app registrations
- **Config fallback** — Provider-level `[gmail]`, `[graph]` sections serve as shared fallback

## [0.1.3] - 2026-09-24

### Added
- **IMAP/SMTP adapter** — Generic IMAP/SMTP support for mail operations
- **IMAP app password auth** — `mailhub auth imap <alias>` prompts for app password
- **Full mail operations via IMAP** — folders, search, get, send, draft, move, trash
- **IMAP configuration** — host, port, SSL/TLS, SMTP settings in config.toml
- **Config template** — IMAP/SMTP example in generated config
- **README** — IMAP/SMTP setup instructions

### Fixed
- Core now loads IMAP adapter alongside Gmail/Graph

## [0.1.2] - 2026-09-24

### Added
- **Health endpoints**: `GET /health` (basic) and `GET /health/detailed` (per-adapter status)
- **Graceful shutdown**: SIGTERM/SIGINT handling with adapter cleanup and flush time
- **Docker support**: Multi-stage Dockerfile, docker-compose.yml, .dockerignore
- **Docker security hardening**: non-root user, multi-stage build, no secrets in image
- **MCP server info**: `server_name`, `server_version`, `instructions` in initialize response
- **MCP capabilities**: Proper `tools` capability exposure in initialize response
- **README**: MCP configuration examples for all major AI clients (Claude Desktop, Cursor, VS Code, Windsurf, Continue, Zed, Cody)
- **Docker non-loopback support**: `MAILHUB_ALLOW_NON_LOOPBACK` env var for container deployments

### Fixed
- CI/CD: Added `[project.optional-dependencies]` for `dev` extra (pytest, pytest-asyncio)
- Docker: Fixed build context and package installation

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
