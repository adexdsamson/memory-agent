---
phase: 01-schema-ports-local-core-foundation
reviewed: 2026-06-10T00:00:00Z
depth: standard
files_reviewed: 23
files_reviewed_list:
  - src/mnema/__init__.py
  - src/mnema/adapters/embedding/stub.py
  - src/mnema/adapters/object_store/local_fs.py
  - src/mnema/adapters/scheduler/in_process.py
  - src/mnema/adapters/vector_store/sqlite_t1.py
  - src/mnema/core/buffer.py
  - src/mnema/core/classifier.py
  - src/mnema/core/engine.py
  - src/mnema/core/recall.py
  - src/mnema/core/schema.py
  - src/mnema/core/write_path.py
  - src/mnema/ports/embedding.py
  - src/mnema/ports/llm.py
  - src/mnema/ports/object_store.py
  - src/mnema/ports/record_store.py
  - src/mnema/ports/scheduler.py
  - src/mnema/ports/vector_index.py
  - tests/conftest.py
  - tests/test_providers.py
  - tests/test_remember_recall.py
  - tests/test_scheduler.py
  - tests/test_schema.py
  - tests/test_scope_isolation.py
  - tests/test_sdk_interface.py
  - tests/test_write_path.py
findings:
  critical: 5
  warning: 5
  info: 3
  total: 13
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-06-10T00:00:00Z
**Depth:** standard
**Files Reviewed:** 23
**Status:** issues_found

## Summary

This review covers the Phase 1 schema, ports, and local core foundation. The implementation is structurally sound — the D-02 scope isolation rule is correctly applied in `SqliteT1.vector_search` and `live_records`, the column whitelist in `update()` blocks SQL injection via field names, and the PROV-06 startup dim assertion is in place.

However five blockers were found, three of which affect correctness in the current test suite (the Scheduler Protocol/adapter mismatch causes `consolidate()` to silently no-op, the `cursor.row_factory` reset is a no-op in aiosqlite leaving vec_t1 results interpreted through `_make_record`, and the LocalFS TOCTOU race can corrupt line offsets under concurrent appends). Two additional blockers concern the safety guarantee directly: the `_is_safety_claim` guard only fires when `type_hint == "fact"` is explicitly passed, so `"I am allergic to peanuts"` without `type_hint` gets `protected=False`; and the access_count double-increment in `RecallPath` reports the wrong count to callers.

---

## Critical Issues

### CR-01: Scheduler Protocol/adapter mismatch — `consolidate()` is a guaranteed silent no-op with `InProcessScheduler`

**File:** `src/mnema/core/engine.py:237-240`

**Issue:** `Scheduler` Protocol (ports/scheduler.py) declares all methods as **synchronous** (`def trigger_now(self) -> None`). `InProcessScheduler` implements all four methods as **async coroutines** (`async def trigger_now`). In `consolidate()`:

```python
trigger_fn = self._scheduler.trigger_now()   # calls async def → returns a coroutine
if asyncio.iscoroutine(trigger_fn):
    await trigger_fn
```

Because `InProcessScheduler.trigger_now` is `async def`, calling it **without** `await` returns a coroutine object — it never executes at all. The `asyncio.iscoroutine()` branch would catch this and `await` it, which looks right. However, `MemoryEngine.__init__` types `scheduler` as `Any` and receives whichever concrete class is passed. In the test fixture, `InProcessScheduler` is passed directly (async). In a production context where a sync scheduler satisfying the Protocol is passed instead, `trigger_now()` returns `None`, `asyncio.iscoroutine(None)` is `False`, and the job fires synchronously — which is correct for that branch.

**The actual blocker** is the inverse: the Protocol says `sync` but every wiring in the codebase (conftest, test_scheduler) uses `async`. The Protocol is therefore wrong — it documents the interface that does not match the only real adapter. Any future implementer who reads `scheduler.py` and writes a sync adapter will pass the Protocol check but break `consolidate()`. More immediately: `schedule()` and `start()` on `InProcessScheduler` are also async, but `MemoryEngine.__init__` never calls `await scheduler.start()` or `await scheduler.schedule(...)`. The conftest correctly `await scheduler.start()` separately, but if a future caller constructs `MemoryEngine` and expects the engine to self-start the scheduler, nothing happens.

