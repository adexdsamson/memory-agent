---
phase: 05-reference-demo-evaluation
reviewed: 2026-06-15T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - src/mnema/demo/coach.py
  - src/mnema/eval/baseline.py
  - tests/test_demo_coach.py
  - tests/test_eval_baseline.py
findings:
  critical: 2
  warning: 3
  info: 3
  total: 8
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-06-15
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Phase 5 delivers the nutrition-coach demo (`coach.py`), the before/after evaluation
harness (`baseline.py`), and five scenario tests plus the eval baseline test.

The overall architecture is sound: both files consume the engine strictly via the SDK
(`build_engine` + `scope.remember/recall/expand`), no internals are accessed to fake the
guarantees, and the determinism story (StubLLM + StubEmbedder) is correctly exploited.
The eval's supersession logic — `_DIET_CONTENT` with pre-verified `sha256 % 3 == 2` →
`contradict`, naive full-transcript duplicates, MNEMA live-record filter deduplicates —
was traced through end-to-end and is honest: neither side is rigged.

Two blockers were found: a resource-safety gap in the `run_session` finally block (coach.py)
and `run_eval` using a private `engine._t1._db.close()` call that bypasses the WAL
checkpoint that `SqliteT1.close()` guarantees. Three warnings concern test assertion
strength, test-imposed filesystem side-effects, and silent swallowing of teardown errors.

---

## Critical Issues

### CR-01: `run_eval` bypasses WAL checkpoint via private `_db.close()`

**File:** `src/mnema/eval/baseline.py:309`
**Issue:** Teardown calls `engine._t1._db.close()` directly on the raw `aiosqlite`
connection, bypassing `SqliteT1.close()`. The public close method runs
`PRAGMA wal_checkpoint(FULL)` before disconnecting; skipping it means in-flight
WAL pages are not merged into the main database file before the connection is torn
down. In the eval's single-session scenario aiosqlite cleans up on GC, so no data
is visibly lost today — but it is incorrect by construction, leaks the WAL journal
file, and contradicts the pattern established by `coach.py` (which correctly calls
`engine.t1.close()`). The public API (`engine.t1`) already exposes the safe close
path; there is no reason to reach through to `_db`.

**Fix:**
```python
# Replace (baseline.py lines 306-315):
finally:
    try:
        await engine._t1._db.close()        # WRONG: bypasses WAL checkpoint
    except Exception:
        pass
    try:
        await engine._scheduler.shutdown()  # type: ignore[attr-defined]
    except Exception:
        pass

# With:
finally:
    try:
        await engine.t1.close()             # public API: runs wal_checkpoint(FULL) + close
    except Exception:
        pass
    try:
        await engine._scheduler.shutdown()  # type: ignore[attr-defined]
    except Exception:
        pass
```

---

### CR-02: `run_session` finally block leaks resources on consolidation failure

**File:** `src/mnema/demo/coach.py:104-108`
**Issue:** The finally block executes three statements sequentially — `consolidate()`,
`t1.close()`, `_scheduler.shutdown()` — with no exception isolation between them. If
`engine.consolidate()` raises (e.g., SQLite corruption, a `RuntimeError` from the
pipeline), Python propagates that exception and the remaining finally statements
(`t1.close()` and `_scheduler.shutdown()`) are **not called**. The aiosqlite
connection remains open and the scheduler continues running in the background, leaking
OS handles and APScheduler threads for the lifetime of the process.

**Fix:**
```python
# Replace (coach.py lines 104-108):
finally:
    await engine.consolidate()
    await engine.t1.close()
    await engine._scheduler.shutdown()  # type: ignore[union-attr]
    print("Session saved. Goodbye.")

# With:
finally:
    try:
        await engine.consolidate()
    except Exception as exc:
        print(f"Warning: consolidation failed on exit: {exc}")
    try:
        await engine.t1.close()
    except Exception:
        pass
    try:
        await engine._scheduler.shutdown()  # type: ignore[union-attr]
    except Exception:
        pass
    print("Session saved. Goodbye.")
```

---

## Warnings

### WR-01: `test_eval_baseline` writes `EVAL.md` to the project root as an unconditional test side-effect

**File:** `tests/test_eval_baseline.py:85-87`
**Issue:** The test resolves the project root via `Path(__file__).parent.parent / "EVAL.md"`
and writes a generated report there every time the test runs. This has three problems:

1. It mutates the checked-in project tree from within a pytest run — any CI environment
   with a read-only filesystem or an artifact-clean step will see an unexpected write or
   a `PermissionError` that surfaces as a confusing test failure rather than a clean
   assertion error.
2. A stale `EVAL.md` from a previous successful run persists if the test is later
   skipped or if the suite is run with `-k` excluding this test — reviewers may read
   outdated numbers.
3. The project-root write is non-idiomatic: test output belongs in `tmp_path` (already
   used for the primary validation at line 75-82). The deliverable write should be a
   separate, explicitly-gated step (e.g., a `pytest --generate-eval-report` flag or a
   standalone script).

**Fix:**
```python
# Keep the tmp_path validation (lines 75-82) as-is.
# Replace the deliverable write (lines 84-87) with a clearly conditional write
# so the test is deterministic regardless of working-directory permissions:

# --- Deliverable: write EVAL.md to the project root only when explicitly requested ---
project_root_eval = Path(__file__).parent.parent / "EVAL.md"
if os.environ.get("MNEMA_WRITE_EVAL_REPORT"):
    await write_eval_report(results, project_root_eval)
    assert project_root_eval.exists(), "EVAL.md was not written to project root"
```

