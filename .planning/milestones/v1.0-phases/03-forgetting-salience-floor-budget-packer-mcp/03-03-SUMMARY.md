---
phase: 03-forgetting-salience-floor-budget-packer-mcp
plan: "03"
subsystem: vault-consolidation
tags: [vault, consolidation, eviction, tier-03, cons-09, forg-02]
dependency_graph:
  requires: [03-01, 03-02]
  provides: [LocalFSVault, vault-promotion-hook, consolidation-eviction-wiring, engine-consolidate-user-id]
  affects: [src/mnema/core/consolidation.py, src/mnema/core/engine.py, tests/test_vault.py]
tech_stack:
  added: []
  patterns: [two-pass-vault-before-eviction, path-traversal-validation, structural-typing-protocol]
key_files:
  created:
    - src/mnema/adapters/vault/local_fs_vault.py
  modified:
    - src/mnema/core/consolidation.py
    - src/mnema/core/engine.py
    - tests/conftest.py
    - tests/test_vault.py
decisions:
  - LocalFSVault uses str.replace(header+newline, header+newline+bullet, 1) for section insertion — simple, no markdown parser needed (D3-12 MVP)
  - Cast self._record_store to Any for vault loop to avoid pyright Protocol return-type strictness on live_records() — same pattern as decay_pass
  - Dummy staged turn needed to trigger consolidation for a user_id (processed_user_ids only includes users with staged items)
metrics:
  duration: 9 minutes
  completed: 2026-06-14
  tasks_completed: 3
  files_modified: 5
  files_created: 1
---

# Phase 03 Plan 03: LocalFSVault + ConsolidationPipeline vault/eviction wiring Summary

**One-liner:** T2 vault adapter (LocalFSVault) + two-pass vault-before-eviction consolidation wiring with user_id scoping (CONS-09/TIER-03/FORG-02).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement LocalFSVault adapter | f1a85af | src/mnema/adapters/vault/local_fs_vault.py |
| 2a | LocalFSVault conftest fixture | 28cbf75 | tests/conftest.py |
| 2b | Wire vault+eviction into ConsolidationPipeline + engine.consolidate() user_id passthrough | 70c3aa1 | src/mnema/core/consolidation.py, src/mnema/core/engine.py, tests/test_vault.py |

## What Was Built

### LocalFSVault (TIER-03)

`src/mnema/adapters/vault/local_fs_vault.py` — T2 canonical vault adapter satisfying VaultStore Protocol by structural typing (D-08):

- `promote(record)`: validates user_id (T-03-03-01), reads `{base_dir}/{user_id}.md`, deduplicates by summary string (D3-12), inserts bullet under `## {RecordType}s` section header, writes updated content
- `get_user_model(user_id)`: returns markdown content or `""` if no file yet
- `_validate_user_id()`: regex `r"^[A-Za-z0-9_\-]+"` prevents path traversal (mirrors LocalFS._validate_session_id)
- Does NOT inherit from VaultStore (structural typing)

### ConsolidationPipeline vault+eviction wiring (CONS-09/FORG-02)

`src/mnema/core/consolidation.py` changes:

- Added `VAULT_SALIENCE_THRESHOLD = 0.7` and `KEEP_THRESHOLD = 0.3` module-level constants
- `__init__` gains `vault: Any = None` and `t0: Any = None` kwargs
- `run(*, user_id: str | None = None)`: when user_id set, filters staged items to that user
- **TWO SEPARATE LOOPS per uid** (Pitfall 8 ordering invariant):
  - Loop 1 (vault): iterates `live_records(uid)` and promotes qualifying records (non-provisional, salience >= 0.7, valid_until IS None)
  - Loop 2 (eviction): consumes `decay_pass(...)` and runs 4-step eviction for records below KEEP_THRESHOLD

### engine.consolidate() user_id passthrough

`src/mnema/core/engine.py` changes:

- ConsolidationPipeline constructed with `vault=self._vault` and `t0=self._t0`
- `consolidate(*, force=False, user_id: str | None = None)` — passes user_id to pipeline.run()

### Tests

All 6 `tests/test_vault.py` tests GREEN:
- `TestLocalFSVault`: 3 unit tests (write markdown, dedup, sectioned by type)
- `test_vault_promotion_before_eviction`: proves vault-before-eviction ordering (salience=0.72 record is both in vault AND has valid_until set)
- `test_consolidate_user_isolation`: consolidate(user_id="u1") does not touch u2's vault or T1 records
- `test_promotion_on_consolidation`: confirmed high-salience record appears in vault after consolidate()

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_vault.py placeholder fixture and TODO test bodies needed replacement**
- **Found during:** Task 2b implementation
- **Issue:** test_vault.py had a placeholder `engine_with_vault` fixture (yielding None) and three test bodies that just `assert False` with TODO comments
- **Fix:** Replaced placeholder fixture with a real `conftest.py` fixture; implemented full test bodies for the three integration tests with real seeding and assertions
- **Files modified:** tests/test_vault.py, tests/conftest.py
- **Commit:** 28cbf75, 70c3aa1

**2. [Rule 1 - Bug] Pyright strict error on live_records() async iteration**
- **Found during:** Task 2b pyright check
- **Issue:** `async for record in self._record_store.live_records(uid)` triggered 5 pyright errors because RecordStore Protocol declares `live_records` as `async def ... -> AsyncIterator[MemoryRecord]`, which pyright sees as returning `CoroutineType[..., AsyncIterator[...]]` rather than directly iterable
- **Fix:** Cast `self._record_store` to `Any` for the vault loop with explanatory comment — consistent with how `decay_pass` uses `Any` for the same parameter
- **Files modified:** src/mnema/core/consolidation.py
- **Commit:** 70c3aa1

## Verification

```
uv run --extra dev pytest tests/test_vault.py -q → 6 passed
uv run --extra dev pytest tests/ -q → 49 passed, 2 errors (pre-existing: test_mcp_server.py awaiting Plan 03-04)
uv run --extra dev pyright src/ → 0 errors, 0 warnings
```

## Known Stubs

None — all test assertions verify real behavior; no placeholder return values.

## Threat Flags

None — all T-03-03-0x threats from the plan were mitigated:
- T-03-03-01: path traversal prevention implemented via `_validate_user_id()` and tested
- T-03-03-03: vault-before-eviction ordering proven by `test_vault_promotion_before_eviction`
- T-03-03-05: user isolation proven by `test_consolidate_user_isolation`

## Self-Check: PASSED

- `src/mnema/adapters/vault/local_fs_vault.py` — FOUND (created in commit f1a85af)
- `src/mnema/core/consolidation.py` — FOUND (modified, VAULT_SALIENCE_THRESHOLD present)
- `src/mnema/core/engine.py` — FOUND (modified, vault=self._vault in ConsolidationPipeline ctor)
- `tests/conftest.py` — FOUND (engine_with_vault fixture present)
- Commits f1a85af, 28cbf75, 70c3aa1 — all present in git log
