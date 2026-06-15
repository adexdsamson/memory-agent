---
phase: 03-forgetting-salience-floor-budget-packer-mcp
plan: "01"
subsystem: memory-engine
tags: [eviction, decay, sqlite-vec, hypothesis, property-testing, jsonl-audit, forget, engine]

requires:
  - phase: 03-00
    provides: test stubs (FORG-02/03/04), pyproject.toml deps (hypothesis, fastmcp, tiktoken)
  - phase: 02
    provides: decay_pass with structural FORG-03 guarantee, sqlite_t1.delete_vector, engine.forget() stub

provides:
  - engine.forget(): explicit 4-step eviction (set valid_until, delete_vector, archive, append_audit)
  - engine.evict(): batch decay-based eviction pass returning eviction count
  - KEEP_THRESHOLD = 0.3 module constant in engine.py
  - ObjectStorePort.append_audit() Protocol method
  - LocalFS.append_audit() writing eviction_audit.jsonl
  - vault: Any kwarg on MemoryEngine.__init__ (6th adapter axis stub)
  - test_forgetting.py: all 6 tests GREEN (FORG-02/03/04 + ghost-record prevention)

affects:
  - 03-02 (budget packer / re-rank — uses engine.evict() from conftest engine fixture)
  - 03-03 (vault + MCP — uses KEEP_THRESHOLD, engine.forget/evict)
  - phase-04 (cloud path — audit JSONL becomes append-only object store)

tech-stack:
  added: []
  patterns:
    - "4-step eviction: update valid_until → delete_vector → archive → append_audit (no hard-delete)"
    - "KEEP_THRESHOLD as module constant with inline rationale docstring"
    - "Deferred import inside evict()/forget() body for decay_pass and datetime"
    - "Hypothesis sync-wrapper pattern: @given(sync def) with asyncio.run() for FORG-03 invariant"
    - "Ghost-record test: use T1.get() not recall() for pre-eviction precondition check"

key-files:
  created: []
  modified:
    - src/mnema/core/engine.py
    - src/mnema/ports/object_store.py
    - src/mnema/adapters/object_store/local_fs.py
    - tests/test_forgetting.py

key-decisions:
  - "engine.evict() has NO not-protected guard — decay_pass structural guarantee is the proof (FORG-03)"
  - "engine.forget() raises ValueError for cross-user or protected records (explicit forced evict path)"
  - "Pre-eviction precondition check uses T1.get() not recall() to avoid access_count/last_accessed side effects that defeat backdating"
  - "append_audit uses deferred json import inside method body per MNEMA deferred-import convention"

patterns-established:
  - "Ghost-record test pattern: seed evictable record, verify with get() not recall(), evict, assert absent from recall"
  - "4-step eviction sequence is the canonical eviction contract for all future backends"
  - "KEEP_THRESHOLD module constant pattern: type annotation + rationale docstring block"

requirements-completed:
  - FORG-02
  - FORG-03
  - FORG-04

duration: 35min
completed: 2026-06-14
---

# Phase 3 Plan 01: Forget/Evict + Eviction Audit Summary

**engine.forget() + engine.evict() with 4-step eviction sequence (set valid_until, delete_vector, archive, JSONL audit) — KEEP_THRESHOLD=0.3, no hard-delete path, FORG-03 Hypothesis invariant proven**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-06-14T00:00:00Z
- **Completed:** 2026-06-14T00:35:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Implemented the full 4-step eviction sequence used by both explicit forget and batch eviction: set `valid_until`, remove vector from KNN index (ghost-record prevention), archive to cold store, append JSONL audit entry — zero hard-delete paths
- FORG-03 Hypothesis property test passes GREEN: `decay_pass` structural guarantee that protected records are never yielded means the eviction pass has no `not record.protected` guard — the proof lives in the test
- `test_eviction_removes_from_vector_index` GREEN: evicted records absent from subsequent `recall()` results, confirmed by using `T1.get()` rather than `recall()` for the precondition check (avoiding access_count side effects that would defeat backdating)

## Task Commits

1. **Task 1: Add append_audit to ObjectStorePort + LocalFS** - `d28ab3e` (feat)
2. **Task 2: Implement engine.forget() + engine.evict() with KEEP_THRESHOLD** - `5c2f903` (feat)

## Files Created/Modified

- `src/mnema/core/engine.py` — `KEEP_THRESHOLD=0.3` constant; `forget()` filled (4-step + scope/protected checks); `evict()` added (batch decay pass); `vault=None` kwarg added to `__init__`
- `src/mnema/ports/object_store.py` — `append_audit(entry: dict[str, Any]) -> None` added to `ObjectStorePort` Protocol
- `src/mnema/adapters/object_store/local_fs.py` — `append_audit()` writes JSONL to `eviction_audit.jsonl`
- `tests/test_forgetting.py` — all 6 test stubs implemented and GREEN

## Decisions Made

- `engine.evict()` has NO `not record.protected` guard by design (FORG-03): `decay_pass` structurally never yields protected records; the code comment and Hypothesis test are the proof. Adding a guard would create false defense-in-depth that could be silently removed in refactors.
- `engine.forget()` raises `ValueError` on protected records and cross-user scope (tighter than `expand()` which returns `None`): explicit forget is an intentional action, not a query, so a silent no-op would mask programming errors.
- Pre-eviction precondition check in `test_eviction_removes_from_vector_index` uses `engine._t1.get()` not `engine.recall()`: `recall()` increments `access_count` and updates `last_accessed` to now, which resets the backdated timestamps that make the record evictable, causing `evict()` to return 0.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ghost-record test precondition defeating its own backdating**
- **Found during:** Task 2 (test_eviction_removes_from_vector_index verification)
- **Issue:** Original test design used `recall()` to verify the record was retrievable before eviction. `recall()` calls `RecallPath.execute()` which increments `access_count` and sets `last_accessed = now`. This reset the 180-day-old backdated timestamps, making `keep_score` exceed `KEEP_THRESHOLD`, so `evict()` returned 0.
- **Fix:** Changed precondition check from `engine.recall(...)` to `engine._t1.get(record_id)`, which reads the record without modifying any access signals. This preserves the backdated state so eviction fires correctly.
- **Files modified:** `tests/test_forgetting.py`
- **Verification:** `test_eviction_removes_from_vector_index` now passes (count >= 1, record absent from post-eviction recall)
- **Committed in:** `5c2f903` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — Bug)
**Impact on plan:** Essential for test correctness; the test itself was correct in intent but the implementation of the precondition check had a subtle side-effect. No scope creep.

## Issues Encountered

None beyond the deviation documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- FORG-02/03/04 fully implemented and verified; 33 Phase 1+2 tests still green; 6 forgetting tests green
- Plan 03-02 (budget packer + re-rank) can proceed: `engine.recall()` awaits the `budget` parameter and `RecallPath` integration
- Plan 03-03 (vault + MCP) can proceed: `vault=None` kwarg is wired on `MemoryEngine.__init__`; `engine.forget/evict()` are fully implemented for MCP tool delegation

---
*Phase: 03-forgetting-salience-floor-budget-packer-mcp*
*Completed: 2026-06-14*

## Self-Check: PASSED

All files found and all commits verified:
- `src/mnema/core/engine.py` — FOUND
- `src/mnema/ports/object_store.py` — FOUND
- `src/mnema/adapters/object_store/local_fs.py` — FOUND
- `tests/test_forgetting.py` — FOUND
- `.planning/phases/03-forgetting-salience-floor-budget-packer-mcp/03-01-SUMMARY.md` — FOUND
- Commit `d28ab3e` — FOUND
- Commit `5c2f903` — FOUND
