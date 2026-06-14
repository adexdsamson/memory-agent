---
phase: 02-consolidation-supersession
reviewed: 2026-06-14T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - src/mnema/adapters/llm/stub.py
  - src/mnema/core/decay.py
  - src/mnema/core/consolidation.py
  - src/mnema/ports/record_store.py
  - src/mnema/adapters/vector_store/sqlite_t1.py
  - src/mnema/core/engine.py
  - src/mnema/core/write_path.py
  - tests/test_consolidation.py
  - tests/test_decay.py
findings:
  critical: 4
  warning: 5
  info: 3
  total: 12
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-06-14T00:00:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 2 introduces the ConsolidationPipeline, atomic supersession, provisional reconciliation, and the keep_score decay pass. The core safety invariant (CONS-08 protected/FACT gate) is structurally sound — the early-return is at the top of the `contradict` branch and there is no bypass path. The `protected` flag monotonic-upward rule is correctly implemented in the reconciliation path.

However, four blockers require fixes before this code is safe to ship:

1. `_drain_queue` calls `get_nowait()` without calling `task_done()`, making the queue permanently "unfinished" — a correctness bug that silently breaks any caller relying on `asyncio.Queue.join()` (including APScheduler/scheduler coordination patterns).
2. `supersede()` does NOT wrap its three SQL statements in an explicit `BEGIN`/transaction block. Under aiosqlite's autocommit-by-default behaviour, the three `execute()` calls before `commit()` are not protected by a single transaction; a crash between statements produces partial state.
3. `find_by_t0_ref` returns ANY live record with the matching `t0_ref`, not just provisional ones — a semantic mismatch with the CONS-06/07 idempotency fence that causes a confirmed record to be re-upgraded on every re-run, silently resetting its `provisional=False` flag back to values supplied by the LLM.
4. `_insert_new_confirmed` calls `upsert()` and then `upsert_vector()` as two separate, non-atomic operations — a crash between them leaves an orphaned T1 record with no vector, which can never be found by KNN but will appear in `live_records()` and the decay pass.

---

## Critical Issues

### CR-01: `_drain_queue` never calls `task_done()` — queue joins hang permanently

**File:** `src/mnema/core/consolidation.py:162-166`
**Issue:** `asyncio.Queue.get_nowait()` removes an item from the queue but does NOT decrement the unfinished-task counter. Callers that call `await queue.join()` (e.g. APScheduler job-done tracking or any test that awaits the queue) will block forever. Even without a current `join()` call, adding one later (a common pattern when graduating to a real scheduler) will silently deadlock. This is a resource-correctness bug: the queue's internal counter leaks on every consolidation run.

**Fix:**
```python
def _drain_queue(self) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    while True:
        try:
            items.append(self._staging_queue.get_nowait())
            self._staging_queue.task_done()   # <-- required after every get_nowait()
        except asyncio.QueueEmpty:
            break
    return items
```

---

### CR-02: `supersede()` is NOT a single transaction — partial state possible on crash

**File:** `src/mnema/adapters/vector_store/sqlite_t1.py:268-282`
**Issue:** The three `execute()` calls inside `supersede()` are wrapped in a `try/except` that calls `rollback()` on exception — but aiosqlite operates in autocommit mode by default. Without an explicit `BEGIN`, each `execute()` is its own implicit transaction. If the process crashes after the `UPDATE` (retiring the old record) but before the `INSERT` of the new record, the old record is permanently retired with no successor — a data-loss scenario. The `rollback()` in the `except` branch only matters if the failure raises inside a live transaction; without `BEGIN` it does nothing useful.

**Fix:**
```python
async def supersede(self, old_id: str, new_record: MemoryRecord, embedding: list[float]) -> None:
    now_str = _dt_to_str(datetime.now(timezone.utc))
    async with self._db.execute("BEGIN"):   # explicit transaction
        pass
    try:
        await self._db.execute(
            "UPDATE t1_records SET valid_until=?, superseded_by=? WHERE id=? AND user_id=?",
            (now_str, new_record.id, old_id, new_record.user_id),
        )
        await self._db.execute(_INSERT_SQL, _record_params(new_record))
        await self._db.execute(
            "INSERT OR REPLACE INTO vec_t1(record_id, embedding) VALUES (?, ?)",
            (new_record.id, _v32(embedding)),
        )
        await self._db.commit()
    except Exception:
        await self._db.rollback()
        raise
```

