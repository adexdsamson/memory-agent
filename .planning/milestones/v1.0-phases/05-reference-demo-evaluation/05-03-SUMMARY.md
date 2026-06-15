---
phase: "05"
plan: "03"
subsystem: eval
tags: [eval, baseline, containment-scoring, token-budget, EVAL.md]
dependency_graph:
  requires: [05-02, engine-phases-1-4]
  provides: [EVAL-02, EVAL.md]
  affects: [project-root]
tech_stack:
  added: []
  patterns:
    - ProbeResult/EvalResults TypedDicts for pyright-strict dict typing
    - try/finally engine teardown in async eval runner
    - Containment-based deterministic scoring (no LLM grading)
key_files:
  created:
    - src/mnema/eval/baseline.py
    - EVAL.md
  modified:
    - tests/test_eval_baseline.py
    - .planning/phases/05-reference-demo-evaluation/05-VALIDATION.md
decisions:
  - "Used TypedDicts (ProbeResult, EvalResults) instead of dict[str, object] to satisfy pyright strict on all access sites"
  - "Supersession avoidance probe: count occurrences of _DIET_CONTENT in naive vs MNEMA context; naive fails when count > 1 (both original and superseded T0 turn present)"
  - "write_eval_report accepts EvalResults (not dict[str, object]) so callers are type-checked at call sites"
metrics:
  duration: "~20 min"
  completed: "2026-06-15"
  tasks_completed: 3
  files_changed: 4
---

# Phase 05 Plan 03: EVAL-02 Before/After Baseline + EVAL.md Summary

**One-liner:** Containment-based naive-vs-MNEMA eval with 3 deterministic probes; MNEMA 3/3 PASS, Naive 2/3, 38% token reduction; EVAL.md written to project root.

## What Was Built

**src/mnema/eval/baseline.py** — complete implementation replacing Wave 0 stubs:

- `PROBES`: 3 `Probe` instances covering DEMO-04 (protected-fact retention), DEMO-03 (supersession avoidance), DEMO-02 (cross-session recall).
- `_seed_eval_data()`: seeds allergy + diet-preference twice (triggers deterministic supersession via identical content + StubLLM SHA256 contradict verdict).
- `_assemble_naive_context()`: globs `*.jsonl` under `local_fs_path`, excludes `archived.jsonl` and `eviction_audit.jsonl` (T-05-03-01 mitigated).
- `run_eval(data_dir)`: builds `LocalConfig` engine, seeds data, assembles both naive and MNEMA contexts for each probe, measures containment + token counts, returns `EvalResults` TypedDict.
- `write_eval_report(results, output_path)`: writes EVAL.md with results table, token efficiency section, methodology paragraph.
- `ProbeResult` / `EvalResults` TypedDicts: pyright strict compliance (0 errors).

**EVAL.md** — written to project root with real numbers from the eval run.

**tests/test_eval_baseline.py** — xfail removed; full GREEN implementation with 7 assertions.

**05-VALIDATION.md** — `nyquist_compliant: true`; all 6 requirements set to green.

## Headline EVAL Numbers

| Probe | Naive | MNEMA | MNEMA Tokens | Naive Tokens |
|-------|-------|-------|--------------|--------------|
| Protected-fact retention | PASS | PASS | 13 | 21 |
| Superseded-fact avoidance | **FAIL** | PASS | 13 | 21 |
| Cross-session recall | PASS | PASS | 13 | 21 |

- **MNEMA:** 3/3 probes PASS
- **Naive:** 2/3 probes PASS (supersession avoidance FAIL — diet content appears twice in full transcript)
- **Token reduction:** 38.1% (13.0 avg MNEMA vs 21.0 avg naive; budget = 300)

## Phase Gate Results

All checks pass:

- `uv run --extra dev pytest -q`: **124 passed, 71 skipped** (0 failed, 0 xfailed)
- `uv run --extra dev pyright src/mnema/eval/`: **0 errors, 0 warnings**
- `uv run --extra dev ruff check src/mnema/eval/ tests/test_eval_baseline.py`: **All checks passed**
- `EVAL.md` exists at project root with results table and Methodology section
- `05-VALIDATION.md` `nyquist_compliant: true`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TypedDict instead of dict[str, object] for pyright compliance**
- **Found during:** Task 1 (pyright check after writing baseline.py)
- **Issue:** `dict[str, object]` values are untyped — every access site needed `int()`, `float()`, `str()` casts, and pyright reported 23 errors due to the `object` type being unassignable to int/float/str parameters.
- **Fix:** Introduced `ProbeResult` and `EvalResults` TypedDicts; `run_eval()` now returns `EvalResults`; `write_eval_report()` accepts `EvalResults`. All type conversions eliminated; pyright clean.
- **Files modified:** `src/mnema/eval/baseline.py`
- **Commit:** a080a89

**2. [Rule 1 - Bug] Ruff E501 line-length in f-string**
- **Found during:** Task 3 (ruff check)
- **Issue:** Summary line in `write_eval_report()` f-string exceeded 100-char limit.
- **Fix:** Split the line with a backslash continuation inside the f-string.
- **Files modified:** `src/mnema/eval/baseline.py`
- **Commit:** a080a89 (same commit)

## Known Stubs

None — all eval functionality is fully implemented and producing real numbers.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The EVAL.md written to the project root contains only deterministic seeded-data results (no secrets, no credentials). T-05-03-01 (archive/audit exclusion) and T-05-03-04 (engine teardown try/finally) are both implemented.

## Self-Check

- [x] `src/mnema/eval/baseline.py` exists and is implemented
- [x] `EVAL.md` exists at project root
- [x] `tests/test_eval_baseline.py` GREEN (1 passed)
- [x] Full suite 124 passed, 71 skipped (0 failed)
- [x] pyright 0 errors on eval module
- [x] ruff clean on eval module + test
- [x] 05-VALIDATION.md nyquist_compliant: true
- [x] Commit a080a89 exists

## Self-Check: PASSED
