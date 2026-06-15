---
phase: 02-consolidation-supersession
verified: 2026-06-14T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 2: Consolidation & Supersession Verification Report

**Phase Goal:** The slow offline pipeline turns raw turns into clean, deduped, non-contradicting typed records — the highest-risk correctness surface — while still fully local and deterministic.
**Verified:** 2026-06-14
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Consolidation drains the staging queue, extracts typed records via the cheap LLM, and pins safety/medical content to `protected` | VERIFIED | `ConsolidationPipeline.run()` drains via `_drain_queue()`, calls `_llm.complete(EXTRACT_RECORDS:...)`, pins `protected=True`+`salience=1.0` via `_is_safety_claim()` (write_path import). `test_staging_queue_drained` + `test_safety_content_pinned_protected` both green. |
| 2 | A contradicting claim actively supersedes the old record (valid_until + superseded_by + supersedes edge in one transaction), while a non-contradicting refinement merges in place | VERIFIED | `_apply_verdict()` calls `record_store.supersede()` for contradict; `supersede()` wraps UPDATE old + INSERT new + INSERT vector in explicit `BEGIN`/`COMMIT`/`rollback`. Refine path calls `record_store.update()` in-place with `protected_final` guard. `test_contradiction_supersession_atomic` + `test_refinement_merges_in_place` both green. |
| 3 | Provisional records are reconciled by t0_id identity and upgraded in place — never re-extracted into a parallel duplicate — and re-running consolidation is idempotent | VERIFIED | `find_by_t0_ref` filters `AND provisional = 1` (CR-03 fix confirmed in sqlite_t1.py:317). Confirmed records not re-touched on rerun. `test_provisional_reconciled_in_place` + `test_idempotent_rerun` both green. |
| 4 | A protected/fact-type record is never auto-superseded on an LLM contradiction alone (requires explicit forget), proven by a seeded contradiction test | VERIFIED | `_apply_verdict()` lines 331-345: structural two-branch early-return at top of `contradict` block — `if existing.protected or existing.record_type == RecordType.FACT: ... return`. No code path from contradict+protected to supersession. `test_cons08_protected_never_superseded` green, asserts `valid_until is None` AND `contradiction_pending` edge present. |
| 5 | A decay pass computes `keep_score` (recency decay + reinforcement + salience) over all live records | VERIFIED | `decay.py`: `keep_score()` formula `0.4*exp(-0.05*age) + 0.3*log(1+access_count) + 0.3*salience`, clamped to [0,1]. `decay_pass` async generator skips protected records before scoring (FORG-03 structural guarantee). Called in `ConsolidationPipeline.run()` step 7. `test_keep_score_values` + `test_protected_skipped_before_score_math` both green. |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mnema/core/consolidation.py` | ConsolidationPipeline class (7-step pipeline) | VERIFIED | 417 lines; all 5 methods present (run, _drain_queue, _process_turn, _apply_verdict, _insert_new_confirmed); no cloud imports at runtime (TYPE_CHECKING guard confirmed) |
| `src/mnema/core/engine.py` | MemoryEngine.consolidate() wired to ConsolidationPipeline; llm parameter | VERIFIED | `consolidate()` calls `self._consolidation_pipeline.run()` + `self._scheduler.trigger_now()`; `llm: LLMProvider | None = None` parameter with StubLLM lazy default |
| `src/mnema/core/write_path.py` | staging queue put extended with user_id key | VERIFIED | Line 179: `await self._staging_queue.put({"turn": turn, "t0_ref": t0_ref, "user_id": user_id})` |
| `src/mnema/core/decay.py` | keep_score + decay_pass pure-sync module | VERIFIED | Pure sync `keep_score()`, async generator `decay_pass()` with FORG-03 protected skip |
| `src/mnema/adapters/vector_store/sqlite_t1.py` | supersede() + find_by_t0_ref() | VERIFIED | `supersede()` uses explicit BEGIN/COMMIT/rollback + rowcount check (CR-02, WR-04 fixes); `find_by_t0_ref()` filters `AND provisional = 1` (CR-03 fix) |
| `src/mnema/adapters/llm/stub.py` | StubLLM deterministic adapter | VERIFIED | Dispatches on `EXTRACT_RECORDS:` / `JUDGE_CONTRADICTION:` sentinels; sha256 mod 3 for deterministic verdicts; no network |
| `tests/test_consolidation.py` | 8 GREEN tests covering CONS-01..08 | VERIFIED | All 8 tests pass; no skips or xfails |
| `tests/test_decay.py` | 2 GREEN decay tests covering FORG-01 + protected guard | VERIFIED | Both tests pass |
| `src/mnema/ports/record_store.py` | RecordStore Protocol extended with supersede + find_by_t0_ref + upsert_with_vector | VERIFIED | All 7 methods declared including `upsert_with_vector` (CR-04 fix) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `consolidation.py` | `write_path.py` | `from mnema.core.write_path import _is_safety_claim` | VERIFIED | Line 28 of consolidation.py; safety pinning uses write_path rule, not duplicated |
| `consolidation.py` | `record_store.py` | `await self._record_store.supersede()` + `find_by_t0_ref()` | VERIFIED | Lines 373 and 223 of consolidation.py call the Protocol methods |
| `engine.py` | `consolidation.py` | `ConsolidationPipeline(...)` in `__init__` | VERIFIED | Lines 126-133 of engine.py; lazy import pattern |
| `consolidation.py` | `decay.py` | `from mnema.core.decay import decay_pass` | VERIFIED | Line 138 of consolidation.py; called in run() step 7 |
| `test_consolidation.py` | `engine.py` | `await engine_with_llm.consolidate()` | VERIFIED | All 8 tests call consolidate() through the engine fixture |

---

### Goal-Backward Correctness Checks

#### CONS-08: Structural early-return in `_apply_verdict`

Code at `consolidation.py:331-345`:
```python
if verdict == "contradict":
    # CONS-08: structural gate — ALWAYS check protected/FACT FIRST.
    if existing.protected or existing.record_type == RecordType.FACT:
        # record contradiction_pending edge, return
        ...
        return  # Existing record remains live — NO supersession
    # Not protected/FACT → supersession
    ...
    await self._record_store.supersede(...)
    return