A simpler and more idiomatic approach with aiosqlite is to use `async with self._db` as a context manager (which issues `BEGIN`/`COMMIT`/`ROLLBACK` automatically), but the explicit pattern above is the minimal surgical fix. The key invariant: `BEGIN` must precede the first `execute()`.

---

### CR-03: `find_by_t0_ref` returns non-provisional live records — idempotency fence is broken

**File:** `src/mnema/adapters/vector_store/sqlite_t1.py:304-311`
**Issue:** The SQL query is:
```sql
SELECT * FROM t1_records WHERE t0_ref = ? AND user_id = ? AND valid_until IS NULL
```
It does NOT filter `provisional = 1`. After a successful first consolidation run, the record for that `t0_ref` is live but `provisional = False`. On a second run (e.g., CONS-07 idempotency test), `find_by_t0_ref` returns this confirmed record and the pipeline enters the reconciliation branch (lines 220-241 of consolidation.py), calling `record_store.update()` to overwrite `record_type`, `salience`, `summary`, and `keywords` with whatever the LLM extracted in the current run. This silently re-applies LLM output to a confirmed record on every re-run, destroying any human or prior-consolidation edits. It also means the CONS-07 idempotency test passes by accident (record count stays 1) while the record's fields are quietly mutated.

The port definition (`ports/record_store.py:54-65`) documents the intent: "Return the live **provisional** record" — the implementation does not honour this.

**Fix:**
```python
async def find_by_t0_ref(self, t0_ref: str, user_id: str) -> MemoryRecord | None:
    cursor = await self._db.execute(
        "SELECT * FROM t1_records "
        "WHERE t0_ref = ? AND user_id = ? AND valid_until IS NULL AND provisional = 1",
        (t0_ref, user_id),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return row  # type: ignore[return-value]
```

---

### CR-04: `_insert_new_confirmed` is not atomic — orphaned records on crash between upsert and upsert_vector

**File:** `src/mnema/core/consolidation.py:374-405`
**Issue:** `_insert_new_confirmed` calls `record_store.upsert(record)` (line 404) and then `vector_index.upsert_vector(record.id, embedding)` (line 405) as two separate, non-atomic operations. If the process crashes (or an exception is raised inside `upsert_vector`) after `upsert()` succeeds, a live T1 record exists with no corresponding vector entry. This record will:
- Appear in `live_records()` and the decay pass (inflating the record count)
- Never be found by `vector_search()` (invisible to recall)
- Never be superseded by entity resolution (it cannot be found by KNN)

The same two-call pattern also appears at lines 170-171 in `write_path.py` for the provisional fast-path write. That path is lower-risk because the record is provisional, but the consolidation confirmed-record path is higher-risk because the confirmed record has no TTL-based cleanup path.

**Fix:** Delegate the combined record+vector insert to `SqliteT1.supersede()`-style atomicity. Either add a new `RecordStore.upsert_with_vector(record, embedding)` port method that wraps both operations in one transaction, or wrap the two calls in an explicit transaction guard inside `SqliteT1`. At minimum, if a protocol-level atomic method is not yet available, document this as a known data-integrity gap and add a repair/reconciliation check.

```python
# Preferred: add to RecordStore Protocol and SqliteT1
async def upsert_with_vector(self, record: MemoryRecord, embedding: list[float]) -> None:
    """Atomically insert record + vector in one transaction."""
    try:
        await self._db.execute("BEGIN")   # or use async-with context manager
        await self._db.execute(_INSERT_SQL, _record_params(record))
        await self._db.execute(
            "INSERT OR REPLACE INTO vec_t1(record_id, embedding) VALUES (?, ?)",
            (record.id, _v32(embedding)),
        )
        await self._db.commit()
    except Exception:
        await self._db.rollback()
        raise
```

---

## Warnings

### WR-01: `_apply_verdict` "refine" path does NOT preserve `protected` flag monotonically

**File:** `src/mnema/core/consolidation.py:310-319`
**Issue:** The `refine` branch calls `record_store.update()` with `salience` and `keywords` from the new extraction, but never touches `protected`. If the existing record has `protected=True` and the new extraction returns `protected=False` (e.g., a non-safety phrase that is a refinement), the `protected` flag is untouched because `update()` is a partial update. This is actually correct behaviour by omission — but only because `protected` is not included in the `update()` call. There is no explicit assertion or comment that the monotonic-upward rule is being honoured here, making it a latent correctness risk if a future refactor adds `protected=bool(ext.get("protected", False))` to the `refine` update payload (mirroring the reconciliation path at line 227-231).

