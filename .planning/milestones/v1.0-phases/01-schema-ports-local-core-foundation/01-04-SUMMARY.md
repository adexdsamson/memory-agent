---
phase: 01-schema-ports-local-core-foundation
plan: "04"
subsystem: core
tags: [python, memory-engine, classifier, buffer, write-path, recall-path, sqlite-vec, pydantic]

# Dependency graph
requires:
  - phase: 01-schema-ports-local-core-foundation
    plan: "02"
    provides: schema, ports, SqliteT1 adapter, StubEmbedder, LocalFS
  - phase: 01-schema-ports-local-core-foundation
    plan: "03"
    provides: InProcessScheduler adapter

provides:
  - "MemoryEngine: 5-verb async engine (remember/recall/expand/forget/consolidate)"
  - "ScopedHandle: ergonomic front door binding user_id for SDK consumers"
  - "WritePath: fast online write — T0 append + buffer push + provisional T1 + staging queue"
  - "RecallPath: dense KNN + buffer union + access-count update"
  - "RecentSessionBuffer: per-(user_id, session_id) bounded deque, D-02 user-scoped"
  - "looks_like_durable_claim(): pure-logic heuristic classifier (first-person stative + question/modal suppression)"
  - "from mnema import MemoryEngine, ScopedHandle — public SDK surface"

affects:
  - phase-02-consolidation-supersession (consumes staging queue, WritePath provisional flag)
  - phase-03-forgetting-decay (consumes forget() stub, access_count reinforcement signal)
  - phase-04-mcp-server (consumes MemoryEngine via MCP tool wrappers)
  - demo-nutrition-coach (consumes ScopedHandle as primary entry point)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Core modules import ONLY from mnema.ports.* and mnema.core.* — no adapter imports in core"
    - "WritePath: one embed() call on write, NO LLM call (WRITE-03 invariant)"
    - "Buffer keyed by (user_id, session_id) — user isolation without DB access"
    - "MemoryEngine constructor raises ValueError on dim mismatch (PROV-06 startup assertion)"
    - "T1 adapter satisfies RecordStore + VectorIndex structurally (Any param, runtime duck-typed)"
    - "consolidate() uses asyncio.iscoroutine() to handle both sync and async scheduler implementations"

key-files:
  created:
    - src/mnema/core/classifier.py
    - src/mnema/core/buffer.py
    - src/mnema/core/write_path.py
    - src/mnema/core/recall.py
    - src/mnema/core/engine.py
  modified:
    - src/mnema/__init__.py
    - src/mnema/adapters/vector_store/sqlite_t1.py

key-decisions:
  - "buffer.push() takes (user_id, session_id) key — D-02 user isolation at buffer layer without DB"
  - "recall.py: T1 records returned first, buffer-synthesized records appended (provenance order)"
  - "engine.py: t1 typed as Any with runtime duck-typing — Python cannot express RecordStore & VectorIndex intersection"
  - "consolidate() wraps trigger_now() with asyncio.iscoroutine() check — supports both sync Scheduler Protocol and async InProcessScheduler"
  - "forget() and consolidate() are intentional stubs per plan (Phase 3 / Phase 2 scope)"

patterns-established:
  - "TYPE_CHECKING import guard for port interfaces in core modules (no circular deps)"
  - "looks_like_durable_claim: durable kwarg > type_hint override > question > modal > first-person stative"
  - "WritePath._is_safety_claim: protected=True when type_hint=='fact' AND safety keyword present"
  - "RecallPath: _turn_to_record() synthesizes provisional MemoryRecord from buffer Turn for uniform result type"
  - "engine.scope(user_id) factory pattern for ScopedHandle — binds user_id, delegates to engine"

requirements-completed:
  - WRITE-01
  - WRITE-02
  - WRITE-03
  - WRITE-04
  - RECALL-01
  - RECALL-02
  - RECALL-06
  - RECALL-07
  - TIER-04
  - IFACE-01

# Metrics
duration: 19min
completed: 2026-06-10
---

# Phase 01 Plan 04: Core Engine Assembly Summary

**MemoryEngine with 5 async verbs, ScopedHandle ergonomic front door, and full remember→recall round-trip working over SQLite+sqlite-vec with user-scoped in-memory session buffer**

## Performance

- **Duration:** 19 min
- **Started:** 2026-06-10T13:22:13Z
- **Completed:** 2026-06-10T13:41:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- All 10 tests pass: 5-scenario remember/recall harness, write-path tests, SDK interface test, and provider dim-mismatch test
- Fast write path: T0 append + buffer push + single embed() call + provisional T1 write — no LLM on write path (WRITE-03)
- Classifier correctly identifies durable claims (first-person stative), suppresses questions and modal/hypotheticals
- Cross-session recall works via provisional T1 + within-session freshness via buffer (D-02 isolated by user_id)
- Pyright strict exits 0 on entire src/mnema/ tree

