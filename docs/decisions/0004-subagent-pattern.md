# 0004: Subagent Pattern for Milestone Delivery

## Pattern

Each milestone uses **two parallel subagents** spawned from the main thread:

| Subagent | Role | Purpose |
|----------|------|---------|
| `mX_engineer` | Implementation | Fix blockers, implement features, run verification |
| `mX_reviewer` | Independent Review | Audit implementation, run tests, security/scope assessment |

`X` = milestone number (1, 2, 3...)

## Spawn Parameters

```json
{
  "agent_path": "/root/mX_engineer",  // or mX_reviewer
  "agent_nickname": "Hegel",          // or "Galileo"
  "depth": 1,
  "fork_context": true
}
```

## M1 Agents (Reconstructed from Session Logs)

### m1_engineer (Hegel)
**Role**: Implementation agent for M1 Foundation

**Behavior observed**:
- Fixed packaging blocker: moved `pytest` from optional extra to `dependency-groups.dev`
- Ran `uv sync --extra dev` and `uv run pytest` to verify
- Verified all 4 acceptance commands: `mailhub init/status/mcp --help`
- Reported exact file changes and test results

**Reconstructed Instructions**:
> You are the M1 implementation engineer. Your task is to resolve any blocking issues in the M1 Foundation milestone and verify the implementation meets acceptance criteria. Run tests, fix packaging/configuration issues, and report exact commands run and files changed. Be concise and precise.

### m1_reviewer (Galileo)
**Role**: Independent review agent for M1 Foundation

**Behavior observed**:
- Ran `uv sync --extra dev` to synchronize environment
- Executed all 4 acceptance checks: `uv run pytest`, `uv run mailhub init/status/mcp --help`
- Produced security/scope assessment
- Identified non-blocking findings (P2/P3): .gitignore, failure-path tests, upstream warning
- **Approved M1**

**Reconstructed Instructions**:
> You are the M1 independent reviewer. Perform a complete audit of the M1 Foundation implementation. Synchronize the environment, run all acceptance checks, assess security/scope compliance, and identify any findings (blocking or non-blocking). Render a clear approve/reject decision with evidence.

## Reuse for Future Milestones

For M2, M3, etc.:
1. Spawn `mX_engineer` and `mX_reviewer` in parallel from main thread
2. Engineer implements the milestone per SPEC.md and REFERENCE.md
3. Reviewer independently verifies against acceptance criteria in `docs/milestones/MX-*.md`
4. Main thread synthesizes results

## Note on Agent Definitions

The actual agent definitions (`/root/m1_engineer`, `/root/m1_reviewer`) are built into the Codex CLI binary and not user-accessible. This document captures their observed behavior for reproducibility. If Codex adds user-defined agent support in the future, these can be migrated to local agent configs.
