---
phase: 03-forgetting-salience-floor-budget-packer-mcp
plan: "00"
subsystem: deps-protocols-test-stubs
tags: [wave-0, tdd-red, deps, protocols, hypothesis, fastmcp, tiktoken, vault]
dependency_graph:
  requires: []
  provides:
    - fastmcp>=3.4.2,<4 runtime dep
    - tiktoken>=0.13 runtime dep
    - hypothesis>=6.155 dev dep
    - VaultStore Protocol (6th adapter axis)
    - src/mnema/mcp/__init__.py package
    - src/mnema/adapters/vault/__init__.py package
    - tests/test_forgetting.py RED stubs (FORG-02/03/04)
    - tests/test_recall_packer.py RED stubs (RECALL-03/04/05)
    - tests/test_vault.py RED stubs (CONS-09/TIER-03)
    - tests/test_mcp_server.py RED stubs (IFACE-02)
  affects:
    - pyproject.toml (dep additions)
    - uv.lock (92 packages resolved)
tech_stack:
  added:
    - fastmcp 3.4.2 (MCP server framework)
    - tiktoken 0.13.0 (token counting, cp312-win_amd64 wheel)
    - hypothesis 6.155.2 (property-based testing dev dep)
  patterns:
    - VaultStore Protocol mirrors scheduler.py shape (async, no @runtime_checkable, TYPE_CHECKING guard)
    - Hypothesis property test with sync asyncio.run() wrapper (established test_decay.py pattern)
    - Deferred imports inside test bodies for RED state collection
key_files:
  created:
    - pyproject.toml (modified — fastmcp, tiktoken, hypothesis added)
    - uv.lock (92 packages)
    - src/mnema/ports/vault.py
    - src/mnema/mcp/__init__.py
    - src/mnema/adapters/vault/__init__.py
    - tests/test_forgetting.py
    - tests/test_recall_packer.py
    - tests/test_vault.py
    - tests/test_mcp_server.py
  modified: []
decisions:
  - "KEEP_THRESHOLD defined locally in test_protected_records_never_evicted for Wave 0 (0.3); moves to engine.py in Plan 03-01"
  - "Hypothesis test verifies decay_pass structural guarantee — PASSES in Wave 0"
  - "TestEviction integration stubs use bare assert False (not xfail) — they execute until engine.evict() is available"
  - "MCP test fixture fails at execution (ERROR) not collection — correct RED state per plan spec"
metrics:
  duration_minutes: 45
  completed_date: "2026-06-14"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 9
---

# Phase 03 Plan 00: Wave 0 — Deps, VaultStore Protocol, RED Test Stubs Summary

**One-liner:** fastmcp 3.4.2 + tiktoken 0.13 + hypothesis 6.155 added as deps; VaultStore Protocol (6th adapter axis) created; 4 RED test stub files cover all 9 Phase 3 requirements with Hypothesis FORG-03 invariant test passing.

## What Was Built

### Task 1: Phase 3 deps + package inits (commit `f7510f9`)

Added to `pyproject.toml`:
- `fastmcp>=3.4.2,<4` in `[project.dependencies]` (runtime — MCP server)
- `tiktoken>=0.13` in `[project.dependencies]` (runtime — TiktokenCounter token packer)
- `hypothesis>=6.155` in `[project.optional-dependencies].dev` (property-based test)

Created empty package inits:
- `src/mnema/mcp/__init__.py` — "MNEMA MCP server surface."
- `src/mnema/adapters/vault/__init__.py` — "MNEMA vault adapter implementations."

`uv lock` resolved 92 packages (up from 22) including fastmcp 3.4.2, tiktoken 0.13.0, hypothesis 6.155.2, mcp 1.27.2, and all transitive deps. `uv sync --extra dev` installed all 90 packages into the worktree venv.

### Task 2: VaultStore Protocol (commit `d88f972`)

Created `src/mnema/ports/vault.py` — the 6th adapter axis (D3-09, TIER-03):

```python
class VaultStore(Protocol):
    async def promote(self, record: "MemoryRecord") -> None: ...
    async def get_user_model(self, user_id: str) -> str: ...
```

Follows `scheduler.py` Protocol shape exactly: no `@runtime_checkable`, async methods per D-11, `MemoryRecord` under `TYPE_CHECKING` guard (not at runtime). Static checking only per D-10.

### Task 3: Four RED test stub files (commit `ae48662`)

All four files collect cleanly (`pytest --collect-only` exits 0 with 51 tests). Existing 33 Phase 1+2 tests remain GREEN.

**tests/test_forgetting.py** (FORG-02/03/04):
- `test_protected_records_never_evicted` — Hypothesis `@given`/`@settings(max_examples=100)` property test, sync with `asyncio.run()` wrapper. **PASSES in Wave 0** because it tests the structural guarantee of existing `decay_pass`. `KEEP_THRESHOLD` defined locally (0.3) for Wave 0; moves to `engine.py` in Plan 03-01.
- `TestEviction` class: `test_eviction_sets_valid_until`, `test_eviction_archives_to_cold_store`, `test_eviction_audit_jsonl`, `test_eviction_skips_protected` — assert False stubs.
- `test_eviction_removes_from_vector_index` — standalone async stub verifying ghost-record prevention.

