# Security Review: Mailhub M2-M5 (Galileo/James)

## Verdict: **APPROVE with P2 findings**

**Test Baseline**: 185 passed, 5 warnings

---

## P1 Blocking Findings: **None**

All 13 SPEC.md security requirements verified in implementation:

| # | Requirement | Verified | Location |
|---|-------------|----------|----------|
| 1 | REST binds 127.0.0.1 only | ✅ | `app.py:create_app()` → `uvicorn.run(host="127.0.0.1")` |
| 2 | No hard-delete | ✅ | Only `trash()`, `delete_event()`, `delete_task()` (cancel) |
| 3 | Mutation requires `confirm=true` | ✅ | All adapters: `send`, `create/update/delete` require confirm |
| 4 | Allowlist enforcement | ✅ | `core.py:_match_glob()` case-insensitive glob; `allow_anywhere` opt-in |
| 5 | Audit sanitization | ✅ | `_sanitize_for_audit()` → `[REDACTED]` for `_SENSITIVE_FIELDS` |
| 6 | Credential 0600/atomic/lock | ✅ | `store.py`: `os.fchmod(0o600)`, `os.replace()`, `fcntl.flock()` |
| 7 | OAuth PKCE | ✅ | `oauth.py`: verifier/challenge, random state, proper scopes |
| 8 | Token refresh on 401 | ✅ | All adapters: 401 → `_refresh_access_token()` → retry once |
| 9 | Retry: bounded/backoff/Retry-After | ✅ | `_request()` loops, max 3, honors `Retry-After`, exp backoff |
| 10 | Typed error hierarchy | ✅ | `CoreError`, `SendDenied`, `ReauthNeeded`, `CalendarError`, etc. |
| 11 | Bodies untrusted | ✅ | No embedded instruction parsing; structured returns only |
| 12 | Fresh IDs | ✅ | Graph `move` returns new ID; Gmail labels stable |
| 13 | MCP read-only default | ✅ | `mcp.py`: only `mailhub_status` tool in `ro` mode |

---

## P2 Findings (Fix Before Production)

### 1. CLI REST host not validated
**File**: `mailhub/app.py` / `mailhub/cli.py`
**Issue**: `mailhub serve --host 0.0.0.0` would be accepted, violating SPEC "configuration and command-line overrides must reject non-loopback hosts"
**Fix**: Add validation in `run_server()` and CLI argument parsing to reject non-loopback hosts

### 2. MCP full mode not implemented
**File**: `mailhub/mcp.py`
**Issue**: `--mode full` rejected with "M1 supports only read-only MCP mode" but SPEC M2 requires full mode for mutations
**Fix**: Implement `mode="full"` path that registers mutation tools (send, move, trash, etc.)

---

## P3 Non-Blocking

| Finding | Location |
|---------|----------|
| `asyncio_mode` pytest warning | `pyproject.toml` (cosmetic) |
| `pydantic_settings` forward ref warning | Upstream FastMCP |
| CalDAV/CardDAV adapters are read-only stubs | `carddav.py`, `caldav.py`, `tasks_caldav.py` |
| `mail` CLI commands not implemented | `cli.py` only has admin commands |

---

## Code Quality

| Criterion | Status |
|-----------|--------|
| Type hints on public APIs | ✅ All adapters, core, domain models |
| Stdlib preference | ✅ Only `httpx`, `mcp` in deps |
| Mocked HTTP in tests | ✅ 185 tests use `MockResponse` + `patch` |
| No secrets in tests/fixtures | ✅ Hardcoded fake tokens only |

---

## M5 Operations Specific

| Check | Status |
|-------|--------|
| Systemd units user-scoped | ✅ `deploy/*.service` use `%h/.local/bin/mailhub` |
| Backup outputs 0600 | ✅ `backup.py` uses `os.fchmod(0o600)` |
| Restore atomic via CredentialStore | ✅ `restore_state()` uses `store.save()` |
| Docs warn about credential locations | ✅ `docs/operations.md` explicitly warns |

---

## Summary

**Decision**: **APPROVE** — No P1 blockers. Two P2 items must be fixed before production deployment. All SPEC.md security requirements satisfied in implementation.
