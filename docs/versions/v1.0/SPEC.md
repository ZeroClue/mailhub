Short answer: in this conversation I have no shell, filesystem, or tool access — there's no agent mode for me to switch into here. The agent that *can* execute is already on your machine (opencode/pi.dev). And for this specific project, spec-first is the better path anyway, for three reasons:

1. **The code already exists** — my previous message is a complete reference implementation. A local agent's job is transcription + dependency install + first-run debugging, not design.
2. **The critical path is irreducibly yours** — provider console clicks and OAuth consent screens. No agent should do those for you, and none can.
3. **The residual risk lives in first-run seams** (FastMCP handshake, Graph `$search` quirks, token rotation) that need a live terminal against real APIs — exactly what your local agent has and I don't.

So the right shape is: **spec (arbiter) + reference code (transcription source) → your local agent (build & verify) → you (human-only steps) → me (patch the seams when they fail).** One rule keeps it non-flaky: *where reference code and spec disagree, the spec wins* — that prevents drift when the agent "improves" something.

Here's the spec, written to be handed to a cold agent.

---

# mailhub — Implementation Spec v1.0

**Environment:** WSL2 distro, Python ≥ 3.11, `uv`. Target users: opencode and pi.dev agents plus the human's shell.

## 0. How to use this document

1. Save the prior assistant message (full code listing) as `~/mailhub/REFERENCE.md`.
2. Save this document as `~/mailhub/SPEC.md`.
3. Kick off the agent with the prompt in §11.
4. The agent transcribes, fixes the defects listed in §8, builds in the order of §7, and stops at every step marked **[HUMAN]** in §6.

## 1. Goal

One local service that gives agents uniform, safe, non-flaky access to all of the user's Gmail and Outlook.com mailboxes through official provider APIs (Gmail API, Microsoft Graph), replacing Thunderbird as the integration point. Three surfaces over one core: REST (127.0.0.1), CLI, stdio MCP.

## 2. Goals

- **G1** — Read, search, draft, send, file, and trash mail across N Gmail + N Outlook.com accounts via one interface with per-account aliases.
- **G2** — Tokens live for months, not days: Google app published to production (no 7-day Testing expiry); weekly keepalive refresh defeats Microsoft's 90-day inactivity lapse.
- **G3** — Safe delegation: read-only credential for agents by default; send gated by dry-run → `confirm:true` **and** a server-side recipient allowlist; all mutations audit-logged.
- **G4** — No hard-delete capability exists anywhere in the stack.
- **G5** — Fail-fast and isolable: one dead account never 500s the others; hub-down produces instant, actionable errors, never hangs.

## 3. Non-goals

- No local mail store, mirror, cache, or background fetch (stateless live proxy — no sync drift).
- No cross-provider search-syntax normalization; provider dialects pass through (examples live in tool descriptions).
- No network exposure: bind 127.0.0.1, always. No Docker (deferred; the design tolerates containerization later).
- No calendar/contacts in v1 (both OAuth apps can gain scopes later without re-architecture).
- No Thunderbird integration (permanently out of scope for v1; user confirmed no TB-local-only data).

## 4. Final decisions (do not re-litigate)

| # | Decision | Rationale |
|---|---|---|
| D1 | Gmail scope = `gmail.modify` | Sensitive, not restricted; everything except hard delete. Supersedes the earlier `mail.google.com` idea. |
| D2 | Google app published to production, unverified | Escapes the 7-day refresh-token death of Testing mode; one "unsafe" click per account at consent. |
| D3 | MSFT: public client, `/consumers` authority, redirect `http://localhost:8788`, no secret | Personal accounts; standard desktop-app flow. |
| D4 | OAuth via paste-back (no local listener) | Windows browser's localhost ≠ WSL's localhost under bridged networking. |
| D5 | Daemon (systemd user service) for REST/CLI; **MCP as separate stdio subprocess** | stdio MCP must not depend on the daemon and avoids FastAPI/FastMCP lifespan gluing. |
| D6 | Tokens: `~/.local/state/mailhub/tokens.json`, 0600, atomic writes, per-account async lock **plus cross-process file lock** | MSFT rotates refresh tokens; races kill accounts. |
| D7 | Two bearer tokens: `ro` (GET), `full` (mutations) | Agents get `ro` unless explicitly promoted. |
| D8 | Send requires `confirm:true`; allowlist enforced in core, not client; blocks audited | The only model-independent prompt-injection control. |
| D9 | Audit = mutations only, JSONL | Reads would bloat and leak subjects to disk. |
| D10 | Message IDs opaque and non-cacheable; `move` returns `new_id` | Graph IDs mutate on move. |
| D11 | `doctor` doubles as keepalive: weekly systemd timer | Pre-warms refreshes; proves D2 via token age. |