---

### WR-02: `test_eval_baseline` allows naive to fail any number of probes, hiding regressions

**File:** `tests/test_eval_baseline.py:60-65`
**Issue:** The assertion `results["probes_passed_naive"] <= 2` passes if naive fails
0, 1, 2, or 3 probes. The test's stated intent is that naive fails **exactly** the
supersession probe and passes the protection and cross-session probes. The current
assertion does not catch a regression where naive also incorrectly fails the peanut
protection or cross-session recall probes (e.g., if `_assemble_naive_context` is broken
and returns an empty string). If `probes_passed_naive == 0`, the test still passes —
which would give a false impression that MNEMA is demonstrably better than naive when
in fact naive is just completely broken.

**Fix:**
```python
# Replace:
assert results["probes_passed_naive"] <= 2, (
    f"Naive baseline must fail the supersession avoidance probe ..."
)

# With (naive must pass exactly 2 probes — protection + cross-session — and fail supersession):
assert results["probes_passed_naive"] == 2, (
    f"Naive baseline must pass 2 probes (protection + cross-session) and fail 1 "
    f"(supersession avoidance). Got {results['probes_passed_naive']} probes passed. "
    f"Per-probe breakdown: {results['probe_results']}"
)
```

---

### WR-03: `test_coach_entrypoint` assertions are trivially satisfied by a broken recall path

**File:** `tests/test_demo_coach.py:83-85`
**Issue:** The two assertions — `isinstance(result, str)` and `len(result) > 0` — are
always true regardless of whether the recall actually works. `suggest_meal()` returns a
non-empty string on **every possible code path**:

- `if not results:` branch returns `"Suggested meal: No dietary constraints on record — anything goes!"` (non-empty string).
- `else:` branch returns a formatted string (non-empty string).

A completely broken `scope.recall()` that always returns `[]` would pass this test.
The test is supposed to verify DEMO-01 — that the coach entrypoint exercises the engine
end-to-end with the seeded allergy. It should assert the allergy fact appears in the
suggestion.

**Fix:**
```python
result = await suggest_meal(scope, "what can I eat for lunch")
assert isinstance(result, str)
assert len(result) > 0
# Assert the engine actually recalled the seeded allergy (not trivially vacuous):
assert "peanut" in result.lower() or "allergic" in result.lower(), (
    f"suggest_meal should surface the seeded peanut allergy in the suggestion, got: {result!r}"
)
```

---

## Info

### IN-01: `write_eval_report` is declared `async` but contains no `await` statements

**File:** `src/mnema/eval/baseline.py:351-441`
**Issue:** `write_eval_report` is an `async def` function but performs only synchronous
I/O — `output_path.write_text(content, encoding="utf-8")`. There is no `await` in the
function body. The `async` declaration forces callers to `await` it unnecessarily and
implies async I/O that does not exist, which is misleading. The function should be
`def write_eval_report(...)`.

**Fix:**
```python
# Change:
async def write_eval_report(
    results: EvalResults,
    output_path: Path,
    *,
    suite_description: Optional[str] = None,
) -> None:

# To:
def write_eval_report(
    results: EvalResults,
    output_path: Path,
    *,
    suite_description: Optional[str] = None,
) -> None:
```
(Remove all `await write_eval_report(...)` call sites accordingly.)

---

### IN-02: `run_session` docstring documents the private `_t1.close()` instead of the public `t1.close()`

**File:** `src/mnema/demo/coach.py:69`
**Issue:** The docstring for `run_session` says:
> "calls `engine.consolidate()` and `engine._t1.close()` (WAL flush)"

The actual code (line 106) correctly uses the public property: `engine.t1.close()`.
The docstring contradicts the implementation and could lead a future maintainer to
copy the wrong pattern. The verifier noted this discrepancy in the issue description
(`engine.t1.close()` vs `engine._t1.close()`).

**Fix:**
```
# In docstring line 69, change:
"calls engine.consolidate() and engine._t1.close() (WAL flush)"
# To:
"calls engine.consolidate() and engine.t1.close() (WAL flush)"
```

---

### IN-03: `_assemble_naive_context` re-reads T0 files on every probe iteration

**File:** `src/mnema/eval/baseline.py:268`
**Issue:** `_assemble_naive_context(cfg.local_fs_path)` is called inside the
`for probe in PROBES` loop. Since all seed data is written before the probe loop
begins, the assembled context is identical on all three iterations. The files are
read three times instead of once. This is a minor inefficiency (small files in tests)
but also means `naive_tokens` in the results dict is the same value for all three
probes, which the EVAL.md report presents as three separate per-probe columns — the
report implies naive token cost is query-dependent when it is not.

**Fix:**
```python
# Before the probe loop, assemble once:
naive_context = _assemble_naive_context(cfg.local_fs_path)
naive_tokens = counter.count(naive_context)

for probe in PROBES:
    # mnema is still per-probe (query-dependent):
    mnema_records = await scope.recall(probe.query, budget=EVAL_BUDGET)
    mnema_context = "\n".join(
        r.summary if r.summary else r.content[:80] for r in mnema_records
    )
    mnema_tokens = counter.count(mnema_context)
    # ... rest of probe logic unchanged, using pre-computed naive_context / naive_tokens
```

---

_Reviewed: 2026-06-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
