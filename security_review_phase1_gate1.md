# Gate 1 Security Review: Phase 1 (mail CLI + config subcommands)

**Test Baseline**: 246 tests passing

**Verdict: APPROVE with P2 findings**

---

## P1 Blocking Findings: **None**

All SPEC.md security requirements verified:

| # | Requirement | Verified | Location |
|---|-------------|----------|----------|
| 1 | REST binds 127.0.0.1 only | ✅ | `mail_cli.py:_validate_host()` rejects non-loopback |
| 2 | No hard-delete | ✅ | Only trash/cancel operations |
| 3 | Mutation requires `confirm=true` | ✅ | `mail send --confirm`, config mutations validated |
| 4 | Allowlist enforcement | ✅ | Core enforces, mail CLI passes through |
| 5 | Audit sanitization | ✅ | Core `_sanitize_for_audit()` → `[REDACTED]` |
| 6 | Credential 0600/atomic/lock | ✅ | `store.py`: 0600, atomic writes, fcntl lock |
| 7 | OAuth PKCE | ✅ | `oauth.py`: verifier/challenge, random state |
| 8 | Token refresh on 401 | ✅ | Core `_refresh_access_token()` on 401 |
| 9 | Retry: bounded/backoff/Retry-After | ✅ | `_request()` loops, max 3, honors Retry-After |
| 10 | Typed error hierarchy | ✅ | `CoreError`, `SendDenied`, `ReauthNeeded`, etc. |
| 11 | Bodies untrusted | ✅ | No embedded instruction parsing |
| 12 | Fresh IDs | ✅ | Graph move returns new ID |
| 13 | MCP read-only default | ✅ | `mcp.py`: ro default, full mode available |

---

## P2 Findings (Fix Before Production)

### 1. CLI `mcp` help still shows `choices=("ro",)` 
**File**: `mailhub/cli.py` line ~170
**Issue**: `--mode` help says `choices=("ro",)` but full mode is implemented
**Fix**: Update to `choices=("ro", "full")`

### 2. OAuth state uses temp files (not XDG)
**Files**: `cli.py` auth flow
**Issue**: State stored in `/tmp/mailhub_oauth_*.json` - lost on reboot
**Fix**: Use XDG state dir (`~/.local/state/mailhub/oauth_state_*.json`)

---

## P3 Non-Blocking

| Finding | Location |
|---------|----------|
| `asyncio_mode` pytest warning | `pyproject.toml` (cosmetic) |
| `pydantic_settings` forward ref warning | Upstream FastMCP |
| CalDAV/CardDAV adapters read-only | `carddav.py`, `caldav.py`, `tasks_caldav.py` |
| `mail` CLI not in `--help` output | `cli.py` - only `mailhub` command shown |

---

## Summary

**Gate 1: APPROVED** ✅

Phase 1 (mail CLI + config subcommands) meets all SPEC.md security requirements. Two P2 items to fix before production. Ready for **Gate 2** (OAuth wizards).
