# Mailhub Roadmap - Post M1-M5 Polish

## Overview
Mailhub M1-M5 complete (187 tests). This roadmap covers production hardening & UX improvements.

---

## P0 - Critical UX Gaps (Blocking End-to-End Use)

| ID | Task | Status | Owner | Review | Notes |
|----|------|--------|-------|--------|-------|
| P0-1 | Implement `mail` CLI command (thin REST client) | ✅ | | ☐ | `mail send/search/get/folders` - thin HTTP client to REST API |
| P0-2 | Add `mailhub config` subcommands | ✅ | | ☐ | `add-account`, `list`, `validate`, `doctor`, `setup-google`, `setup-microsoft` |
| P0-3 | Google OAuth setup wizard | ✅ | | ☐ | Opens browser to Google Cloud, guides consent screen, stores client_id/secret |
| P0-4 | Microsoft OAuth setup wizard | ✅ | | ☐ | Opens browser to Entra ID, guides app registration, stores client_id |
| P0-5 | Update README with M1-M5 usage | ✅ | | ☐ | Full feature list, install, config, usage examples for all milestones |

---

## P1 - High Value Polish

| ID | Task | Status | Owner | Review | Notes |
|----|------|--------|-------|--------|-------|
| P1-1 | Fix MCP `--mode full` in CLI help | ✅ | | ☐ | Update choices to `("ro", "full")` |
| P1-2 | Add `.gitignore` | ✅ | | ☐ | Ignore `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.pyc` |
| P1-3 | Fix `asyncio_mode` pytest warning | ✅ | | ☐ | Remove `asyncio_mode = "auto"` from pyproject.toml |
| P1-4 | Add OAuth state persistence (survive restarts) | ✅ | | ☐ | Currently uses temp files - use XDG state dir |

---

## P2 - Developer Experience

| ID | Task | Status | Owner | Review | Notes |
|----|------|--------|-------|--------|-------|
| P2-1 | Shell completions (bash/zsh/fish) | ✅ | | ☐ | `mailhub --generate-completion` |
| P2-2 | Man pages | ✅ | | ☐ | `man mailhub`, `man mail` |
| P2-5 | PyPI publish workflow | ✅ | | ☐ | GitHub Actions: hatch build + publish |

---

## P3 - Nice to Have

| ID | Task | Status | Owner | Review | Notes |
|----|------|--------|-------|--------|-------|
| P3-1 | Docker image | ✅ | | ☐ | Multi-stage, non-root, GHCR, docker-compose |
| P3-2 | Homebrew tap formula | ☐ | | ☐ | Optional |
| P3-3 | Arch/AUR package | ☐ | | ☐ | Optional |
| P3-4 | CalDAV/CardDAV write support | ☐ | | ☐ | Currently read-only stubs |
| P3-5 | SSE/Streamable HTTP transport for MCP | ☐ | | ☐ | For web-based AI clients |

---

## Review Gates (Orchestrator Checkpoints)

| Gate | When | Reviewer | Criteria |
|------|------|----------|----------|
| **Gate 1** | After Phase 1 (mail + config CLI) | Galileo | 187+ tests pass, security review, no P1 findings |
| **Gate 2** | After Phase 2 (OAuth wizards) | Galileo | OAuth flow works, tokens stored securely, no secrets in logs |
| **Gate 3** | After Phase 3 (docs/fixes) | Galileo | README complete, gitignore correct, pytest clean |
| **Gate 4** | After Phase 4 (completions/man) | Galileo | Completions work, man pages render, no P1 findings |
| **Gate 5** | Final (PyPI + validation) | Galileo | 187+ tests, PyPI publish works, security audit clean |

---

## Done (M1-M5)

| Milestone | Tests | Key Deliverables |
|-----------|-------|------------------|
| M1 - Foundation | 15 | config, store, cli, mcp (ro) |
| M2 - Mail | 71 | gmail.py, graph.py, core.py, app.py, cli extensions |
| M3 - Calendar | 114 | gcal.py, gcal_graph.py, caldav.py, calendar.py |
| M4 - Contacts/Tasks | 166 | people.py, people_graph.py, carddav.py, tasks.py, tasks_graph.py, tasks_caldav.py |
| M5 - Operations | 187 | deploy/, backup.py, docs/operations.md |

**Total: 187 tests passing (267 with polish)**

---

## Subagent Strategy

| Task Type | Use Subagent? | Rationale |
|-----------|---------------|-----------|
| New CLI commands (`mail`, `config`) | ✅ Yes | Independent, well-scoped, parallelizable |
| OAuth wizards | ✅ Yes | Independent, browser automation logic |
| README/docs | ❌ No | Quick, iterative, low complexity |
| Gitignore/pytest fixes | ❌ No | Trivial, single file |
| Shell completions | ✅ Yes | Independent, bash/zsh/fish separate |

---

## Execution Order

1. **Phase 1** (Parallel): `mail` CLI + `config` subcommands (2 subagents parallel) → **Gate 1**
2. **Phase 2** (Parallel): Google wizard + Microsoft wizard (2 subagents parallel) → **Gate 2**
3. **Phase 3** (Serial): README, gitignore, pytest fixes → **Gate 3**
4. **Phase 4** (Parallel): Shell completions, man pages (2 subagents) → **Gate 4**
5. **Phase 5**: PyPI workflow, final validation → **Gate 5**

---

## Orchestrator Rules

1. **Spawn → Wait → Review → Gate → Next Phase**
2. **Never skip gates** - independent reviewer must approve
3. **Document all findings** in security_review_*.md
4. **Orchestrator does not implement** - only orchestrates, reviews gates, merges

---

## Current Release: v0.1.2

**Status**: ✅ Released

| Artifact | Version | Location |
|----------|---------|----------|
| PyPI package | 0.1.2 | `pip install zc-mailhub` |
| Docker image | v0.1.2 | `ghcr.io/zeroclue/zc-mailhub:v0.1.2` |
| Git tag | v0.1.2 | https://github.com/ZeroClue/mailhub/releases/tag/v0.1.2 |

**Completed in v0.1.2:**
- Health endpoints (`/health`, `/health/detailed`)
- Graceful shutdown (SIGTERM/SIGINT)
- Docker support (multi-stage, docker-compose, GHCR)
- MCP spec compliance (server info + tools capability)
- Docker non-loopback support (`MAILHUB_ALLOW_NON_LOOPBACK`)
- MCP configuration examples for all major AI clients
- Updated man pages (v0.1.2)
- docs/operations.md with Docker deployment guide
