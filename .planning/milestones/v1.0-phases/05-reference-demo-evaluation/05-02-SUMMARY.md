---
phase: 05-reference-demo-evaluation
plan: "02"
subsystem: testing
tags: [demo, decay, protected, eviction, budget-packing, expand, tdd, pytest]

# Dependency graph
requires:
  - phase: 05-reference-demo-evaluation
    plan: "01"
    provides: DEMO-01/02/03 GREEN; persistent_engine_factory fixture; coach.py complete
provides:
  - test_decay_protected_and_recovery PASSED (DEMO-04)
  - test_budget_packing_and_expand PASSED (DEMO-05)
  - All 5 demo scenario tests GREEN (5/5)
affects:
  - Phase 5 evaluation gate: 5/5 DEMO scenarios proven GREEN
  - Core Value Pillar 3: protected facts provably survive every decay pass (keep_score math verified)
  - Core Value Pillar 4: recall fits within token budget; critical facts always surfaced

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "xfail removal: converting XPASS stubs to GREEN by removing @pytest.mark.xfail"
    - "backdating pattern: t1.update(id, created_at=past, last_accessed=past, salience=0.2)"
    - "keep_score proof comment: keep_score(60d,sal=0.2,acc=0)=0.08 < KEEP_THRESHOLD=0.3"
    - "two-pass packer assertion: non_protected_tokens <= budget (protected overflow by design)"
    - "ruff E501 fix: parenthesized assertion messages for lines > 100 chars"

key-files:
  created: []
  modified:
    - tests/test_demo_coach.py

key-decisions:
  - "Wave 1 stubs were already fully implemented (XPASS) — Task 1/2 only removed xfail markers and strengthened assertions per plan spec"
  - "DEMO-04 assertion: evicted_count >= 1, peanut in allergy recall, kale absent from live, expand() returns Turn with kale"
  - "DEMO-05 assertion: non_protected_tokens <= 300 (not total_tokens — protected overflow by design per packer.py), expand() on allergy returns peanut"
  - "Ruff E501 fixes added as separate style commit rather than squashing into feat commits"

# Metrics
duration: 12min
completed: 2026-06-15
---

# Phase 05 Plan 02: DEMO-04/05 GREEN Summary

**Remove xfail markers from DEMO-04 (decay+protected+recovery) and DEMO-05 (budget packing+expand); strengthen assertions per plan spec; fix ruff line-length violations**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-15
- **Completed:** 2026-06-15
- **Tasks:** 3
- **Files modified:** 1 (tests/test_demo_coach.py)

## Accomplishments

- **DEMO-04 GREEN:** `test_decay_protected_and_recovery` — removed `@pytest.mark.xfail`; added
  inline proof comment "keep_score(60d,sal=0.2,acc=0) = 0.08 < KEEP_THRESHOLD=0.3 -> evicted;
  protected allergy skipped before score math (decay_pass structural guarantee, FORG-03)";
  added assertion messages for all five checks (evicted_count, allergy survival, kale eviction,
  expand() not None, "kale" in turn.content)

- **DEMO-05 GREEN:** `test_budget_packing_and_expand` — removed `@pytest.mark.xfail`; added
  inline proof comment for two-pass packer (RECALL-05); strengthened from "first result with ref"
  pattern to explicitly calling expand() on `protected_results[0]` and asserting "peanut" in
  turn.content; added `assert any("peanut" in r.content for r in protected_results)` check

- **Full suite:** 5/5 DEMO tests PASSED; 123 passed / 71 skipped / 1 xfailed in full suite;
  pyright 0 errors; ruff clean

## Task Commits

1. **Task 1: GREEN test_decay_protected_and_recovery (DEMO-04)** — `15011c4`
2. **Task 2: GREEN test_budget_packing_and_expand (DEMO-05)** — `b901ee9`
3. **Task 3: Ruff E501 style fixes** — `ae7056b`

## Verification Gate

```
pytest tests/test_demo_coach.py -v
```
Result: **5 passed** (0 xfail, 0 xpass, 0 failed)

```
pytest tests/ -q -x
```
Result: **123 passed, 71 skipped, 1 xfailed** (no failures)

```
pyright src/mnema/
```
Result: **0 errors, 0 warnings, 0 informations**

```
ruff check src/ tests/
```
Result: **All checks passed**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing] Ruff E501 line-length violations introduced by assertion messages**
- **Found during:** Task 3 (regression check)
- **Issue:** New assertion messages in Tasks 1 and 2 exceeded the 100-char ruff limit (E501)
- **Fix:** Wrapped long assertion messages with parenthesized continuation; wrapped long
  `sum()` expression over `non_protected_results`
- **Files modified:** tests/test_demo_coach.py
- **Commit:** ae7056b

## Known Stubs

None — all five DEMO tests are now fully implemented and passing. No placeholder text or
hardcoded empty values in modified files.

## Threat Flags

No new security-relevant surface introduced. This plan only modifies test assertions.

## Self-Check

- tests/test_demo_coach.py: FOUND (modified)
- Commit 15011c4: FOUND
- Commit b901ee9: FOUND
- Commit ae7056b: FOUND
- 5 PASSED gate: CONFIRMED (pytest output above)

## Self-Check: PASSED
