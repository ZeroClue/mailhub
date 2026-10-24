# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Mailhub** is a local, MCP-first personal-operations hub for AI assistants. It provides a unified interface to email, calendar, contacts, and tasks across multiple providers (Gmail, Microsoft Graph, IMAP/SMTP, CalDAV, CardDAV).

The project exposes three surfaces:
- **MCP server** (stdio): Model Context Protocol server with read-only and full modes
- **REST API** (localhost:8787): FastAPI server bound exclusively to 127.0.0.1
- **CLI tools**: `mailhub` (admin) and `mail` (user-facing REST client)

## Development Commands

```bash
# Install dependencies
uv sync --extra dev

# Run tests
uv run pytest                    # All tests
uv run pytest tests/test_core.py # Single test file
uv run pytest -k test_name       # Single test by name
uv run pytest -v                 # Verbose output

# Linting and formatting
uv run ruff check mailhub tests  # Lint
uv run ruff format mailhub tests # Format
uv run ruff check --fix          # Auto-fix issues

# Security scanning
uv run bandit -r mailhub -f json -o bandit.json
uv run safety check

# Run the application locally
uv run mailhub init              # Initialize config
uv run mailhub serve             # Start REST API server
uv run mailhub mcp --mode ro     # Start MCP server (read-only)
uv run mailhub mcp --mode full   # Start MCP server (full access)
uv run mailhub doctor            # Health check

# Build package
uv build                         # Creates dist/
```

## Architecture

### Core Layer Pattern

The architecture follows a **Core + Adapters** pattern:

1. **Core** (`core.py`): Central policy engine that:
   - Manages account registry and credentials via `CredentialStore`
   - Handles OAuth token refresh (delegates to `oauth.py`)
   - Enforces send policy (allowlist, confirmation requirements)
   - Implements retry logic with exponential backoff
   - Writes audit logs (sanitizes sensitive fields)
   - Routes operations to provider-specific adapters

2. **Adapters** (per-provider): Each adapter implements the same operation interface:
   - `GmailAdapter` - Gmail API (REST)
   - `GraphAdapter` - Microsoft Graph API (REST)
   - `IMAPAdapter` - Generic IMAP/SMTP servers
   - Calendar adapters: `GoogleCalendarAdapter`, `GraphCalendarAdapter`, `CalDAVAdapter`
   - Contact adapters: `GooglePeopleAdapter`, `GraphPeopleAdapter`, `CardDAVAdapter`
   - Task adapters: `GraphTasksAdapter`, `CalDAVTasksAdapter`

Core instantiates adapters lazily and routes by account provider. Adapters receive `Core` in their constructor and call back to `_ensure_access_token(alias)` for auth.

### Configuration Flow

- **Config file** (`~/.config/mailhub/config.toml`): Accounts, OAuth client IDs, send policy
- **Credential store** (`~/.local/state/mailhub/credentials.json`): OAuth tokens, IMAP passwords
  - Owner-only (0600 permissions)
  - Atomic writes via temp file + `os.replace()`
  - Process-wide lock using `fcntl` (Unix-only)

`Config` is immutable (frozen dataclasses). `CredentialStore` handles all mutable state with transactional locking.

### OAuth Flow (PKCE)

1. `mailhub auth <provider> <alias>` generates authorization URL with PKCE challenge
2. User completes browser OAuth flow, pastes redirect URL back
3. CLI exchanges code + PKCE verifier for access/refresh tokens
4. Tokens stored in credential store with expiry timestamp
5. Core auto-refreshes expired tokens before adapter calls

See `oauth.py` for PKCE implementation. `ReauthNeeded` exception triggers interactive re-auth.

### Security Model

- REST server binds **only** to `127.0.0.1` (checked at startup via `_validate_host`)
- Auth tokens (`ro_token`, `full_token`) auto-generated on `mailhub serve` startup
- Send operations require `confirm=true` + recipient passes allowlist (glob patterns)
- No hard-delete operations (only trash/cancel)
- Audit log (`~/.local/state/mailhub/audit.jsonl`) never records tokens or message bodies
- Sensitive fields (`_SENSITIVE_FIELDS` in `core.py`) redacted from logs

### MCP Server (`mcp.py`)

Uses `fastmcp` library. Two modes:
- **Read-only** (`--mode ro`): Only `mailhub_status` tool
- **Full** (`--mode full`): All tools including mutations

Tools are module-level functions to avoid closure issues with `fastmcp`. Core instance stored in module-level `_core_holder` dict.

### Testing Patterns

Tests use `pytest` with:
- `tmp_path` fixture for isolated config/state files
- Mocked HTTP responses via `monkeypatch` or test doubles
- Account setup helpers in test files (e.g., `_make_account`, `_make_config`)

When adding provider features, update both the adapter and corresponding test file (e.g., `mailhub/imap.py` ↔ `tests/test_imap.py`).

## Common Workflows

### Adding a new provider capability

1. Update `PROVIDER_CAPABILITIES` in `config.py` if adding new capability type
2. Implement adapter methods in `mailhub/<provider>.py`
3. Add routing logic in `core.py` if needed (for new operation types)
4. Write tests in `tests/test_<provider>.py`
5. Update MCP tool definitions in `mcp.py` if exposing to AI agents
6. Document in README.md under Features section

### Modifying send policy

Send policy is enforced in `Core._check_send_policy()`. All send operations flow through this gate. The allowlist uses `fnmatch` glob patterns.

### Working with credentials

Always use `CredentialStore.transaction()` context manager when reading + modifying credentials to prevent race conditions across processes. The lock file is per-credential-store (`.credentials.json.lock`).

### Debugging auth issues

1. Check `~/.local/state/mailhub/credentials.json` for token expiry (`expires_at` is Unix timestamp)
2. Run `mailhub doctor` to validate config and credential state
3. Check OAuth scopes match provider requirements (in `oauth.py` constants)
4. For IMAP: verify app passwords are used if 2FA is enabled

## CI/CD

GitHub Actions workflows in `.github/workflows/`:
- **ci.yml**: Lint (ruff), security scan (bandit, safety), tests, Docker build
- **publish.yml**: PyPI publish on version tags (`v*.*.*`)
- **docker.yml**: GHCR publish on version tags

Version must be bumped in `pyproject.toml` before tagging. The CI only publishes on tags, not on `main` branch pushes.

## Important Files

- `core.py`: Start here to understand request flow
- `config.py`: Account model and TOML parsing
- `store.py`: Atomic credential persistence
- `oauth.py`: PKCE OAuth flow for Google/Microsoft
- `app.py`: FastAPI REST endpoints + token generation
- `mcp.py`: MCP server tool definitions
- `cli.py`: Admin CLI commands (init, auth, config, serve, mcp, doctor)
- `mail_cli.py`: User-facing CLI (thin HTTP client to REST API)

## Notes

- The project uses XDG Base Directory specification for config/state paths
- All timestamps are Unix timestamps (float) for OAuth expiry
- Message bodies are treated as untrusted input (HTML sanitization in `util.py`)
- Adapter HTTP clients should be closed via `close()` method during graceful shutdown
- The REST server generates auth tokens on startup if missing—never commit tokens to config.toml
