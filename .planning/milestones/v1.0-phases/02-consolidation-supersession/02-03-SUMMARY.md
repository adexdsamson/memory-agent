---
phase: 02-consolidation-supersession
plan: "03"
subsystem: record-store
tags: [protocol-extension, atomic-transaction, idempotency, sqlite-t1]
dependency_graph:
  requires:
    - 02-01  # walking skeleton — StubLLM + test stubs established
  provides:
    - supersede()  # atomic contradiction resolution (CONS-04)
    - find_by_t0_ref()  # idempotency fence (CONS-06/07)
  affects:
    - 02-04  # ConsolidationPipeline depends on both new methods via RecordStore Protocol
tech_stack:
  added: []
  patterns:
    - "module-level _INSERT_SQL + _record_params() extraction (single source of INSERT truth)"
    - "try/except rollback/raise pattern for multi-statement aiosqlite transactions"
    - "AND user_id=? predicate on all T1 writes for hard user isolation (T-02-05)"
key_files:
  created: []
  modified:
    - src/mnema/ports/record_store.py
    - src/mnema/adapters/vector_store/sqlite_t1.py
decisions:
  - "supersede() UPDATE includes AND user_id=? predicate (not just id=?) per threat model T-02-05; if old_id belongs to a different user, 0 rows are updated and no partial write occurs"
  - "WR-01 fixed opportunistically during Task 2: get_latest() now adds AND valid_until IS NULL so superseded records are excluded from the 'latest record' convenience query"
  - "_record_params() extracted as module-level function (not private method) so it is accessible to any future adapters sharing the same schema serialization pattern"
metrics:
  duration: "~18 minutes"
  completed: "2026-06-13"
  tasks_completed: 3
  files_modified: 2
---

# Phase 02 Plan 03: RecordStore Protocol Extension + SqliteT1 supersede()/find_by_t0_ref() Summary

**One-liner:** Atomic supersession transaction (valid_until+superseded_by+vector in one SQLite commit) and t0_ref idempotency lookup added to RecordStore Protocol and SqliteT1, gated by mandatory user_id predicates.

## What Was Built

### Task 0: RecordStore Protocol extended

`src/mnema/ports/record_store.py` now declares two new method stubs:

- `supersede(old_id, new_record, embedding)` — documents the atomic contract, user_id scoping, and CONS-04 usage
- `find_by_t0_ref(t0_ref, user_id)` — documents the valid_until IS NULL contract and CONS-06/07 idempotency purpose

ConsolidationPipeline (Plan 04) can call both methods through the Protocol without importing SqliteT1 at runtime (structural subtyping — D-08).

### Task 1: _INSERT_SQL + _record_params() extracted; supersede() added

`upsert()` was refactored to delegate to `_INSERT_SQL` (module-level constant) and `_record_params()` (module-level function). The observable behaviour of `upsert()` is unchanged — same SQL, same parameter serialization.

`supersede(old_id, new_record, embedding)` wraps three statements in a single aiosqlite transaction:
1. `UPDATE t1_records SET valid_until=?, superseded_by=? WHERE id=? AND user_id=?` — retires the old record with user_id scope guard (T-02-05)
2. `INSERT OR REPLACE` via `_INSERT_SQL` + `_record_params(new_record)` — inserts new record
3. `INSERT OR REPLACE INTO vec_t1` using `_v32(embedding)` — inserts new vector

On any exception: `await self._db.rollback(); raise` (T-02-06). Commit only on full success.

### Task 2: find_by_t0_ref() added; WR-01 fixed

`find_by_t0_ref(t0_ref, user_id)` placed after `get()`, before `update()`. Query:
```sql
SELECT * FROM t1_records WHERE t0_ref = ? AND user_id = ? AND valid_until IS NULL
```
Returns the live provisional record or None. fetchone() pattern mirrors `get()` exactly.

WR-01 (Phase 1 deferred code review): `get_latest()` query updated to include `AND valid_until IS NULL` — superseded records are now excluded from the "most recently created live record" convenience method.

## Verification Results

| Check | Result |
|-------|--------|
| `pyright src/mnema/ports/record_store.py` | 0 errors |
| `pyright src/mnema/adapters/vector_store/` | 0 errors |
| 23 Phase 1 tests (post upsert refactor) | 23 passed |
| supersede() atomicity smoke test | PASSED |
| find_by_t0_ref() smoke test (None + found + cross-user None) | PASSED |

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 0: Protocol extension | `4d9dd7b` | `src/mnema/ports/record_store.py` |
| Task 1: supersede() + helpers | `f8cdbf6` | `src/mnema/adapters/vector_store/sqlite_t1.py` |
| Task 2: find_by_t0_ref() + WR-01 | `ecd738e` | `src/mnema/adapters/vector_store/sqlite_t1.py` |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] WR-01: get_latest() missing valid_until IS NULL filter**

- **Found during:** Task 2 — the plan explicitly requests this fix as part of Task 2's action
- **Issue:** `get_latest()` queried all records for a user ordered by `created_at DESC LIMIT 1` without filtering out superseded records (valid_until IS NOT NULL). After supersession is in use, this method would return a retired record as the "latest" if it was created most recently before being superseded.
- **Fix:** Added `AND valid_until IS NULL` to `get_latest()`'s WHERE clause
- **Files modified:** `src/mnema/adapters/vector_store/sqlite_t1.py`
- **Commit:** `ecd738e`

### Plan deviations (non-issue)

The smoke test in the plan used `SqliteT1(str(tmp), embedding_dim=4)` (direct constructor). The actual API is `SqliteT1.open(path, dim=...)` (classmethod that opens the connection). Smoke tests were adapted accordingly — this is consistent with how conftest.py uses the API.

## Known Stubs

None — both methods are fully implemented with real SQL queries and real transaction logic.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes were introduced. The two new methods operate on existing columns (`valid_until`, `superseded_by`, `t0_ref`) already in the DDL.

## Self-Check: PASSED

All key files exist and all task commits are present in git history.

| Check | Result |
|-------|--------|
| `src/mnema/ports/record_store.py` exists | FOUND |
| `src/mnema/adapters/vector_store/sqlite_t1.py` exists | FOUND |
| `02-03-SUMMARY.md` exists | FOUND |
| Commit `4d9dd7b` (Task 0) | FOUND |
| Commit `f8cdbf6` (Task 1) | FOUND |
| Commit `ecd738e` (Task 2) | FOUND |
