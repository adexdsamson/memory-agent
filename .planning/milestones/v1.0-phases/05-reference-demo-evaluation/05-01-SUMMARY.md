---
phase: 05-reference-demo-evaluation
plan: "01"
subsystem: testing
tags: [demo, coach, pytest, xfail, cross-session, supersession, sqlite, wal]

# Dependency graph
requires:
  - phase: 05-reference-demo-evaluation
    plan: "00"
    provides: suggest_meal() implementation in coach.py; persistent_engine_factory fixture; SqliteT1.close(); 3 xfail test stubs
provides:
  - test_coach_entrypoint PASSED (DEMO-01)
  - test_cross_session_recall PASSED (DEMO-02)
  - test_supersession_surfaces_fields PASSED (DEMO-03)
affects:
  - Phase 5 evaluation gate: 3/5 DEMO scenarios now proven GREEN
  - 05-02: Wave 2 can proceed with DEMO-04/DEMO-05 and eval baseline

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "xfail removal: converting RED stubs to GREEN by removing @pytest.mark.xfail"
    - "DEMO-03 mechanism proof: _verdict_for_pair sanity assert before engine calls"
    - "DEMO-02 cross-session: consolidate() before close() comment pattern for staging-queue flush"
    - "recall(food preference) exclusion assert on retired records (valid_until filter)"

key-files:
  created: []
  modified:
    - tests/test_demo_coach.py

key-decisions:
  - "Wave 0 coach.py suggest_meal() was already complete — Task 1 only removed xfail marker"
  - "Wave 0 cross-session test body was already complete — Task 2 removed xfail and added inline consolidate() comment"
  - "DEMO-03 added _verdict_for_pair sanity assert + recall exclusion assertion to prove the full supersession mechanism, not just field inspection"
  - "DEMO-03 uses separate session_ids (s1/s2) for the two remember() calls for audit clarity"

# Metrics
duration: 18min
completed: 2026-06-15
---

# Phase 05 Plan 01: DEMO-01/02/03 GREEN Summary

**Remove xfail markers from three RED stubs; prove suggest_meal(), cross-session recall, and supersession mechanism with deterministic assertions**

## Performance

- **Duration:** 18 min
- **Started:** 2026-06-15T10:15:00Z
- **Completed:** 2026-06-15T10:33:00Z
- **Tasks:** 3
- **Files modified:** 1 (tests/test_demo_coach.py)

## Accomplishments

- **DEMO-01:** Removed `@pytest.mark.xfail` from `test_coach_entrypoint`; `suggest_meal()` was already implemented in Wave 0 coach.py; smoke test confirms constraint-respecting string returned; pyright 0 errors
- **DEMO-02:** Removed `@pytest.mark.xfail` from `test_cross_session_recall`; added inline comment "staging queue is in-memory; consolidate() flushes to SQLite before engine close" documenting the critical ordering
- **DEMO-03:** Removed `@pytest.mark.xfail` from `test_supersession_surfaces_fields`; imported `_verdict_for_pair` from `tests.test_consolidation`; added sanity assert before engine calls; added recall exclusion assert proving `valid_until` filter works end-to-end

## Task Commits

1. **Task 1: GREEN test_coach_entrypoint (DEMO-01)** — `2ded92f`
2. **Task 2: GREEN test_cross_session_recall (DEMO-02)** — `a4b493a`
3. **Task 3: GREEN test_supersession_surfaces_fields (DEMO-03)** — `100b9f7`

## Verification Gate

```
pytest tests/test_demo_coach.py::test_coach_entrypoint \
       tests/test_demo_coach.py::test_cross_session_recall \
       tests/test_demo_coach.py::test_supersession_surfaces_fields -v
```
Result: **3 passed** (not xfail/xpass)

```
ruff check src/ tests/
```
Result: **All checks passed**

```
pyright
```
Result: **0 errors, 0 warnings, 0 informations**

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

The coach.py skeleton from Wave 0 already contained a complete `suggest_meal()` implementation (including the `scope.recall(query, budget=300)` call and fallback string). The Wave 0 xfail stubs also contained complete test implementations — only the markers needed removal.

## Known Stubs

None in files modified by this plan. The DEMO-04/DEMO-05 tests and `test_eval_baseline.py` retain their `xfail` markers as intended (Wave 2 scope).

## Threat Flags

No new security-relevant surface introduced. This plan only removes `xfail` markers and adds assertions.

## Self-Check

- tests/test_demo_coach.py: FOUND (modified)
- Commit 2ded92f: FOUND
- Commit a4b493a: FOUND
- Commit 100b9f7: FOUND
- 3 PASSED gate: CONFIRMED (pytest output above)

## Self-Check: PASSED
