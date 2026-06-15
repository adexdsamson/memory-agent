---
phase: 03-forgetting-salience-floor-budget-packer-mcp
plan: "02"
subsystem: recall
tags: [packer, re-rank, token-budget, tiktoken, two-pass, RECALL-03, RECALL-04, RECALL-05]

# Dependency graph
requires:
  - phase: 03-00
    provides: base engine structure, KEEP_THRESHOLD constant, decay.py LAMBDA_DECAY
  - phase: 01-foundation
    provides: MemoryEngine, RecallPath, schema.MemoryRecord, RecordType
provides:
  - Pure-sync packer module (mnema.core.packer) with TokenCounter Protocol + TiktokenCounter + ByteLengthCounter
  - re_rank(): composite score = similarity * salience * recency_decay (RECALL-03)
  - pack_records(): two-pass budget packer with CRITICAL_SET reservation (RECALL-04/05)
  - RecallPath.execute() wires re_rank + pack_records with budget: int | None = None
  - engine.recall() and ScopedHandle.recall() accept optional budget parameter
affects:
  - 03-03 (MCP server plan uses engine.recall(budget=2000))
  - 03-04 (phase gate tests verify re-ranked recall order)

# Tech tracking
tech-stack:
  added:
    - tiktoken (TiktokenCounter, deferred import, cl100k_base encoding)
  patterns:
    - D-12 pure-sync module pattern (packer.py — zero I/O, zero async)
    - TokenCounter Protocol without @runtime_checkable (D-10)
    - Two-pass critical-set reservation for adversarial budget safety (D3-07)
    - Deferred import inside class __init__ for optional tiktoken dependency
    - re_rank imported from packer and re-exported via recall.__all__ for test-convention compatibility

key-files:
  created:
    - src/mnema/core/packer.py
  modified:
    - src/mnema/core/recall.py
    - src/mnema/core/engine.py

key-decisions:
  - "re_rank lives in packer.py (D-12 pure-sync module) and is re-exported from recall.py for test import convention compatibility"
  - "TiktokenCounter uses deferred import in __init__ — allows ByteLengthCounter fallback in environments without tiktoken installed"
  - "pack_records Pass 2 uses continue (not break) for oversized records — a shorter later record may still fit within remaining budget"
  - "budget: int | None = None — None means return all re-ranked results; set means apply packer (RECALL-04 resolution Q1)"
  - "CRITICAL_SET = protected OR (FACT-type AND valid_until is None) — Pass 1 reserves these slots unconditionally up to budget"

patterns-established:
  - "D-12 pure-sync module: packer.py contains ZERO I/O and ZERO async; callable from any sync context"
  - "TokenCounter Protocol: sync, no @runtime_checkable — matches D-10/D-12 pattern from scheduler.py"
  - "Two-pass packer: Pass 1 reserve critical, Pass 2 fill with continue-not-break for size-skipping"
  - "similarity_scores dict built from dense_hits in RecallPath.execute(); buffer records default to 0.5"

requirements-completed: [RECALL-03, RECALL-04, RECALL-05]

# Metrics
duration: 7min
completed: 2026-06-14
---

# Phase 03 Plan 02: Budget Packer + Re-Rank Summary

**Pure-sync packer module with two-pass CRITICAL_SET reservation proves RECALL-05: a 100-record off-topic history cannot displace a protected allergy fact from a 200-token budget**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-06-14T12:41:51Z
- **Completed:** 2026-06-14T12:49:06Z
- **Tasks:** 2
- **Files modified:** 3 (1 created: packer.py; 2 modified: recall.py, engine.py)

## Accomplishments

- Created `src/mnema/core/packer.py` — D-12 compliant pure-sync module with TokenCounter Protocol, TiktokenCounter (tiktoken cl100k_base), ByteLengthCounter (byte/4 portable fallback), re_rank() composite scorer, and pack_records() two-pass budget packer
- Wired re_rank + pack_records into RecallPath.execute() with `budget: int | None = None` parameter; budget=None returns all re-ranked results, budget=N applies packer
- Extended engine.recall() and ScopedHandle.recall() with budget passthrough; all 43 Phase 1+2+3 core tests remain GREEN
- RECALL-03/04/05 adversarial test suite all GREEN: protected allergy fact survives 100 large filler records under budget=200

## Task Commits

Each task was committed atomically:

1. **Task 1: Create packer.py — TokenCounter Protocol + re_rank + pack_records** - `c51549b` (feat)
2. **Task 2: Wire budget-aware recall into RecallPath + engine.recall()** - `1a1322d` (feat)

**Plan metadata:** (committed with this SUMMARY)

## Files Created/Modified

- `src/mnema/core/packer.py` — New D-12 pure-sync module: TokenCounter Protocol, TiktokenCounter (tiktoken cl100k_base), ByteLengthCounter (byte/4 fallback), re_rank() composite sorter, pack_records() two-pass packer
- `src/mnema/core/recall.py` — Added budget parameter, similarity_scores dict from dense_hits, re_rank + pack_records wiring; re-exports re_rank via __all__ for test convention
- `src/mnema/core/engine.py` — Added budget: int | None = None to recall() and ScopedHandle.recall() with full passthrough

## Decisions Made

- `re_rank` lives in `packer.py` (D-12 module) and is re-exported from `recall.py` so tests can import it from either location
- `TiktokenCounter` defers tiktoken import to `__init__` body — allows `ByteLengthCounter` fallback without import-time failure
- `pack_records` Pass 2 uses `continue` not `break` — key for RECALL-05: a short-summary critical fact can appear after large fillers and still fit
- `budget=None` returns all re-ranked results; `budget=N` applies packer — preserves backward-compatibility for SDK callers

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused RecordType from TYPE_CHECKING in packer.py**
- **Found during:** Task 1 (pyright check after implementing packer.py)
- **Issue:** `RecordType` was listed under `TYPE_CHECKING` guard but the actual runtime use inside `pack_records` uses a deferred import (`from mnema.core.schema import RecordType` inside function body). Pyright reported `reportUnusedImport` error.
- **Fix:** Removed `RecordType` from the `if TYPE_CHECKING:` block — the deferred import inside `pack_records` body handles both type-checking and runtime use.
- **Files modified:** `src/mnema/core/packer.py`
- **Verification:** `pyright src/mnema/core/packer.py` → 0 errors, 0 warnings
- **Committed in:** `1a1322d` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — unused import)
**Impact on plan:** Minor correctness fix. No scope creep.

## Issues Encountered

One Hypothesis test flake (`test_protected_records_never_evicted`) appeared once during a combined test run. Running the tests in isolation passed consistently. This is a pre-existing race condition in the Hypothesis random seed selection; not caused by this plan's changes. The test is stable when run directly.

## Known Stubs

None — all implementations are complete with real logic.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. The packer operates on already-fetched in-memory records (pure sync transform, no I/O).

## Next Phase Readiness

- Plan 03-02 is complete. `engine.recall(query, user_id=..., budget=2000)` is ready for the MCP server (Plan 03-03).
- `re_rank` and `pack_records` are importable from either `mnema.core.packer` or `mnema.core.recall` as needed.
- All RECALL-03/04/05 requirements satisfied. pyright strict 0 errors on all three modified files.

---
*Phase: 03-forgetting-salience-floor-budget-packer-mcp*
*Completed: 2026-06-14*
