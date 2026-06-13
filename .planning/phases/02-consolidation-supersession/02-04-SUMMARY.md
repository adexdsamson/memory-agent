---
phase: 02-consolidation-supersession
plan: "04"
subsystem: core/consolidation + core/engine + core/write_path
tags: [consolidation, pipeline, supersession, entity-resolution, safety-gate, wiring]
dependency_graph:
  requires:
    - 02-02  # decay.py (decay_pass called at end of run())
    - 02-03  # RecordStore Protocol extension (supersede + find_by_t0_ref)
  provides:
    - ConsolidationPipeline (full 7-step offline pipeline)
    - MemoryEngine.consolidate() real implementation
    - user_id propagation through staging queue
  affects:
    - All future plans that call engine.consolidate()
    - Phase 4 LLM adapter (must honour EXTRACT_RECORDS:/JUDGE_CONTRADICTION: sentinels)
tech_stack:
  added: []
  patterns:
    - TYPE_CHECKING-only adapter imports in core (no vendor imports at runtime)
    - Lazy deferred import for StubLLM and ConsolidationPipeline inside engine.__init__
    - Two-branch early return at top of _apply_verdict for CONS-08 gate
    - Protected flag monotonic-upward invariant in provisional reconcile path
key_files:
  created:
    - src/mnema/core/consolidation.py
  modified:
    - src/mnema/core/engine.py
    - src/mnema/core/write_path.py
decisions:
  - "ENTITY_MAX_DISTANCE = sqrt(2 - 2*0.85) ≈ 0.5477 per RESEARCH.md Pitfall 4 (cosine >= 0.85 threshold)"
  - "Lazy deferred import for ConsolidationPipeline inside engine.__init__ avoids circular import risk"
  - "Protected flag treated as monotonic-upward: consolidation can set but never clear (T-02-11)"
  - "decay_pass in run() consumes yielded (record, score) pairs as pass (Phase 3 will act on scores)"
metrics:
  duration: ~25 minutes
  completed: 2026-06-13T16:30:50Z
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 2
requirements_completed: [CONS-01, CONS-02, CONS-03, CONS-04, CONS-05, CONS-06, CONS-07, CONS-08, FORG-01]
---

# Phase 02 Plan 04: ConsolidationPipeline + Engine Wiring Summary

**One-liner:** 7-step offline consolidation pipeline with CONS-08 protected/FACT gate, LLM sentinel protocol, and lazy-defaulted StubLLM wired into MemoryEngine.consolidate().

## What Was Built

### Task 1: ConsolidationPipeline (`src/mnema/core/consolidation.py`)

Implements the full 7-step pipeline from the architecture diagram:

| Step | Action | Key detail |
|------|--------|------------|
| 1 | Drain staging queue | `get_nowait()` loop until `asyncio.QueueEmpty` |
| 2 | LLM extraction | `EXTRACT_RECORDS:` sentinel → `json.loads()` with try/except (T-02-09) |
| 3 | Safety pin pass | `_is_safety_claim()` imported from `write_path` (D-05); overrides LLM salience |
| 4 | Reconcile-by-t0_ref | `find_by_t0_ref()` → upgrade provisional in place; protected flag is monotonic-upward (T-02-11) |
| 5 | Entity resolution | `embed()` + `vector_search(k=5)` narrowed to same `record_type`; threshold `ENTITY_MAX_DISTANCE = 0.5477` |
| 6 | Verdict + CONS-08 gate | `JUDGE_CONTRADICTION:` sentinel; two-branch early return for protected/FACT (T-02-10) |
| 7 | Decay pass | `decay_pass(record_store, uid)` per unique user_id processed (FORG-01) |

**CONS-08 structural gate** — located at the **top** of `_apply_verdict()`:
```python
if existing.protected or existing.record_type == RecordType.FACT:
    # Append contradiction_pending edge; leave record live — NO fallthrough to supersession
    ...
    return
```
There is no code path from `contradict + protected/FACT` to the supersession branch. The protected flag cannot be cleared by consolidation (monotonic-upward invariant across both the reconcile path and verdict path).

