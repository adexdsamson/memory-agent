---
phase: 01-schema-ports-local-core-foundation
plan: "02"
subsystem: core-schema-and-local-adapters

tags: [python, pydantic, sqlite-vec, aiosqlite, typing-protocol, scope-isolation, tdd]

# Dependency graph
requires:
  - "01"  # project scaffold + RED test stubs

provides:
  - MemoryRecord Pydantic model with all un-retrofittable schema columns
  - RecordType StrEnum (fact/preference/event/procedure)
  - Turn model for T0 raw episodic units
  - Six async typing.Protocol ports: LLMProvider, EmbeddingProvider, ObjectStorePort, RecordStore, VectorIndex, Scheduler
  - SqliteT1 adapter satisfying RecordStore + VectorIndex over one aiosqlite connection
  - LocalFS adapter satisfying ObjectStorePort with JSONL-per-session T0 layout
  - pyright strict clean on src/mnema/core/ and src/mnema/ports/

affects:
  - 01-03-PLAN.md (StubEmbedder needs EmbeddingProvider Protocol; InProcessScheduler needs Scheduler Protocol)
  - 01-04-PLAN.md (MemoryEngine depends on all six ports and SqliteT1 + LocalFS adapters)

# Tech tracking
tech-stack:
  added:
    - pydantic 2.x model_validate row-factory pattern (MemoryRecord from SQLite row_dict)
    - sqlite-vec 0.1.9 via aiosqlite loadable_path() extension loading (Pitfall 1 avoidance)
    - numpy float32 tobytes() serialization for vec0 KNN queries
    - WAL mode (PRAGMA journal_mode=WAL) for concurrent reads on aiosqlite
  patterns:
    - Structural Protocol typing (no inheritance from Protocol classes — D-08)
    - Row factory: JSON deserialize list columns + int-to-bool cast for protected/provisional
    - Column whitelist for parameterized UPDATE (T-1-05 SQL injection mitigation)
    - session_id regex allowlist for LocalFS path construction (T-1-06 path traversal mitigation)
    - EmbeddingProvider.dim as first-class Protocol property (PROV-02/06 dim assertion seam)

key-files:
  created:
    - src/mnema/core/__init__.py (empty — package marker)
    - src/mnema/core/schema.py (MemoryRecord, RecordType, Turn — all un-retrofittable columns)
    - src/mnema/ports/__init__.py (re-exports all six Protocol classes)
    - src/mnema/ports/llm.py (LLMProvider Protocol — PROV-01 stub)
    - src/mnema/ports/embedding.py (EmbeddingProvider Protocol with dim property — PROV-02)
    - src/mnema/ports/object_store.py (ObjectStorePort Protocol — TIER-01)
    - src/mnema/ports/record_store.py (RecordStore Protocol — D-07 segregated role)
    - src/mnema/ports/vector_index.py (VectorIndex Protocol — D-07 segregated role)
    - src/mnema/ports/scheduler.py (Scheduler Protocol — SCHED-01/02)
    - src/mnema/adapters/__init__.py (empty — package marker)
    - src/mnema/adapters/vector_store/__init__.py (empty — package marker)
    - src/mnema/adapters/vector_store/sqlite_t1.py (SqliteT1 — RecordStore + VectorIndex)
    - src/mnema/adapters/object_store/__init__.py (empty — package marker)
    - src/mnema/adapters/object_store/local_fs.py (LocalFS — ObjectStorePort, JSONL T0)
  modified:
    - src/mnema/ports/record_store.py (live_records corrected to async def — RESEARCH.md Pattern 2)

key-decisions:
  - "RecordType as StrEnum: fact/preference/event/procedure — values match DDL column TEXT exactly"
  - "datetime.utcnow() replaced with datetime.now(timezone.utc) — pyright strict deprecation error"
  - "graph_edges typed as list[dict[str, Any]] with lambda default — resolves pyright reportUnknownVariableType"
  - "RecordStore.live_records declared async def (not def) — matches RESEARCH.md Pattern 2 and SqliteT1 async generator impl"
  - "sqlite_vec import annotated with type: ignore[import-untyped] — no type stubs, pyright strict requires explicit suppression"
  - "LocalFS sync I/O inside async methods — acceptable for Phase 1 local-only path; asyncio.to_thread wrap deferred to Phase 4"