## 5. Module contracts

Reference implementation is authoritative for code shape; contracts below are the spec-level guarantees:

- **config.py** — TOML at `~/.config/mailhub/config.toml`; `Account(alias, provider, email, client)`; `init` scaffolds with two random tokens.
- **store.py** — token KV; atomic write (temp + `os.replace`); in-process lock **and `fcntl.flock`** (see §8.2).
- **oauth.py** — URL builders (Google: `access_type=offline, prompt=consent`; MS: `offline_access ...`), exchange/refresh, `ReauthNeeded` on `invalid_grant`, state-parameter check on paste-back.
- **gmail.py / graph.py** — adapters implementing: `folders, search, get, attachment, send, draft, mark, move, trash, profile`. Graph: `$search` requires `ConsistencyLevel: eventual` and cannot combine with `$orderby`. Gmail: search fan-out caps at `limit ≤ 50`, semaphore 8.
- **core.py** — token lifecycle (cache → per-account lock → refresh → persist, re-read inside lock); retry-once on 401 and 429/503 (honoring `Retry-After`, cap 10 s); allowlist (fnmatch, case-insensitive); audit; `doctor`; error taxonomy → HTTP: 409 reauth, 428 missing confirm, 403 allowlist/scope, 404 unknown alias/folder, 502 upstream.
- **app.py** — FastAPI; bearer middleware with `hmac.compare_digest`; `/health` unauthenticated; mutations depend on `full` scope.
- **mcp.py** — FastMCP stdio, 9 tools mirroring core; `instructions` must retain the untrusted-body clause, the no-ID-caching clause, and both search-dialect examples.
- **cli.py** — `mailhub` (init/serve/auth/doctor/mcp) and `mail` (client); hub-unreachable → exit with "start it: systemctl --user start mailhub", never retry-loop.

## 6. Human-only steps (agent must stop and instruct, never attempt)

1. **[HUMAN]** Google Cloud: create project → enable Gmail API → OAuth consent (External) → **Publish to production** → Desktop-app OAuth client → paste id/secret into config.
2. **[HUMAN]** Entra: app registration (personal accounts only) → mobile/desktop platform → `http://localhost:8788` → delegated perms (`offline_access, Mail.ReadWrite, Mail.Send, MailboxSettings.ReadWrite`) → paste client id.
3. **[HUMAN]** Per-account consent: open printed URL in Windows browser → click through "unsafe" warning → copy failed `localhost:8788/...` URL → run `mailhub auth <provider> <alias> --code '<url>'`.
4. **[HUMAN]** Decide account aliases, allowlist entries, and which agents receive `ro` vs `full`.
5. **[HUMAN]** Exclude `~/.config/mailhub/` and `~/.local/state/mailhub/` from all cloud backup/sync.

## 7. Build order & acceptance criteria

**S1 — Read path, one Gmail account.** Transcribe, fix §8 defects, `uv tool install --editable .`, config, auth, doctor.
✅ `mailhub doctor` exits 0 · `curl -s localhost:8787/health` ok · `mail accounts` shows status ok · `mail search me "newer_than:7d"` returns rows · `mail get <id>` prints body · tokens.json mode 0600.

**S2 — Gmail mutations.**
✅ `mail draft me --to ... --subject t --body b` creates a draft visible in Gmail web · `mail send` without `--confirm` → 428-style refusal · with `--confirm` → delivered · recipient failing allowlist → 403 + `send_blocked` audit line · `read`/`move`/`trash` verified in Gmail web UI.