```
The gate is at the TOP of the `contradict` branch, not nested inside supersession. There is no bypass path.

Test `test_cons08_protected_never_superseded` (line 301-396):
- Sub-test (a): verifies allergy content yields `protected=True` after consolidation
- Sub-test (b): manually pins `protected=True` on a non-safety record, seeds `contradict` verdict, asserts `valid_until is None` AND `contradiction_pending` edge present
- Assertion is NOT weakened — full triple check: record still live, contradiction_pending edge present, valid_until IS None

#### Protected flag monotonic-upward (never cleared)

Reconcile path (`consolidation.py:230-231`):
```python
protected_final = (
    bool(ext.get("protected", False)) or existing_provisional.protected
)
```

Refine path (`consolidation.py:320`):
```python
protected_final = bool(ext.get("protected", False)) or existing.protected
```

Both paths use the OR pattern — consolidation can SET but never CLEAR the protected flag. This was WR-01 in the code review, confirmed fixed.

#### CONS-04 Atomicity in `supersede()`

`sqlite_t1.py:268-291`: Uses explicit `BEGIN` (CR-02 fix) + rowcount assertion (WR-04 fix) + `rollback` on any exception. Transaction wraps all three SQL statements: UPDATE old + INSERT new + INSERT vector.

#### CONS-07 Idempotency in `find_by_t0_ref`

`sqlite_t1.py:313-323`: Filters `AND provisional = 1` (CR-03 fix). A confirmed record (provisional=0) with the same t0_ref is NOT returned, so the reconciliation branch is not entered on the second run. The staging queue is empty on the second run anyway (items drained on first run + `task_done()` called — CR-01 fix).

#### Determinism: all tests use StubLLM + StubEmbedder

Confirmed: no network calls, no cloud provider imports in consolidation path. `conftest.py` wires `engine_with_llm` fixture with `StubLLM` + `StubEmbedder` + in-memory SQLite.

#### "Fully local": no cloud imports in consolidation path

Grep of `consolidation.py` for dashscope/anthropic/voyage/openai/boto3: no matches. TYPE_CHECKING guard prevents any runtime adapter imports.

---

### Data-Flow Trace (Level 4)

Not applicable to the consolidation pipeline — it is a processing pipeline, not a component that renders dynamic data. The data flow is: staging queue → LLM extraction → T1 record store. The T1 store is verified to produce real SQL queries (not empty returns) by the passing test suite which exercises actual SQLite operations.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full 33-test suite | `uv run --extra dev pytest tests/ -q` | `33 passed in 1.55s` | PASS |
| CONS-08 safety gate test | `pytest tests/test_consolidation.py::TestConsolidation::test_cons08_protected_never_superseded -v` | PASSED | PASS |
| pyright type check | `uv run --extra dev pyright` | `0 errors, 0 warnings, 0 informations` | PASS |

---

### Probe Execution

No probes defined for this phase. Not applicable.

---

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|---------|
| CONS-01 | Consolidation drains staging queue, extracts typed records via LLM | SATISFIED | `ConsolidationPipeline.run()` + `test_staging_queue_drained` GREEN |
| CONS-02 | Salience judged; safety/medical pinned to `protected` | SATISFIED | `_is_safety_claim()` override in step 3; `test_safety_content_pinned_protected` GREEN |
| CONS-03 | Entity resolution matches by same subject+predicate via vector similarity | SATISFIED | KNN over live records with `ENTITY_MAX_DISTANCE`; `test_entity_resolution_finds_match` GREEN |
| CONS-04 | Contradicting match superseded atomically (valid_until + superseded_by + supersedes edge) | SATISFIED | `supersede()` wraps three SQL statements in one BEGIN/COMMIT; `test_contradiction_supersession_atomic` GREEN |
| CONS-05 | Non-contradicting match merged into existing record | SATISFIED | `_apply_verdict` refine branch updates in place; `test_refinement_merges_in_place` GREEN |
| CONS-06 | Provisional records reconciled in place by t0_ref, provisional flag cleared | SATISFIED | `find_by_t0_ref` + `update(provisional=False)`; `test_provisional_reconciled_in_place` GREEN |
| CONS-07 | Consolidation idempotent — no duplicate live records or dangling pointers on rerun | SATISFIED | `find_by_t0_ref` filters `provisional=1`; empty queue on second run; `test_idempotent_rerun` GREEN |
| CONS-08 | Protected/fact records never auto-superseded on LLM contradiction | SATISFIED | Structural early-return gate at top of contradict branch; `test_cons08_protected_never_superseded` GREEN with unweakened assertions |
| FORG-01 | Decay pass computes keep_score (recency + reinforcement + salience) over all live records | SATISFIED | `keep_score()` formula verified; `decay_pass` called in `run()` step 7; `test_keep_score_values` GREEN |

All 9 Phase 2 requirements SATISFIED.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `engine.py:249` | `# TODO Phase 3: evict to cold storage` | TODO in `forget()` stub | INFO | `forget()` is an intentional Phase 3 stub; deferred by design per ROADMAP Phase 3 scope. Not a Phase 2 gap. |