The reconciliation path (lines 223-238) correctly computes `protected_final = bool(...) or existing_provisional.protected`. The `refine` path has no equivalent guard. The asymmetry is a silent maintenance trap.

**Fix:** Add an explicit monotonic-upward guard in the `refine` branch, mirroring the reconciliation path:
```python
if verdict == "refine":
    protected_final = bool(ext.get("protected", False)) or existing.protected
    await self._record_store.update(
        existing.id,
        content=new_content,
        summary=new_content[:60].strip(),
        salience=float(ext.get("salience", existing.salience)),
        keywords=list(ext.get("keywords", existing.keywords)),
        protected=protected_final,   # <-- explicit monotonic upward guard
    )
    return
```

---

### WR-02: `StubLLM._judge` is vulnerable to hash-space collisions between test users sharing the same content

**File:** `src/mnema/adapters/llm/stub.py:119-132`
**Issue:** `_judge` hashes `body.strip()` where `body = f"{existing}\n{new}"`. Two tests using the same content strings (but different `user_id`s, e.g. CONS-03 and CONS-05 both use `'spicy food preference item 1'`) produce identical hashes and identical verdicts. This is by design for the stub. However, the verdict depends only on the content pair, not on any test isolation boundary. If a future test accidentally uses a content string that produces a different verdict than expected (because a prefix collision occurs in the 1000-iteration search in `_find_new_content_for_verdict`), the test will fail non-obviously with no clear link to the stub logic.

More concretely: the `_find_new_content_for_verdict` helper in `test_consolidation.py` iterates `f"{prefix}_{i}_{existing_content[:20]}"`. The body hashed by `_judge` is `f"{existing}\n{candidate}"` — but `existing` here is the *extracted content* (what the LLM returned), not the raw `content` string passed to `remember()`. Since `StubLLM._extract` returns `content` verbatim (line 88-89), they happen to match. But if extraction ever truncates or reformats the content string, the verdict pre-computation in the test module (`_verdict_for_pair`) will diverge from what the pipeline actually hashes, silently producing wrong verdicts and flaky tests.

**Fix:** Add a comment in `_judge` and `_verdict_for_pair` explicitly documenting that the hashed body uses the *extracted* content (as returned by `_extract`), not the raw turn content, so future changes to `_extract` output format are caught as test invariant failures.

---

### WR-03: `consolidation.py` silently swallows all malformed LLM responses — no observability

**File:** `src/mnema/core/consolidation.py:185-192`
**Issue:** A `json.JSONDecodeError` or non-list response causes `_process_turn` to return silently (lines 187-192). The turn's `t0_ref` is never reconciled and the staging item was already drained from the queue (CR-01 context). There is no counter, log, or error signal. In production with a real LLM this means any hallucinated or truncated response causes a permanent silent data loss: the turn is dequeued, not processed, and never re-queued. The CONS-07 idempotency design assumes the pipeline can always reprocess a `t0_ref`, but once the queue item is drained there is no mechanism to re-enqueue it.

**Fix:** At minimum, log the failure (or raise to a counters dict) so operators can detect LLM extraction failures. Consider a dead-letter queue or a retry marker on the T0 record. For Phase 2 (stub LLM) this is low severity, but it is a correctness gap for the real LLM path.

```python
except (json.JSONDecodeError, ValueError):
    # TODO: dead-letter or re-enqueue for retry (Phase 4)
    import logging
    logging.getLogger(__name__).warning(
        "Malformed LLM response for t0_ref=%s; turn will not be consolidated", t0_ref
    )
    return
```

---

### WR-04: `supersede()` user_id cross-scope predicate is insufficient — silent no-op on wrong user

**File:** `src/mnema/adapters/vector_store/sqlite_t1.py:270-273`
**Issue:** The `UPDATE` uses `WHERE id=? AND user_id=?` as intended. However, if `old_id` belongs to a different user than `new_record.user_id` (an incorrect caller), the `UPDATE` silently matches 0 rows — SQLite does not raise an error for `UPDATE ... WHERE` that touches 0 rows. The insert of `new_record` and its vector then succeeds, leaving a dangling "supersedes" edge pointing at a record that was never actually retired. There is no rowcount check.

**Fix:**
```python
cursor = await self._db.execute(
    "UPDATE t1_records SET valid_until=?, superseded_by=? WHERE id=? AND user_id=?",
    (now_str, new_record.id, old_id, new_record.user_id),
)
if cursor.rowcount != 1:
    await self._db.rollback()
    raise ValueError(
        f"supersede(): old_id={old_id!r} not found or user_id mismatch; "
        f"expected user_id={new_record.user_id!r}"
    )
```