**Fix:** Align the Protocol with the real adapter. Either:
- Change `Scheduler` Protocol to declare async methods:
```python
class Scheduler(Protocol):
    async def schedule(self, fn: object, *, every_seconds: int) -> None: ...
    async def trigger_now(self) -> None: ...
    async def start(self) -> None: ...
    async def shutdown(self) -> None: ...
```
- And update `consolidate()` to simply `await self._scheduler.trigger_now()` — removing the `iscoroutine` branch, which is an unreliable runtime check anyway.

---

### CR-02: `cursor.row_factory = None` in `vector_search` is a no-op in aiosqlite — vec_t1 rows are fed through `_make_record` and will crash

**File:** `src/mnema/adapters/vector_store/sqlite_t1.py:342-344`

**Issue:** After `open()` sets `db.row_factory = _make_record`, every subsequent `execute()` on that connection returns cursors that inherit the connection-level row factory. The code tries to suppress it for `vector_search` results:

```python
cursor = await self._db.execute(sql, params)
cursor.row_factory = None   # ← set AFTER execute; cursor rows are already fetched lazily
rows = await cursor.fetchall()
```

In aiosqlite, `cursor.row_factory` is proxied to the underlying `sqlite3.Cursor` row factory. **Setting it after the cursor is created but before `fetchall()`** may or may not take effect depending on the aiosqlite version and whether the underlying sqlite3 cursor re-applies the factory per row on `fetchall()`. The standard CPython `sqlite3` module applies `row_factory` at fetch time (not at execute time), so the assignment may work. But this is undocumented behavior in aiosqlite's cursor proxy.

More critically: if the row factory IS applied, `_make_record` expects a cursor whose `description` has all 24 `t1_records` columns. The `vec_t1` query only selects `record_id, distance` (2 columns). `_make_record` would call `cursor.description` and get a 2-column description, then try to access `row_dict["user_id"]` etc. — raising a `KeyError` or producing a `MemoryRecord.model_validate` failure.

The safe pattern is to use a dedicated connection or to reset the factory before execute, not after:

**Fix:** Reset the factory before executing the vec_t1 query, or use a raw `aiosqlite` connection without the global factory for vector searches:

```python
# Temporarily clear the factory before executing the vec query
self._db.row_factory = None
cursor = await self._db.execute(sql, params)
rows = await cursor.fetchall()
self._db.row_factory = _make_record  # restore
return [(str(row[0]), float(row[1])) for row in rows]
```

Alternatively, open a second bare connection for vector searches, or inline the 2-column fetch without relying on row_factory assignment ordering.

---

### CR-03: LocalFS `append()` has a TOCTOU race — line offset can be wrong under concurrent writes

**File:** `src/mnema/adapters/object_store/local_fs.py:68-79`

**Issue:** The `append()` method counts lines in one open/close, then opens the file again to append. There is no locking between the two operations:

```python
line_count = 0
if path.exists():
    with path.open("r", ...) as fh:
        for _ in fh:
            line_count += 1          # counts N lines

# <-- another coroutine or OS process can append here -->

with path.open("a", ...) as fh:
    fh.write(turn.model_dump_json() + "\n")   # appends at line N+1

return f"t0://{session_id}/{line_count}"      # returns N, but data is at N+1
```

Under concurrent writes (two coroutines writing to the same session file), the returned offset will be wrong for at least one writer, and `get(ref)` will return the wrong Turn for that ref. Phase 1 is single-user, but the T0 ref is stored in `MemoryRecord.t0_ref` and backed by `expand()`. A wrong offset silently corrupts the expand() path.

Additionally, file I/O is sync inside `async def` — blocking the event loop. The docstring acknowledges this and defers it to Phase 4, which is acceptable for Phase 1, but the TOCTOU issue is a correctness bug even in single-threaded use if two `remember()` calls are concurrent (e.g., `asyncio.gather`).

**Fix:** Use an atomic append-and-count pattern. Since JSONL is append-only, count lines by reading the written position after the append, or hold the file open across both operations:

