---
phase: 05-reference-demo-evaluation
verified: 2026-06-15T12:00:00Z
status: passed
score: 6/6
overrides_applied: 0
---

# Phase 5: Reference Demo & Evaluation — Verification Report

**Phase Goal:** An interactive nutrition coach proves the engine end-to-end through the SDK alone, and a before/after baseline quantifies MNEMA against naive transcript-stuffing on the same suite.
**Verified:** 2026-06-15
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | DEMO-01: coach.suggest_meal() runs on build_engine(LocalConfig) and returns a constraint-respecting string; test_coach_entrypoint is a live PASSED test (xfail removed) | VERIFIED | `test_coach_entrypoint` PASSED (no xfail marker). Manual smoke: returns "Suggested meal considering your constraints: - I am allergic to peanuts". `suggest_meal` calls `scope.recall(budget=300)` and formats recalled facts. |
| 2 | DEMO-02: cross-session recall uses a PERSISTENT store (not :memory:) — engine#1 writes + consolidates + closes (WAL checkpoint), engine#2 reopens SAME store and recall honors the constraint | VERIFIED | `test_cross_session_recall` PASSED. Fixture uses `data_dir / "mnema.db"` (real file). `close_engine()` calls `eng.t1.close()` (the `close()` method with WAL checkpoint). Engine#2 opened over same cfg asserts "peanut" in recall. |
| 3 | DEMO-03: supersession test asserts the MECHANISM — old record valid_until is not None AND superseded_by set (not just chat text) | VERIFIED | `test_supersession_surfaces_fields` PASSED. Directly fetches old record via `eng.t1.get(old_id)` and asserts `old_record.valid_until is not None` and `old_record.superseded_by is not None`. Also asserts retired record excluded from recall. |
| 4 | DEMO-04: backdated transient is evicted then recovered via expand(); protected allergy survives (protected=True, valid_until None); protected never evicted | VERIFIED | `test_decay_protected_and_recovery` PASSED. Asserts `evicted_count >= 1`, "peanut" in allergy recall after evict, kale not in live records, `expand(kale_id)` returns non-None Turn with "kale" in content. |
| 5 | DEMO-05: packed context non-protected token count <= budget AND one verbatim expand() returns the Turn | VERIFIED | `test_budget_packing_and_expand` PASSED. Asserts `non_protected_tokens <= BUDGET (300)` using TiktokenCounter, protected allergy always in results, `scope.expand(protected_results[0].id)` returns Turn with "peanut". |
| 6 | EVAL-02: run_eval() compares naive vs MNEMA with containment metrics + token counts; EVAL.md exists with real numbers; naive excludes archived.jsonl/eviction_audit.jsonl; MNEMA passes superseded-fact avoidance where naive fails; MNEMA uses fewer context tokens | VERIFIED | `test_eval_baseline_comparison` PASSED. EVAL.md at project root: MNEMA 3/3 PASS, Naive 2/3 (supersession FAIL), 38.1% token reduction (13.0 avg MNEMA vs 21.0 avg naive). `_assemble_naive_context` excludes `archived.jsonl` and `eviction_audit.jsonl` explicitly. |