No TBD, FIXME, or XXX markers found in any Phase 2 source or test file.

**Debt marker gate:** No unresolved debt markers. The single TODO at `engine.py:249` is an explicitly phased forward reference (Phase 3 FORG-02/FORG-04 scope) — not a Phase 2 deliverable.

---

### Code Review CR Fixes Confirmed

| CR # | Issue | Fix Confirmed |
|------|-------|---------------|
| CR-01 | `_drain_queue` missing `task_done()` | FIXED — `self._staging_queue.task_done()` called after every `get_nowait()` (consolidation.py:167) |
| CR-02 | `supersede()` not wrapped in explicit transaction | FIXED — `await self._db.execute("BEGIN")` before first SQL statement (sqlite_t1.py:271) |
| CR-03 | `find_by_t0_ref` returned non-provisional confirmed records | FIXED — `AND provisional = 1` predicate added (sqlite_t1.py:317) |
| CR-04 | `_insert_new_confirmed` was non-atomic (upsert + upsert_vector separate) | FIXED — now calls `record_store.upsert_with_vector()` (consolidation.py:416); atomic method added to Protocol + SqliteT1 |
| WR-01 | `_apply_verdict` refine path did not preserve `protected` monotonically | FIXED — `protected_final = bool(ext.get("protected", False)) or existing.protected` in refine branch (consolidation.py:320) |
| WR-04 | `supersede()` no rowcount check — silent no-op on wrong user | FIXED — `if cursor.rowcount != 1: rollback + raise ValueError` (sqlite_t1.py:277-282) |
| WR-05 | `update()` only cast named bool fields; other bool fields stored as True/False string | FIXED — `elif isinstance(v, bool): serialized[k] = int(v)` covers all bool fields (sqlite_t1.py:348-350) |

Deferred items (WR-02, WR-03, IN-01, IN-02, IN-03) are tracked in `.planning/todos/pending/phase-02-code-review-deferred.md` and are all low-severity, Phase 4 concerns or cosmetic.

---

### Human Verification Required

None. All Phase 2 success criteria are verifiable programmatically through the test suite. The phase is fully local and deterministic.

---

## Gaps Summary

No gaps. All must-haves verified. All 9 requirements satisfied. All 4 code-review criticals and 3 warnings fixed. Full 33-test suite green. pyright 0 errors.

---

_Verified: 2026-06-14T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