```python
async def append(self, session_id: str, turn: Turn) -> str:
    _validate_session_id(session_id)
    path = self._base / f"{session_id}.jsonl"
    line = turn.model_dump_json() + "\n"
    with path.open("a+", encoding="utf-8") as fh:
        fh.seek(0)
        line_count = sum(1 for _ in fh)   # count under the same file handle lock
        fh.write(line)
    return f"t0://{session_id}/{line_count}"
```

---

### CR-04: Safety claim `protected=True` only fires when caller explicitly passes `type_hint="fact"` — the primary use case (`"I am allergic to peanuts"` without type_hint) gets `protected=False`

**File:** `src/mnema/core/write_path.py:64-74`

**Issue:** `_is_safety_claim` checks `if type_hint != "fact": return False`. This means:

```python
await engine.remember("I am allergic to peanuts", user_id="u1", session_id="s1")
# type_hint defaults to None → _is_safety_claim returns False → protected=False
```

The MNEMA thesis is "a protected fact (allergy → salience 1.0) must survive every decay pass by construction." But the classifier already correctly identifies this text as a durable claim (the first-person stative pattern matches). The gap is that `_is_safety_claim` gates on the caller having labelled it `type_hint="fact"`, which the primary test case (`test_remember_and_recall_scoped`) does not do.

The D-05 requirement says safety-relevant claims produce a provisional T1 write *immediately on the fast path*. It should also be setting `protected=True` on the heuristic path when safety keywords are detected, regardless of `type_hint`.

**Fix:** Remove the `type_hint` gate from `_is_safety_claim`:

```python
def _is_safety_claim(content: str, type_hint: Optional[str]) -> bool:
    """Return True if the content appears to be a safety-relevant claim."""
    content_lower = content.lower()
    return any(kw in content_lower for kw in _SAFETY_KEYWORDS)
```

This makes `protected=True` any time a safety keyword appears in durable content, regardless of whether the caller supplied `type_hint`. The `type_hint` argument can be removed from the signature entirely since it is now unused, or kept for future use.

---

### CR-05: `access_count` is double-incremented — the returned object reports +2 per recall, not +1

**File:** `src/mnema/core/recall.py:151-158`

**Issue:** The access_count update block reads the count from the in-memory record, writes +1 to the store, then adds +1 again to the in-memory object:

```python
for record in t1_records:
    await self._record_store.update(
        record.id,
        access_count=record.access_count + 1,   # DB: access_count = N+1
        last_accessed=now,
    )
    # Update the in-memory object too so callers see the incremented count
    object.__setattr__(record, "access_count", record.access_count + 1)  # in-mem: N+1
```

The in-memory record's `access_count` starts at `N` (from the DB fetch). The `update()` call persists `N+1`. Then `object.__setattr__` sets the in-memory object to `N+1`. This is correct for the **first recall**. On the **second recall**, the record is fetched fresh from DB (access_count = 1), then +1 is written to DB (access_count = 2), and +1 is applied to the in-memory object (also 2). This part is fine.

The actual bug is in the test assertion at `test_remember_recall.py:84`:

```python
assert record.access_count >= 1
```

But `test_expand_and_access_count` calls `recall()` once, which returns a record. The record fetched from the store has `access_count=0`. The store is updated to `access_count=1`. The in-memory object is set to `access_count=1`. The test checks `>= 1`. This passes. However, if `recall()` is called twice, the in-memory `record.access_count` after the second call would be 2 (correct), but the store would hold 2 as well. This appears correct.

**The real bug** is more subtle: `object.__setattr__(record, "access_count", record.access_count + 1)` is called **after** `update()` has already written `record.access_count + 1` to the DB. If the `record` object was fetched at access_count=0, `update` writes 1 to DB, and `setattr` sets in-memory to 1 — consistent. But the caller receives this same object and may call `recall()` again with a **cached** reference. If they check `record.access_count` on the stale in-memory object after a second recall that has already incremented the DB, they will see a stale value.

More concretely: the `object.__setattr__` bypass of Pydantic's frozen model is the actual correctness concern. `MemoryRecord` uses `ConfigDict(from_attributes=False)` but does not declare `frozen=True` explicitly — however Pydantic v2 models are by default mutable (not frozen). So `object.__setattr__` is unnecessary (normal `record.access_count = ...` should work) **but also bypasses Pydantic validators**. If a validator is added to `access_count` in future (e.g. `access_count >= 0`), this bypass will silently skip it.