**Sentinel constants** (`_EXTRACT_SENTINEL`, `_JUDGE_SENTINEL`) are module-level — the real `QwenLLMProvider` in Phase 4 must use these same strings.

### Task 2: Engine wiring + staging queue user_id

**`write_path.py`** (1-line change): staging queue item now includes `user_id`:
```python
await self._staging_queue.put({"turn": turn, "t0_ref": t0_ref, "user_id": user_id})
```
This propagates the hard isolation boundary into every ConsolidationPipeline T1 operation (D-02/D-03, T-02-13).

**`engine.py`** changes:
- `llm: "LLMProvider | None" = None` added as keyword-only parameter (backward-compatible)
- Lazy-default StubLLM when `llm is None` (deferred import inside `__init__`)
- `ConsolidationPipeline` constructed in `__init__` (also deferred import — peer core module)
- `consolidate()` stub replaced: `await self._consolidation_pipeline.run()` then `await self._scheduler.trigger_now()`

## Verification Results

| Check | Result |
|-------|--------|
| `pyright src/mnema/core/consolidation.py` | 0 errors |
| `pyright src/mnema/core/engine.py src/mnema/core/write_path.py` | 0 errors |
| 23 Phase 1 tests (--ignore=test_consolidation --ignore=test_decay) | 23 passed |
| `from mnema.core.consolidation import ConsolidationPipeline` | OK, 5 methods present |
| MemoryEngine constructed without `llm=` | OK (StubLLM default) |
| staging queue item contains `user_id` key | PASSED (verified by targeted assertion) |

## Commits

| Hash | Message |
|------|---------|
| `4db296e` | feat(02-04): implement ConsolidationPipeline in core/consolidation.py |
| `4a9beb6` | feat(02-04): wire engine.consolidate() to ConsolidationPipeline + user_id in staging queue |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pyright strict reportPrivateUsage on `_is_safety_claim` import**
- **Found during:** Task 1 pyright run
- **Issue:** pyright strict flags cross-module import of underscore-prefixed names
- **Fix:** Added `# pyright: ignore[reportPrivateUsage]` on the import line; import is architecturally required (D2-03 — single canonical safety gate in write_path)
- **Files modified:** `src/mnema/core/consolidation.py`
- **Commit:** `4db296e`

**2. [Rule 1 - Bug] pyright strict reportUnknownVariableType from `json.loads` Any**
- **Found during:** Task 1 pyright run (3 errors initially)
- **Issue:** `json.loads` returns `Any`; pyright strict propagates Unknown through list comprehension
- **Fix:** Replaced list comprehension with explicit `for` loop + `isinstance(item, dict)` guard + `# type: ignore[arg-type]` on append
- **Files modified:** `src/mnema/core/consolidation.py`
- **Commit:** `4db296e`

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced by this plan. The consolidation pipeline operates entirely within the existing T1 SQLite adapter (supersede/find_by_t0_ref from Plan 03) and the existing RecordStore Protocol. No new external surface.

Threat mitigations implemented as specified:
- T-02-09 (LLM JSON injection): `try/except json.JSONDecodeError` with `return`
- T-02-10 (CONS-08 gate): structural two-branch early return at top of `_apply_verdict()`
- T-02-11 (protected monotonic-upward): explicit re-set in provisional reconcile path
- T-02-12 (supersession atomicity): delegated entirely to `SqliteT1.supersede()` (Plan 03)
- T-02-13 (cross-user creation): `user_id` from staging item → every MemoryRecord construction

## Known Stubs

None. The consolidation pipeline is fully wired. StubLLM (already present from Phase 2 wave 1) serves as the real default LLM in all Phase 2 tests; it is replaced by `QwenLLMProvider` in Phase 4 transparently via the `LLMProvider` Protocol.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `src/mnema/core/consolidation.py` | FOUND |
| `src/mnema/core/engine.py` | FOUND |
| `src/mnema/core/write_path.py` | FOUND |
| commit `4db296e` | FOUND |
| commit `4a9beb6` | FOUND |