**Score:** 6/6 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mnema/demo/__init__.py` | Package marker | VERIFIED | File exists, importable |
| `src/mnema/demo/coach.py` | suggest_meal() + run_session() + __main__ | VERIFIED | Full implementation; `suggest_meal` calls `scope.recall(budget=300)`; `__main__` block present; `if __name__` block confirmed |
| `src/mnema/eval/__init__.py` | Package marker | VERIFIED | File exists, importable |
| `src/mnema/eval/baseline.py` | PROBES list (3), run_eval(), write_eval_report(), containment_check() | VERIFIED | 3 Probes; `run_eval` fully implemented with try/finally teardown; `write_eval_report` produces EVAL.md; `containment_check` deterministic scorer |
| `src/mnema/adapters/vector_store/sqlite_t1.py` | `async def close()` with WAL checkpoint | VERIFIED | Lines 242-258; `PRAGMA wal_checkpoint(FULL)` before `self._db.close()`; idempotent (try/except) |
| `tests/test_demo_coach.py` | 5 PASSED tests, no xfail | VERIFIED | 5 tests PASSED; only xfail mention is in module docstring (comment), no decorators |
| `tests/test_eval_baseline.py` | test_eval_baseline_comparison PASSED, no xfail | VERIFIED | 1 test PASSED; no xfail marker anywhere |
| `EVAL.md` | Project root, real numbers, Methodology section | VERIFIED | Date: 2026-06-15; Results table with Naive/MNEMA columns; Token Efficiency section; Methodology paragraph |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `SqliteT1.close()` | `self._db.close()` | `PRAGMA wal_checkpoint(FULL)` + `await self._db.close()` | WIRED | Lines 254-255 of sqlite_t1.py |
| `test_cross_session_recall` | `SqliteT1.close()` | `close_engine()` calls `eng.t1.close()` | WIRED | `t1` is a public `@property` returning `self._t1`; confirmed in engine.py line 159 |
| `test_supersession_surfaces_fields` | consolidation pipeline | `await eng.consolidate()` after second `remember()` | WIRED | Two consolidate() calls; mechanism asserted via direct field inspection |
| `suggest_meal` | `scope.recall(budget=300)` | `results = await scope.recall(query, budget=300)` | WIRED | coach.py line 51 |
| `baseline.run_eval()` | LocalFS JSONL files (naive baseline) | `Path(local_fs_path).glob("*.jsonl")` excluding archived/audit | WIRED | baseline.py lines 196-210 |
| `baseline.run_eval()` | `scope.recall(query, budget=EVAL_BUDGET)` | MNEMA budgeted context assembly | WIRED | baseline.py line 269 |
| `write_eval_report()` | `EVAL.md` | `output_path.write_text(content, encoding="utf-8")` | WIRED | baseline.py line 441 |
| `test_eval_baseline_comparison` | project root EVAL.md | `Path(__file__).parent.parent / "EVAL.md"` + `write_eval_report` | WIRED | test_eval_baseline.py lines 85-87 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `suggest_meal()` | `results` (list[MemoryRecord]) | `await scope.recall(query, budget=300)` | Yes — live engine query over sqlite T1 | FLOWING |
| `run_eval()` naive context | `naive_context` (str) | `_assemble_naive_context()` reads JSONL from LocalFS | Yes — reads actual written T0 turns | FLOWING |
| `run_eval()` MNEMA context | `mnema_context` (str) | `scope.recall(probe.query, budget=EVAL_BUDGET)` | Yes — live recall against seeded engine | FLOWING |
| `test_cross_session_recall` | `results` from engine#2 | SqliteT1 (persistent file, not :memory:) | Yes — real SQLite file re-opened | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| suggest_meal returns constraint content | `python -c "...smoke() smoke..."` | "Suggested meal considering your constraints: - I am allergic to peanuts" | PASS |
| All 6 Phase 5 tests GREEN, no xfail | `pytest tests/test_demo_coach.py tests/test_eval_baseline.py -v` | 6 passed in 4.03s | PASS |
| Full suite 124 passed, 71 skipped, 0 failed | `pytest tests/ -q` | 124 passed, 71 skipped in 19.41s | PASS |
| pyright clean on demo/eval modules | `pyright src/mnema/demo/ src/mnema/eval/` | 0 errors, 0 warnings, 0 informations | PASS |
| ruff clean on demo/eval + test files | `ruff check src/mnema/demo/ src/mnema/eval/ tests/test_demo_coach.py tests/test_eval_baseline.py` | All checks passed | PASS |

---

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes found in this phase. Phase gate verification commands were run directly (see Behavioral Spot-Checks above).

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| DEMO-01 | 05-01-PLAN.md | Interactive nutrition-coach app runs on the engine | SATISFIED | `test_coach_entrypoint` PASSED; `suggest_meal()` returns constraint-respecting string; `__main__` + `run_session()` implement the CLI loop |
| DEMO-02 | 05-01-PLAN.md | Cross-session recall — constraints from early session respected later | SATISFIED | `test_cross_session_recall` PASSED; uses persistent SQLite file; WAL checkpoint before session 2 open |
| DEMO-03 | 05-01-PLAN.md | Supersession — diet change retires old record, surfaces valid_until/superseded_by | SATISFIED | `test_supersession_surfaces_fields` PASSED; asserts mechanism fields directly, not just chat text |
| DEMO-04 | 05-02-PLAN.md | Decay + protected fact — backdated transient evicted, pinned allergy survives | SATISFIED | `test_decay_protected_and_recovery` PASSED; evict count >= 1; allergy in recall; expand() recovers kale turn |
| DEMO-05 | 05-02-PLAN.md | Budget packing — large history packed under token budget with verbatim expand | SATISFIED | `test_budget_packing_and_expand` PASSED; non_protected_tokens <= 300; protected allergy always in results |
| EVAL-02 | 05-03-PLAN.md | Before/after baseline comparing naive vs MNEMA; EVAL.md with methodology | SATISFIED | `test_eval_baseline_comparison` PASSED; EVAL.md at project root with real numbers (MNEMA 3/3, Naive 2/3, 38% token reduction) |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/mnema/eval/baseline.py` | 309 | `engine._t1._db.close()` bypasses public `close()` (skips WAL checkpoint) in eval teardown | INFO | No functional impact — eval doesn't need WAL persistence across sessions; engine is discarded after run_eval(); try/except swallows any error. Not a stub; teardown is correct. |

No TBD/FIXME/XXX markers found in any Phase 5 modified files. No placeholders or NotImplementedError in delivered code.

---

### Human Verification Required

One behavior is human-only by design (documented in 05-VALIDATION.md):

**Interactive coach feel (DEMO-01)**
- **Test:** Run `uv run python -m mnema.demo.coach --data-dir mnema_demo_data --session-id session-1`, chat, state an allergy, change diet, observe that subsequent meal suggestions respect the allergy and the updated preference.
- **Expected:** CLI interactive loop reads stdin, stores turns, prints constraint-respecting meal suggestions, exits cleanly on "quit" with WAL flush confirmation.
- **Why human:** Real interactive I/O is not tested in automated tests; correctness is covered by `test_coach_entrypoint`, but the interactive loop feel and the actual stdin/stdout behavior require a human to verify.

All correctness behaviors (cross-session persistence, supersession mechanism, decay + protected-fact invariant, budget packing, eval metrics) are fully covered by automated tests that passed. The human item is UX-only and does not block the phase goal from being achieved — the automated evidence is sufficient for goal verification.

---

### Gaps Summary

No gaps. All 6 must-have truths are VERIFIED, all artifacts exist and are substantive and wired, all key links confirmed, gate checks (pytest 124/0, pyright 0 errors, ruff clean) pass, EVAL.md contains real numbers from a passing eval run.

The one INFO-level observation (eval teardown uses `_t1._db.close()` instead of the public `close()`) has no behavioral impact — the eval does not perform a cross-session reopen and the resources are still closed correctly.

---

_Verified: 2026-06-15T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