**S3 — Microsoft account.**
✅ `mailhub auth microsoft <alias>` paste-back succeeds · `mail search <alias> "received>=2025-01-01 hasAttachments:true"` returns rows · `mail move <id> archive` returns `new_id`, and re-search finds the message under `new_id` · send delivers with `--confirm`.

**S4 — MCP into both agents.**
✅ `npx @modelcontextprotocol/inspector mailhub mcp` completes initialize + `tools/list` · opencode local MCP wiring: agent answers "how many unread from X this week" via `mail_search` · same via pi.dev · **daemon stopped:** MCP tools still work (stdio independence).

**S5 — Service hardening.**
✅ systemd user units + weekly doctor timer enabled, `loginctl enable-linger` · survives reboot · `kill` daemon mid-session → CLI errors instantly with the start-hint · `--json` flag works in all positions (see §8.1) · after 8+ days, `doctor` shows `token_age_days > 7` on Google accounts with status ok (proves D2 escaped).

## 8. Known defects in the reference implementation — fix during transcription

1. **`cli.py`: `--json` is registered on the root parser after subparsers**, so it only parses *before* the subcommand. Move it onto each subparser (or pre-scan argv).
2. **`store.py` locking is in-process only.** Daemon, stdio MCP, and `doctor` refresh concurrently across processes → MS refresh-token rotation race. Add `fcntl.flock` on a `tokens.lock` file around load/update.
3. **`core.py` doesn't map `LookupError`** (unknown label/folder) → return 404 `NotFound`, not a 500.
4. **`core.py` audit()** uses `__import__("os")` — replace with a plain `import os`.
5. **Pin the `mcp` SDK version** in pyproject; verify the stdio handshake before wiring agents (§ S4).
6. **Documented limitation, not a bug:** Graph reply path (`reply_to`) sends plain-text comment only, no HTML/subject control. Keep; note it in the tool description.

## 9. Risk register — mitigate at the seam, do not redesign

| Risk | Standing mitigation |
|---|---|
| Prompt injection via message bodies | `ro` default; server-side allowlist; untrusted-data clause in MCP instructions. Removing any of these is out of bounds. |
| FastMCP stdio SDK churn | Fix at handshake seam; fallback is `mail` CLI as the agent interface. |
| Graph `$search` semantics | Keep `ConsistencyLevel: eventual`; never combine with `$orderby`. |
| Google tightens unverified-app consent | Fallback ladder: Gmail-via-IMAP app-password adapter behind the same Provider interface. (Outlook has no fallback; Graph is mandatory there.) |
| Token file leak | 0600 + §6.5; never log tokens. |
| Provider 429s | Single retry honoring `Retry-After`, then surface 502. No queues, no background jobs. |

## 10. Artifacts

`~/mailhub/` — `SPEC.md`, `REFERENCE.md`, `pyproject.toml`, `mailhub/` (10 modules), `deploy/` (3 units). State: `~/.config/mailhub/config.toml` (0600), `~/.local/state/mailhub/{tokens.json,audit.log}`.

## 11. Kickoff prompt (paste into opencode)

```text
You are building "mailhub" in ~/mailhub. SPEC.md is the normative design;
REFERENCE.md holds a reference implementation to transcribe and verify.
Where they conflict, SPEC wins. Work strictly in SPEC §7 order (S1→S5),
running each stage's acceptance checks and showing me the output before
advancing. Apply all §8 fixes during transcription. Do not change any §4
decision or §9 mitigation. Steps marked [HUMAN] in §6 are mine — when you
reach one, stop and give me exact click-by-click instructions, then wait.
Env: WSL2, Python 3.11+, uv. Repo deps only: fastapi, uvicorn, httpx, mcp.
```

---

That's the complete handoff package. Run S1 today — it's ~30 minutes of your clicks plus the agent's transcription, and it already gives your agents read access to a real mailbox, which is the earliest point you'll know the OAuth paste-back flow works on your bridged setup. When a stage fails, bring me the verbatim error and I'll patch that seam.