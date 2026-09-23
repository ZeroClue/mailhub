# M1 — Foundation Engineering Brief

## Outcome

Create an installable Python 3.11+ foundation for Mailhub. It must start a local, read-only stdio MCP server and provide configuration, account/capability discovery, and secure credential-state primitives. It must not contact real providers or require OAuth console setup.

## In Scope

- `pyproject.toml` with pinned runtime and development dependencies, package entry points, and test configuration.
- `mailhub/` package with configuration validation, account models, capability declarations, credential-state storage, and a minimal read-only MCP server.
- Commands for configuration initialization and local status. `mailhub mcp` defaults to read-only mode.
- Strict local permissions, atomic state writes, and a transaction-level lock abstraction suitable for later token refreshes.
- Unit tests for configuration, capabilities, file permissions, atomic-state behavior, and read-only MCP tool registration.
- Concise user-facing setup and test commands in project documentation where needed.

## Explicitly Out of Scope

- Gmail, Graph, IMAP/SMTP, CalDAV/CardDAV, tasks, and live OAuth requests.
- REST daemon, systemd units, attachment handling, provider credentials, and any real mailbox access.
- Full-mode mutation tools. A full-mode placeholder may exist only when it cannot perform a mutation.

## Required Design Constraints

- Follow current `SPEC.md`; treat `REFERENCE.md` as historical only.
- Use XDG paths under `~/.config/mailhub` and `~/.local/state/mailhub` by default, with testable path injection.
- Never write secrets to stdout, logs, fixtures, or repository files.
- `mailhub mcp --mode ro` may advertise only read-only tools. Invalid modes fail clearly.
- Configuration must reject duplicate aliases and unsupported account/capability combinations.
- No listening socket is created in M1.

## Acceptance Checks

```bash
uv run pytest
uv run mailhub init --help
uv run mailhub status --help
uv run mailhub mcp --help
```

The test suite must use temporary directories and mocked interfaces only. The implementation report must list changed files, commands run, and any assumptions. An independent reviewer must assess the final diff before orchestration approval.
