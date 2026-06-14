---
phase: 03-forgetting-salience-floor-budget-packer-mcp
plan: "04"
subsystem: mcp-server
tags: [mcp, fastmcp, iface-02, d3-13, d3-14, d3-15, d3-16, phase-gate]
dependency_graph:
  requires: [03-01, 03-02, 03-03]
  provides: [create_mcp_server, MCP-tool-surface, IFACE-02]
  affects: [src/mnema/mcp/server.py, tests/test_mcp_server.py]
tech_stack:
  added: []
  patterns: [closure-capture-injection, fastmcp-in-process-client, pyright-ignore-decorator-false-positive]
key_files:
  created:
    - src/mnema/mcp/server.py
  modified:
    - tests/test_mcp_server.py
    - tests/test_recall_packer.py
    - tests/test_vault.py
decisions:
  - API probe before assertions confirmed FastMCP 3.4.2 CallToolResult.data is the canonical Python return value (not .content) — both attributes exist but .data is the clean path
  - pyright strict reportUnusedFunction false positive on @mcp.tool inner functions suppressed with inline pyright ignore on each async def line — functions ARE used via decorator registration
  - Ruff I001 import-sort pre-existing issues in wave-2 test files fixed as part of phase gate (auto-fix only, no logic changes)
metrics:
  duration: 15 minutes
  completed: 2026-06-14
  tasks_completed: 2
  files_modified: 3
  files_created: 1
---

# Phase 03 Plan 04: FastMCP MCP server wrapper + Phase 3 phase gate Summary

**One-liner:** FastMCP 3.4.2 MCP server exposing five engine verbs via closure-captured injection, with explicit user_id isolation on every tool (D3-14), confirmed via in-process client tests and full phase gate (54 tests, pyright 0 errors, ruff clean).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement create_mcp_server factory + five tools | e15e3a2 | src/mnema/mcp/server.py (created) |
| 2 | MCP tests GREEN + Phase 3 full suite phase gate | b6ea5d2 | tests/test_mcp_server.py (updated) |
| fix | Phase gate: pyright + ruff clean | 80cb82b | server.py, test_recall_packer.py, test_vault.py |

## Key Deliverables

### src/mnema/mcp/server.py

`create_mcp_server(engine: MemoryEngine) -> FastMCP` factory function:
- Creates `FastMCP("mnema")` instance
- Registers 5 tools as inner async functions closed over the injected engine (D3-13 closure capture)
- Every tool has `user_id: str` as an explicit, required, non-defaulted argument (D3-14)
- `consolidate` tool passes `user_id` to `engine.consolidate(user_id=user_id)` — D3-14 isolation real, not deceptive (T-03-04-06)
- `__main__` entry point for stdio smoke-testing (D3-15)

### tests/test_mcp_server.py

Five tests covering IFACE-02:
1. `test_mcp_tools_list` — verifies exactly {remember, recall, forget, consolidate, expand} exposed
2. `test_mcp_remember_recall_roundtrip` — peanut allergy stored + retrieved via MCP surface
3. `test_mcp_forget_protected_raises` — forget scope checks surfaced through MCP layer
4. `test_mcp_expand_returns_none_for_wrong_user` — T-03-04-01 user isolation proven via expand
5. `test_mcp_consolidate_passes_user_id` — D3-14 consolidation scoping proven (T-03-04-06)

## API Probe Finding (Task 1 — BLOCKER 4 resolution)

FastMCP 3.4.2 `call_tool` returns `CallToolResult` with attributes:
```
content, data, is_error, meta, structured_content
```
`result.data` is the canonical Python return value — str, list[dict], dict, or None.
`result.content` is `list[TextContent]` (serialized form).
All test assertions in this plan use `result.data`.

## Phase Gate Results

| Check | Result |
|-------|--------|
| `pytest tests/ -q` | 54 passed, 0 failed |
| `pyright` | 0 errors, 0 warnings |
| `ruff check src/ tests/` | All checks passed |
| MCP tool listing | {remember, recall, forget, consolidate, expand} confirmed |
| remember→recall roundtrip | peanut allergy retrievable via MCP surface |
| expand wrong user_id | Returns None (scope check proven) |
| consolidate user_id | Passes through to engine.consolidate(user_id=...) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pyright strict reportUnusedFunction false positive on @mcp.tool inner functions**
- **Found during:** Task 1 verify (pyright run)
- **Issue:** Pyright strict mode reports `reportUnusedFunction` for the 5 inner async functions in `create_mcp_server`. They ARE accessed — the `@mcp.tool` decorator registers them — but pyright's static analysis does not see decorator registration as "access".
- **Fix:** Added `# pyright: ignore[reportUnusedFunction]` on each `async def` line (not the decorator line — pyright associates the error with the def statement)
- **Files modified:** `src/mnema/mcp/server.py`
- **Commit:** 80cb82b

**2. [Rule 1 - Bug] Pre-existing ruff I001 import-sort issues in wave-2 test files**
- **Found during:** Phase gate ruff check
- **Issue:** `tests/test_recall_packer.py` and `tests/test_vault.py` had 7 `I001` import-sort violations from earlier waves — not in my files but blocking the phase gate
- **Fix:** `ruff check --fix` applied (pure formatting, no logic changes)
- **Files modified:** `tests/test_recall_packer.py`, `tests/test_vault.py`
- **Commit:** 80cb82b

## Threat Surface Scan

No new network endpoints, auth paths, or trust boundary changes introduced.
- `src/mnema/mcp/server.py` is a stdio-local MCP server (no network surface in MVP)
- user_id isolation: all 5 tools require explicit `user_id` arg (D3-14)
- Pre-existing threat model in PLAN.md covers T-03-04-01 through T-03-04-06 — all mitigations implemented

## Known Stubs

None. The MCP server is a complete thin wrapper with no placeholder code. All five tools delegate to the engine and return real data.

## Self-Check: PASSED

- `src/mnema/mcp/server.py` exists: FOUND
- `tests/test_mcp_server.py` updated: FOUND
- Commit e15e3a2 exists: FOUND
- Commit b6ea5d2 exists: FOUND
- Commit 80cb82b exists: FOUND
- 54 tests passing: CONFIRMED
- Pyright 0 errors: CONFIRMED
- Ruff clean: CONFIRMED
