# Mailhub Roadmap

## Current status

Mailhub's core mail, calendar, contacts, tasks, REST, CLI, and MCP capabilities are implemented. The latest Git tag is `v0.1.21`; this checkout is being prepared as a `0.1.22` release candidate.

The candidate includes 66 additional tests for the REST API and IMAP adapter, IMAP flag parsing and warning fixes, security updates to MCP and pytest, and a locked dependency audit in CI. The local release checks pass; the remaining step is review and release publication.

## Next release

Complete release review for `0.1.22`:

1. ✅ Full suite: 333 passed; Ruff lint and format checks pass.
2. ✅ Bandit: no medium/high findings. `uv audit`: no known vulnerabilities in 50 locked packages.
3. ✅ Changelog, package/API/lockfile versions, and man page metadata set to `0.1.22`.
4. ✅ Rebuilt and inspected the wheel and source distribution.
5. ☐ Create and push the release tag after review; the publish workflow is configured to run on tags.

## Optional backlog

These are candidate projects, not release blockers. Prioritize them when there's a concrete user need.

| Item | Status | Notes |
|---|---|---|
| Homebrew tap | Not started | Optional distribution channel |
| Arch/AUR package | Not started | Optional distribution channel |
| CalDAV/CardDAV write support | Not started | Calendar and contact adapters are currently read-only |
| Streamable HTTP MCP transport | Not started | Consider if clients need remote or web-based MCP access |

## Completed capabilities

- Mail providers: Gmail, Microsoft Graph, and IMAP/SMTP
- Calendar providers: Google Calendar, Microsoft Graph, and CalDAV
- Contacts providers: Google People, Microsoft Graph, and CardDAV
- Task providers: Microsoft To Do via Graph and CalDAV VTODO
- Local REST API, `mailhub` administration CLI, and `mail` client CLI
- Read-only and full-mode stdio MCP server
- OAuth setup flows, shell completions, man pages, Docker packaging, and operations documentation
- Automated package publishing workflow