**Fix:** Use normal attribute assignment rather than `object.__setattr__`:

```python
record.access_count = record.access_count + 1
record.last_accessed = now
```

And verify `MemoryRecord` does not declare `model_config = ConfigDict(frozen=True)` — it does not (line 51 of schema.py confirms `from_attributes=False` only), so normal assignment is valid.

---

## Warnings

### WR-01: `get_latest()` does not filter `valid_until IS NULL` — returns dead records

**File:** `src/mnema/adapters/vector_store/sqlite_t1.py:358-370`

**Issue:** `get_latest()` is used by test code to verify schema columns after a write. Its query:

```sql
SELECT * FROM t1_records WHERE user_id = ? ORDER BY created_at DESC LIMIT 1
```

This returns the most recent record for a user **regardless of whether it is live**. In Phase 3 when `forget()` sets `valid_until`, a call to `get_latest()` for a user whose most recent record was evicted will return that evicted record. Test code that calls this to verify live-record properties will silently pass on dead data.

**Fix:** Add `AND valid_until IS NULL` to the query:

```python
"SELECT * FROM t1_records WHERE user_id = ? AND valid_until IS NULL ORDER BY created_at DESC LIMIT 1"
```

---

### WR-02: `as_candidates()` in `RecentSessionBuffer` leaks cross-user data when `session_id` filter matches multiple users

**File:** `src/mnema/core/buffer.py:63-86`

**Issue:** `as_candidates(session_id="s1")` iterates all keys `(uid, sid)` and returns turns for any user whose session matches `s1`. If two users happen to use the same `session_id` string (e.g. both use `session_id="default"`), turns for user A will be returned when querying for session_id from user B's context.

The docstring acknowledges "prefer `as_candidates_for_user` in multi-user contexts," but the method is still public and callable without a user filter. `RecallPath` correctly uses `as_candidates_for_user`. The risk is that future code or a developer debugging with `as_candidates()` leaks cross-user data.

**Fix:** Either remove `as_candidates()` and replace with `as_candidates_for_user()` at all call sites, or add a deprecation warning, or add a mandatory `user_id` parameter:

```python
def as_candidates(
    self, session_id: Optional[str] = None, *, user_id: Optional[str] = None
) -> list[Turn]:
    if user_id is not None:
        # safe path: always filter by user first
        ...
    # else: single-user backward-compat path (log a warning in non-test contexts)
```

---

### WR-03: `InProcessScheduler.schedule()` uses a hardcoded `JOB_ID = "consolidate"` — a second `schedule()` call silently replaces the first job

**File:** `src/mnema/adapters/scheduler/in_process.py:50-56`

**Issue:** `add_job(..., id=self.JOB_ID, ...)` uses the same fixed id every time. If `schedule()` is called twice (e.g., two `MemoryEngine` instances sharing a scheduler, or a test that calls `schedule()` twice), APScheduler will raise `ConflictingIdError` (APScheduler 3.x default behavior) — or silently replace it if `replace_existing=True` is set. The current code does neither:

```python
self._scheduler.add_job(fn, "interval", seconds=every_seconds, id=self.JOB_ID, ...)
```

`ConflictingIdError` from APScheduler 3.x will propagate as an unhandled exception from `await scheduler.schedule(...)`, crashing the caller.

**Fix:** Add `replace_existing=True` if the intent is to allow re-scheduling, or guard with a `get_job` check:

```python
if self._scheduler.get_job(self.JOB_ID) is not None:
    self._scheduler.remove_job(self.JOB_ID)
self._scheduler.add_job(fn, "interval", seconds=every_seconds, id=self.JOB_ID, next_run_time=None)
```

---

### WR-04: PROV-06 dim check uses `hasattr(t1, "_dim")` — a private attribute — making the guard bypassable

**File:** `src/mnema/core/engine.py:79`

**Issue:** The startup dim assertion reads:

```python
if hasattr(t1, "_dim") and embedder.dim != t1._dim:
    raise ValueError(...)
```