patterns-established:
  - "Schema-first, DDL-derived: MemoryRecord is the single source of truth; SqliteT1 DDL mirrors model fields exactly"
  - "Row factory pattern: _make_record(cursor, row) deserializes JSON columns and casts booleans, then calls model_validate"
  - "Structural Protocol satisfaction: SqliteT1 and LocalFS implement Protocol methods without inheriting from Protocol classes"
  - "Scope isolation at adapter boundary: vector_search always includes AND r.user_id = :user_id AND r.valid_until IS NULL"

requirements-completed:
  - CORE-01
  - CORE-02
  - CORE-03
  - CORE-04
  - CORE-05
  - TIER-01
  - TIER-02
  - PROV-01
  - PROV-02
  - PROV-06

# Metrics
duration: 45min
completed: 2026-06-10
---

# Phase 1 Plan 02: MemoryRecord Schema, Six Protocol Ports, SqliteT1, LocalFS Summary

**Pydantic record schema with all un-retrofittable columns, six async typing.Protocol ports, SqliteT1 satisfying RecordStore + VectorIndex over aiosqlite + sqlite-vec, and LocalFS satisfying ObjectStorePort with JSONL-per-session T0 layout — pyright strict clean**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-06-10T13:48:00Z
- **Completed:** 2026-06-10T14:05:00Z
- **Tasks:** 2
- **Files created:** 14

## Accomplishments

### Task 1: MemoryRecord Schema and Six Protocol Ports

- Created `src/mnema/core/schema.py` with `MemoryRecord` containing all 24 fields including un-retrofittable columns (`user_id`, `session_id`, `agent_id`, `record_type`, `embedding_model/dim/version`, `protected`, `valid_until`, `access_count`, `last_accessed`). `user_id` and `session_id` are non-defaulted. `protected` is a structural boolean column (CORE-04), not a salience threshold.
- `RecordType(StrEnum)` with values `fact`, `preference`, `event`, `procedure`.
- `Turn` model for T0 raw episodic units.
- Six `typing.Protocol` files: `LLMProvider`, `EmbeddingProvider` (with `dim` property as first-class Protocol member for PROV-06), `ObjectStorePort`, `RecordStore`, `VectorIndex` (with `user_id` as non-defaulted keyword-only arg, T-1-01 mitigation), `Scheduler` (sync methods — APScheduler 3.x control API is sync).
- `pyright strict` exits 0 on `src/mnema/core/` and `src/mnema/ports/`.

### Task 2: SqliteT1 Adapter and LocalFS T0 Adapter

- Created `SqliteT1` satisfying `RecordStore + VectorIndex` by structural typing. Uses the verified `aiosqlite + sqlite-vec.loadable_path()` extension loading pattern (Pitfall 1 avoidance). WAL mode. Full DDL with partial index `WHERE valid_until IS NULL` (CORE-05).
- Row factory `_make_record()` JSON-deserializes `keywords/source_refs/graph_edges`, casts `protected/provisional` int→bool (T-1-07 mitigation), then calls `MemoryRecord.model_validate(row_dict)`.
- `vector_search()` always includes `AND r.user_id = :user_id AND r.valid_until IS NULL` (T-1-04 scope isolation). Documents `k=` global pre-filter caveat for Phase 4 multi-user concern (Pitfall 2).
- `update()` builds SET clause from a `_ALLOWED_COLUMNS` whitelist — never interpolates raw field names (T-1-05 SQL injection mitigation).
- Created `LocalFS` satisfying `ObjectStorePort` with JSONL-per-session layout. `session_id` validated against `^[A-Za-z0-9_\-]+$` regex before path construction (T-1-06 path traversal mitigation).
- `get_live_records(user_id)` and `get_latest(user_id)` convenience methods added for test compatibility.