## Task Commits

1. **Task 1: Core pure-logic modules** — `edcf7f7` (feat): classifier, buffer, write-path, recall-path
2. **Task 2: MemoryEngine, ScopedHandle, SDK re-export** — `100d0c8` (feat): engine + __init__ + Rule 1 fix in sqlite_t1

## Files Created/Modified

- `src/mnema/core/classifier.py` — looks_like_durable_claim() pure logic, 3 compiled regexes, no I/O
- `src/mnema/core/buffer.py` — RecentSessionBuffer per-(user_id, session_id) bounded deque
- `src/mnema/core/write_path.py` — WritePath: T0 append + buffer + optional provisional T1 (ONE embed call)
- `src/mnema/core/recall.py` — RecallPath: dense KNN + buffer union + access-count update
- `src/mnema/core/engine.py` — MemoryEngine (5 verbs + PROV-06 dim assertion) + ScopedHandle
- `src/mnema/__init__.py` — re-exports MemoryEngine and ScopedHandle as public SDK surface
- `src/mnema/adapters/vector_store/sqlite_t1.py` — Rule 1 fix: vector_search uses cursor with row_factory=None

## Decisions Made

- Buffer uses `(user_id, session_id)` composite key so user isolation is enforced without any DB query — simpler than passing user_id through to every buffer operation at recall time
- `t1` parameter in MemoryEngine typed as `Any` — Python structural typing cannot express `RecordStore & VectorIndex` intersection without a combined Protocol; using Any avoids forcing SqliteT1 to inherit from a composed Protocol class
- `consolidate()` uses `asyncio.iscoroutine()` to detect async vs sync `trigger_now()` — the Scheduler Protocol is sync but InProcessScheduler is async; this bridges the gap without changing the Protocol or the adapter
- `forget()` is an explicit stub (pass) per plan — Phase 3 scope
- WritePath sets `protected=True` when `type_hint=="fact"` AND safety keywords detected — D-05 bias toward recall on safety claims

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed row_factory collision in sqlite_t1.vector_search**
- **Found during:** Task 2 (test_remember_and_recall_scoped failing)
- **Issue:** `db.row_factory = _make_record` was set on the connection in SqliteT1.open(), which caused `execute_fetchall()` in vector_search to pass the 2-column `(record_id, distance)` vec_t1 rows through `_make_record`, which expected all MemoryRecord columns — raising a Pydantic ValidationError on every recall call
- **Fix:** Changed `vector_search` to use `cursor = await self._db.execute(sql, params)` then `cursor.row_factory = None` before `await cursor.fetchall()` — bypasses the connection-level row factory for this specific query
- **Files modified:** `src/mnema/adapters/vector_store/sqlite_t1.py`
- **Verification:** All 10 tests pass including cross-session recall
- **Committed in:** `100d0c8` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Fix was necessary for any recall to work. No scope creep.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `forget()` returns None (no-op) | `src/mnema/core/engine.py` | Phase 3 scope — eviction/decay path not yet built |
| `consolidate()` only fires scheduler | `src/mnema/core/engine.py` | Phase 2 scope — staging queue drain + batch extract not yet built |

These stubs do not prevent the plan's goal: the remember→recall round-trip is complete and all 10 tests pass.

## Issues Encountered

- `uv run pytest` vs `uv run --with pytest pytest` — pytest is in `[project.optional-dependencies]` dev group; needed `uv pip install pytest pytest-asyncio` to run tests in this environment
- pyright needed installation via `uv pip install pyright`

## Next Phase Readiness

- The end-to-end slice is GREEN: remember → T0/buffer/T1 → recall → MemoryRecord with access_count works
- Phase 2 (consolidation) can consume: staging queue (`engine._staging`), provisional flag on T1 records, RecordType system
- Phase 3 (forgetting) can consume: access_count/last_accessed reinforcement signal, protected flag, forget() stub
- Phase 4 (MCP server) can consume: `from mnema import MemoryEngine, ScopedHandle` public surface

## Threat Flags

No new threat surface introduced. T-1-10 (expand scope check), T-1-11 (no LLM on write path), and T-1-12 (non-defaulted user_id) are all mitigated as specified.

---
*Phase: 01-schema-ports-local-core-foundation*
*Completed: 2026-06-10*

## Self-Check: PASSED

Files verified:
- FOUND: src/mnema/core/classifier.py
- FOUND: src/mnema/core/buffer.py
- FOUND: src/mnema/core/write_path.py
- FOUND: src/mnema/core/recall.py
- FOUND: src/mnema/core/engine.py
- FOUND: src/mnema/__init__.py

Commits verified:
- FOUND: edcf7f7 (task 1 — classifier, buffer, write-path, recall-path)
- FOUND: 100d0c8 (task 2 — engine, __init__, sqlite_t1 fix)

Tests: 10 passed, 0 failed
Pyright: 0 errors, 0 warnings