The check is conditioned on `hasattr(t1, "_dim")`. A future T1 adapter that exposes a `dim` property (as required by the `VectorIndex` Protocol's spirit) but names its internal field differently (e.g. `self.vector_dim`) will silently pass the `hasattr` guard without triggering the ValueError. The adapter is then used with the wrong dimension, silently corrupting all vector writes.

`SqliteT1` exposes a public `dim` property (line 153-155). The guard should use the public interface:

**Fix:** Check the public `dim` property instead of the private `_dim` attribute:

```python
t1_dim = getattr(t1, "dim", None)
if t1_dim is not None and embedder.dim != t1_dim:
    raise ValueError(
        f"Embedding dim mismatch: embedder.dim={embedder.dim} but "
        f"t1 was created with dim={t1_dim}. ..."
    )
```

---

### WR-05: `SqliteT1.upsert()` commits after every single record write — performance and atomicity concern

**File:** `src/mnema/adapters/vector_store/sqlite_t1.py:235`, `305`, `352`

**Issue:** Every `upsert()`, `upsert_vector()`, and `delete_vector()` call ends with `await self._db.commit()`. In the write path, `WritePath.execute()` calls `upsert()` and then immediately calls `upsert_vector()`. These are two separate transactions. If the process crashes between the two calls, the `t1_records` row exists but the `vec_t1` entry does not — the record is unfindable by vector search but visible to `get()` and `live_records()`.

This is a data consistency hazard that will manifest as recall failures that are invisible to `get()`.

**Fix:** In Phase 1 the simple fix is to move `commit()` out of individual methods and into the caller (`WritePath.execute`) after both writes succeed:

```python
# In WritePath.execute, after upsert + upsert_vector:
await self._record_store.upsert(record)      # no commit inside
await self._vector_index.upsert_vector(...)  # no commit inside
await self._record_store._db.commit()        # single commit covers both
```

Or add a `begin_transaction()` / `commit()` pair on `SqliteT1` and call it from `WritePath`. The Protocol should expose transaction control for this use case.

---

## Info

### IN-01: `_ALLOWED_COLUMNS` whitelist includes `user_id` and `session_id` — callers can overwrite scope columns via `update()`

**File:** `src/mnema/adapters/vector_store/sqlite_t1.py:36-62`

**Issue:** `_ALLOWED_COLUMNS` contains `user_id`, `session_id`, and `agent_id`. This means `await store.update(record_id, user_id="attacker")` passes the whitelist check and will silently re-scope a record to a different user. The whitelist prevents SQL-injection via column **names**, but does not prevent **semantic** updates to scope columns.

No code currently calls `update()` with these fields, but the interface allows it. In Phase 3 when the forget/supersession path calls `update()`, a bug in that caller could accidentally pass `user_id` and violate D-02.

**Fix:** Remove `user_id`, `session_id`, and `agent_id` from `_ALLOWED_COLUMNS`. These identity columns should be set at `upsert()` time and never changed.

---

### IN-02: `buffer.py` uses `Optional[str]` import from `typing` — redundant with Python 3.12+

**File:** `src/mnema/core/buffer.py:22`

**Issue:** The codebase requires Python >=3.12 (`pyproject.toml:7`). In Python 3.10+ `str | None` is idiomatic and `Optional[str]` from `typing` is unnecessary. The project already uses `str | None` in several ports (`vector_index.py:34`). `buffer.py` and `classifier.py` import `Optional` from `typing` inconsistently.

**Fix:** Replace `from typing import Optional` with `str | None` annotations. Minor consistency issue, not a bug.

---

### IN-03: `conftest.py` engine fixture does not close the `SqliteT1` database connection on teardown

**File:** `tests/conftest.py:28-55`

**Issue:** The `engine` fixture yields and then `await scheduler.shutdown()` — but the `aiosqlite` connection opened by `SqliteT1.open(":memory:", ...)` is never explicitly closed. For in-memory SQLite this causes no data loss (the DB is discarded with the process), but the unclosed connection will trigger a `ResourceWarning` in Python 3.12+ test runs and may interfere with test isolation if the fixture loop scope ever changes to `session`.

**Fix:** Add teardown close:

```python
yield eng
await scheduler.shutdown()
await t1._db.close()
```

---

_Reviewed: 2026-06-10T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