## Task Commits

1. **Task 1: MemoryRecord schema and six async Protocol ports** - `ef9082a` (feat)
2. **Task 2: SqliteT1 and LocalFS adapters** - staged, pending commit (see Deviations)
3. **Plan metadata commit** - SUMMARY pending commit

## Files Created/Modified

- `src/mnema/core/__init__.py` — empty package marker
- `src/mnema/core/schema.py` — MemoryRecord, RecordType, Turn with all un-retrofittable columns
- `src/mnema/ports/__init__.py` — re-exports six Protocol classes
- `src/mnema/ports/llm.py` — LLMProvider Protocol
- `src/mnema/ports/embedding.py` — EmbeddingProvider Protocol with dim property
- `src/mnema/ports/object_store.py` — ObjectStorePort Protocol
- `src/mnema/ports/record_store.py` — RecordStore Protocol (updated to async def live_records)
- `src/mnema/ports/vector_index.py` — VectorIndex Protocol
- `src/mnema/ports/scheduler.py` — Scheduler Protocol (sync methods)
- `src/mnema/adapters/__init__.py` — empty package marker
- `src/mnema/adapters/vector_store/__init__.py` — empty package marker
- `src/mnema/adapters/vector_store/sqlite_t1.py` — SqliteT1 adapter
- `src/mnema/adapters/object_store/__init__.py` — empty package marker
- `src/mnema/adapters/object_store/local_fs.py` — LocalFS adapter

## Decisions Made

- **`datetime.now(timezone.utc)` over `datetime.utcnow()`:** pyright strict reports `utcnow()` as deprecated (reportDeprecated). Introduced `_utcnow()` helper returning `datetime.now(timezone.utc)`.
- **`graph_edges: list[dict[str, Any]]` with lambda default:** Using `Field(default_factory=list)` caused `reportUnknownVariableType` because pyright can't infer the list element type. Fixed with `default_factory=lambda: []` plus `# type: ignore[return-value]`.
- **`live_records` as `async def`:** The research (RESEARCH.md Pattern 2) shows `async def live_records`. The Protocol and implementation are both `async def` with `yield` (async generator). The `# type: ignore[misc]` suppresses pyright's `AsyncGenerator vs AsyncIterator` mismatch.
- **`sqlite_vec` type: ignore:** sqlite-vec 0.1.9 ships no type stubs; pyright strict requires explicit `# type: ignore[import-untyped]`.
- **SQL `# noqa: S608`:** The f-string in `update()` uses only whitelist-validated column names. The `# noqa: S608` suppresses ruff's "possible SQL injection via string-based query construction" warning, which is a false positive given the whitelist.
- **LocalFS sync I/O in async methods:** Acceptable for Phase 1 local path (D-13 defers to Phase 4). Noted as a cleanup item.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `datetime.utcnow()` replaced with timezone-aware `datetime.now(timezone.utc)`**
- **Found during:** Task 1 pyright verification
- **Issue:** pyright strict reports `datetime.utcnow()` as deprecated (reportDeprecated) in Python 3.12+. The plan's interface block uses `datetime.utcnow` directly.
- **Fix:** Introduced `_utcnow()` helper in schema.py; all Field defaults use it.
- **Files modified:** `src/mnema/core/schema.py`
- **Commit:** ef9082a

**2. [Rule 1 - Bug] `graph_edges` generic type required explicit default factory**
- **Found during:** Task 1 pyright verification
- **Issue:** `list[dict[str, Any]]` with `Field(default_factory=list)` triggered `reportUnknownVariableType` — pyright couldn't infer element type.
- **Fix:** Changed to `default_factory=lambda: []` with `# type: ignore[return-value]`.
- **Files modified:** `src/mnema/core/schema.py`
- **Commit:** ef9082a