---

### WR-05: `update()` partial-update serializer does not handle `bool` fields that are NOT named `protected`/`provisional`

**File:** `src/mnema/adapters/vector_store/sqlite_t1.py:329-337`
**Issue:** The serialization loop at lines 329-337 only special-cases `bool` for the field names `"protected"` and `"provisional"`. Any other future boolean column (e.g., a hypothetical `"verified"` flag) would be passed through as a Python `bool` object, which SQLite will store as `True`/`False` string representations rather than `1`/`0` integers. The `_make_record` deserializer at line 140-141 only explicitly casts `protected` and `provisional` back to bool — meaning any other bool column round-trips incorrectly.

**Fix:** Generalise the bool cast to apply to all bool values:
```python
elif isinstance(v, bool):
    serialized[k] = int(v)   # covers all bool fields, not just named ones
```
This supersedes the current `elif k in ("protected", "provisional") and isinstance(v, bool)` check.

---

## Info

### IN-01: `decay_pass` return type annotation is incorrect — `async def` + `yield` = `AsyncGenerator`, not a coroutine

**File:** `src/mnema/core/decay.py:123-127`
**Issue:** The function signature declares `-> AsyncGenerator[tuple["MemoryRecord", float], None]` but is defined as `async def` with `yield` statements. An `async def` function containing `yield` is an async generator function — calling it returns an `AsyncGenerator`, not a coroutine. The return annotation is actually correct for the *returned object type*, but the function-level annotation placement is unusual and pyright/mypy may warn about it. The standard pattern is to annotate async generator functions with `AsyncIterator` or `AsyncGenerator` in the signature only, not as a `-> return type`. This can cause type-checker confusion when callers do `async for x in decay_pass(...)` vs `async for x in await decay_pass(...)`.

The actual runtime behaviour is correct because `async for item in decay_pass(...)` calls the generator function and iterates it. No `await` is needed. But `decay.py` line 127 annotation may mislead readers into thinking `await decay_pass(...)` is the calling convention.

**Fix:** Either leave as-is (it works at runtime) or change to:
```python
async def decay_pass(
    record_store: "Any",
    user_id: str,
    now: datetime | None = None,
) -> AsyncIterator[tuple["MemoryRecord", float]]:
```
and add `from collections.abc import AsyncIterator` to the imports.

---

### IN-02: `_EXTRACT_SENTINEL` and `_JUDGE_SENTINEL` are duplicated across `stub.py` and `consolidation.py`

**File:** `src/mnema/adapters/llm/stub.py:70-73` and `src/mnema/core/consolidation.py:49-56`
**Issue:** `stub.py` uses inline string literals `"EXTRACT_RECORDS:"` and `"JUDGE_CONTRADICTION:"` checked with `in` (line 70, 72). `consolidation.py` defines the same strings as `_EXTRACT_SENTINEL` and `_JUDGE_SENTINEL` constants. These are the *protocol* sentinels — they must stay in sync. If `consolidation.py`'s constants change, `stub.py` will silently continue to match the old strings, causing StubLLM to return `""` for all prompts and all extraction/judging to silently no-op.

**Fix:** Import and use the constants from `consolidation.py` (or a shared `mnema.core.prompts` module) in `stub.py` instead of hardcoding the strings:
```python
from mnema.core.consolidation import _EXTRACT_SENTINEL, _JUDGE_SENTINEL
```
Or move the sentinels to a dedicated shared location both modules import from.

---

### IN-03: `_find_new_content_for_verdict` in `test_consolidation.py` has a magic limit of 1000 with a `RuntimeError` — no guidance on what to do

**File:** `tests/test_consolidation.py:52-57`
**Issue:** The helper iterates up to 1000 candidates and raises `RuntimeError` if none produce the target verdict. With sha256 mod 3, the probability of not finding a match in 1000 trials is `(2/3)^1000 ≈ 10^{-176}` — astronomically unlikely. However, the function is declared in a test module without a docstring explaining this probability bound, and the `RuntimeError` message gives no actionable guidance. It is also called at test-collection time indirectly if any test module-level code calls it (it is currently only called from within test bodies, which is fine).

**Fix:** Add a comment documenting the probability bound and that 100 iterations would be more than sufficient:
```python
# The probability of not finding a match in 1000 trials is (2/3)^1000 ≈ 10^-176.
# 20 iterations would be sufficient in practice; 1000 is a safe paranoia cap.
```

---

_Reviewed: 2026-06-14T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