**tests/test_recall_packer.py** (RECALL-03/04/05):
- `TestReRank.test_rerank_order_by_composite_score` — verifies re_rank() composite scoring order.
- `TestPacker.test_pack_under_budget`, `test_pack_respects_budget_limit` — budget boundary tests.
- `test_critical_fact_survives_large_off_topic_history` — adversarial two-pass packer test (100 filler records vs. protected allergy fact).

**tests/test_vault.py** (CONS-09/TIER-03):
- `TestLocalFSVault`: `test_promote_writes_markdown`, `test_promote_deduplication`, `test_promote_sectioned_by_type`.
- `test_vault_promotion_before_eviction` — ordering test (vault before eviction — RESEARCH.md Pitfall 8).
- `test_consolidate_user_isolation` — isolation: consolidate(u1) must not touch u2.
- `test_promotion_on_consolidation` — integration CONS-09 test.
- `engine_with_vault` fixture stub (yields None in Wave 0, replaced in Plan 03-03).

**tests/test_mcp_server.py** (IFACE-02):
- `test_mcp_tools_list` — checks all 5 verbs exposed.
- `test_mcp_remember_recall_roundtrip` — remember/recall roundtrip via FastMCP in-process Client.
- `mcp_server` fixture wraps `engine` via deferred `create_mcp_server` import.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] KEEP_THRESHOLD not in engine.py for Wave 0 Hypothesis test**
- **Found during:** Task 3 — Hypothesis test failed with `ImportError: cannot import name 'KEEP_THRESHOLD' from mnema.core.engine`
- **Issue:** The plan specified importing `KEEP_THRESHOLD` from `engine.py`, but that constant is part of Plan 03-01's implementation work, not Wave 0.
- **Fix:** Defined `KEEP_THRESHOLD: float = 0.3` locally inside the test body with a comment marking it for relocation to `engine.py` in Plan 03-01. This preserves the test's ability to prove the invariant against existing `decay_pass`.
- **Files modified:** `tests/test_forgetting.py`
- **Commit:** `ae48662`

**2. [Rule 2 - Ruff] Auto-fixed import ordering and unused imports**
- **Found during:** Task 3 post-write lint check
- **Issue:** 15 ruff issues — import ordering (I001), unused imports (F401), unused variables (F841)
- **Fix:** `ruff check --fix` resolved 13 automatically; remaining 2 (unused `old_date`, `record_id`) fixed by replacing stub body with commented pseudocode.
- **Files modified:** all 4 test files + vault.py
- **Commit:** included in `ae48662` (files cleaned before commit)

## Test Results

| Category | Count | Status |
|----------|-------|--------|
| Phase 1+2 existing | 33 | GREEN (passing) |
| Phase 3 Hypothesis (FORG-03) | 1 | GREEN (passing — tests existing decay_pass) |
| Phase 3 RED stubs | 17 | FAILED / ERROR (correct RED state) |
| **Total collected** | **51** | **collect-only exits 0** |

## Key Test Stubs for Subsequent Waves

| Test | File | Required By | Status |
|------|------|-------------|--------|
| `test_eviction_removes_from_vector_index` | test_forgetting.py | Plan 03-01 | RED stub |
| `test_vault_promotion_before_eviction` | test_vault.py | Plan 03-03 | RED stub |
| `test_consolidate_user_isolation` | test_vault.py | Plan 03-03 | RED stub |
| `test_critical_fact_survives_large_off_topic_history` | test_recall_packer.py | Plan 03-02 | RED stub |

## Known Stubs

All assert False stubs in TestEviction, test_vault.py, test_recall_packer.py, and test_mcp_server.py are intentional RED stubs. They will be resolved by Plans 03-01 (eviction), 03-02 (packer), 03-03 (vault), and 03-04 (MCP server) respectively. The Hypothesis property test is **not** a stub — it passes and proves the FORG-03 invariant.

## Threat Flags

None. This plan adds only dep pins and Protocol definition + test stubs. No new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

- [x] `pyproject.toml` modified with fastmcp, tiktoken, hypothesis — FOUND
- [x] `uv.lock` updated (92 packages) — FOUND
- [x] `src/mnema/ports/vault.py` with VaultStore Protocol — FOUND
- [x] `src/mnema/mcp/__init__.py` — FOUND
- [x] `src/mnema/adapters/vault/__init__.py` — FOUND
- [x] `tests/test_forgetting.py` (6 test functions) — FOUND
- [x] `tests/test_recall_packer.py` (4 test functions) — FOUND
- [x] `tests/test_vault.py` (6 test functions) — FOUND
- [x] `tests/test_mcp_server.py` (2 test functions) — FOUND
- [x] Commit `f7510f9` (deps) — FOUND
- [x] Commit `d88f972` (VaultStore) — FOUND
- [x] Commit `ae48662` (RED test stubs) — FOUND
- [x] `pytest --collect-only` exits 0 with 51 tests — VERIFIED
- [x] Phase 1+2 33 tests GREEN — VERIFIED
- [x] `test_protected_records_never_evicted` PASSES — VERIFIED
- [x] `test_eviction_removes_from_vector_index` collected — VERIFIED
- [x] `test_vault_promotion_before_eviction` collected — VERIFIED