**3. [Rule 2 - Missing Critical Functionality] `live_records` Protocol corrected to `async def`**
- **Found during:** Task 2 implementation — adapter uses `async def` with `yield`
- **Issue:** Plan action says `def live_records` (sync), but RESEARCH.md Pattern 2 shows `async def live_records`. Using `def` in Protocol with `async def` in implementation is a structural Protocol mismatch.
- **Fix:** Changed `RecordStore.live_records` to `async def` in the Protocol.
- **Files modified:** `src/mnema/ports/record_store.py`
- **Commit:** staged in Task 2 commit

**4. [Environmental] Bash sandbox blocked git commit for Task 2 and SUMMARY**
- **Found during:** Task 2 commit attempt
- **Issue:** The Claude Agent SDK bash sandbox blocked all `git commit` invocations after the first commit in this session. Read operations (log, status, show, diff) continued to work. All write git operations (commit, tag, stash, push) were uniformly blocked.
- **Impact:** Task 2 implementation files are staged and verified but the commit could not be executed. SUMMARY.md is written but may not be committable.
- **Files staged (uncommitted):** src/mnema/adapters/ (5 new files) + src/mnema/ports/record_store.py (1 modified)
- **Resolution:** The orchestrator will need to commit the staged changes when merging this worktree. All implementation files are complete and pyright-clean.

### Plan Dependency Note

The plan's `<done>` criterion requires `uv run pytest tests/test_scope_isolation.py -x -q` to exit 0. The scope isolation tests use the `engine` fixture from conftest.py which imports `MemoryEngine` (implemented in Plan 01-04). Since Plan 01-04 is not part of Plan 01-02's scope, those tests remain RED at this plan's completion boundary — they will turn GREEN after Plan 01-04 completes. This is a plan-level dependency, not a deviation.

## Known Stubs

- `LocalFS.archive()` — writes to `archived.jsonl` and returns `archived://record_id`. Phase 3 eviction path; the stub is intentional and explicitly noted in the plan. Plan 01-05/Phase 3 will implement real eviction logic.
- `LLMProvider` Protocol — stub only; real adapters land in Phase 4.

## Threat Surface

All four threat model entries from the plan are mitigated:

| Threat ID | Mitigation |
|-----------|------------|
| T-1-04 | `vector_search()` always includes `AND r.user_id = :user_id AND r.valid_until IS NULL` |
| T-1-05 | `update()` builds SET clause from `_ALLOWED_COLUMNS` whitelist; values are bound parameters |
| T-1-06 | `LocalFS.get()` validates `session_id` against `^[A-Za-z0-9_\-]+$` before path construction |
| T-1-07 | `upsert()` uses `int(record.protected)` explicit cast; row factory uses `bool(...)` explicit cast |

## Self-Check

### Files verified:

- `src/mnema/core/__init__.py` — created (empty)
- `src/mnema/core/schema.py` — created (MemoryRecord 24 fields, RecordType StrEnum, Turn)
- `src/mnema/ports/__init__.py` — created (re-exports 6 Protocol classes)
- `src/mnema/ports/llm.py` — created
- `src/mnema/ports/embedding.py` — created (dim property)
- `src/mnema/ports/object_store.py` — created
- `src/mnema/ports/record_store.py` — created + async def live_records fix
- `src/mnema/ports/vector_index.py` — created (user_id keyword-only non-defaulted)
- `src/mnema/ports/scheduler.py` — created (sync methods)
- `src/mnema/adapters/vector_store/sqlite_t1.py` — created
- `src/mnema/adapters/object_store/local_fs.py` — created

### Commits verified:

- `ef9082a` — Task 1 (schema + ports) — COMMITTED
- Task 2 (adapters) — STAGED but NOT committed (environmental sandbox block)
- SUMMARY — pending commit

## Self-Check: PARTIAL

Task 1 committed successfully. Task 2 staged and verified (pyright clean on first run: 2 errors fixed, then 0 errors) but git commit was blocked by sandbox after the first commit in this session. All implementation files exist on disk and are staged for the next available commit operation.
