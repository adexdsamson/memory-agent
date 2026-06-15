---
phase: 01-schema-ports-local-core-foundation
plan: "03"
subsystem: testing

tags: [python, apscheduler, asyncio, embedding, stub, scheduler, pytest, pyright, hashlib]

# Dependency graph
requires:
  - phase: 01-schema-ports-local-core-foundation
    plan: "01"
    provides: "RED test stubs (test_scheduler.py, test_providers.py), pyproject.toml with apscheduler>=3.11,<4"

provides:
  - StubEmbedder: deterministic SHA-256 hash-based L2-normalized unit-vector provider (no API, no numpy)
  - InProcessScheduler: APScheduler 3.x AsyncIOScheduler with async start/schedule/trigger_now/shutdown
  - src/mnema/adapters/ package structure with __init__.py markers

affects:
  - 01-04-PLAN.md (MemoryEngine constructor takes embedder: EmbeddingProvider and scheduler: Scheduler — both structurally satisfied by these adapters)
  - 01-05-PLAN.md (full harness gate — test_scheduler.py now GREEN; test_providers.py stays RED until MemoryEngine + SqliteT1 land in Plan 04)
  - conftest.py engine fixture (InProcessScheduler + StubEmbedder are the concrete types composed into the fixture)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Structural Protocol satisfaction (no superclass): both adapters satisfy their Protocol via duck-typing; pyright strict confirms compatibility at zero runtime overhead"
    - "Async-first adapters: start/schedule/trigger_now/shutdown are all async def even though APScheduler 3.x internals are sync — matches D-11 async-first contract"
    - "type: ignore on untyped third-party calls: APScheduler 3.x ships no type stubs; targeted # type: ignore[no-untyped-call] on specific call sites keeps pyright strict clean without disabling the whole file"
    - "next_run_time=None on add_job: prevents immediate first-fire; trigger_now() uses datetime.now() (local time) for APScheduler 3.x compatibility"
    - "Stdlib-only StubEmbedder: hashlib + math only — zero external dependency, deterministic, portable to any CI environment"

key-files:
  created:
    - src/mnema/adapters/__init__.py (adapters package marker)
    - src/mnema/adapters/embedding/__init__.py (embedding sub-package marker)
    - src/mnema/adapters/embedding/stub.py (StubEmbedder: dim property + async embed, SHA-256 deterministic unit vectors)
    - src/mnema/adapters/scheduler/__init__.py (scheduler sub-package marker)
    - src/mnema/adapters/scheduler/in_process.py (InProcessScheduler: async APScheduler 3.x wrapper)
  modified: []

key-decisions:
  - "Async wrappers over sync APScheduler 3.x: test_scheduler.py uses await scheduler.start() / await scheduler.schedule() / await scheduler.trigger_now() / await scheduler.shutdown() — all methods must be async def even though AsyncIOScheduler internals are synchronous. The async shell is a zero-cost Protocol contract that matches the D-11 async-first design."
  - "type: ignore[no-untyped-call] on APScheduler 3.x calls: apscheduler 3.x ships no py.typed or stubs; targeted suppression keeps pyright strict clean without losing type safety on our own code."
  - "StubEmbedder uses stdlib hashlib + math only: no numpy dependency prevents any import-order or platform issues in hermetic CI; the SHA-256 cycling pattern is deterministic across Python versions and OS."

patterns-established:
  - "Async Protocol adapter pattern: wrap sync third-party scheduler (APScheduler 3.x) with async def methods that call sync internals directly — no asyncio.to_thread needed because APScheduler AsyncIOScheduler manages its own event loop integration"
  - "Hash-cycling embedding for tests: SHA-256 → 32-byte digest → cycle bytes to fill dim-length vector → L2-normalize; produces distinct, stable unit vectors for any text input without API calls"

requirements-completed:
  - PROV-02
  - PROV-06
  - SCHED-01
  - SCHED-02

# Metrics
duration: 20min
completed: 2026-06-10
---

# Phase 1 Plan 03: StubEmbedder + InProcessScheduler Summary

**StubEmbedder (SHA-256 hash-cycling, L2-normalized, stdlib-only) and InProcessScheduler (APScheduler 3.x AsyncIOScheduler with async Protocol wrappers and trigger_now() support) — both pyright strict-clean and test_scheduler.py GREEN**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-10T14:00:00Z
- **Completed:** 2026-06-10T14:20:00Z
- **Tasks:** 2
- **Files created:** 5

## Accomplishments

- Implemented `StubEmbedder` with deterministic SHA-256 hash-cycling: identical input always produces the same L2-normalized unit vector, distinct inputs produce distinguishable vectors, no API calls, no numpy dependency.
- Implemented `InProcessScheduler` as an async wrapper over APScheduler 3.x `AsyncIOScheduler`: `trigger_now()` fires scheduled jobs within 200ms via `job.modify(next_run_time=datetime.now())`.
- Both adapters are pyright strict-clean (0 errors, 0 warnings) with targeted `# type: ignore` only on untyped APScheduler 3.x call sites.
- `test_scheduler.py` is GREEN (1 passed).

## Task Commits

Each task was committed atomically:

1. **Task 1: StubEmbedder — deterministic hash-based embedding provider** - `3c236bb` (feat)
2. **Task 2: InProcessScheduler — APScheduler 3.x async scheduler adapter** - `47082bc` (feat)

**Plan metadata:** (committed with SUMMARY below)

## Files Created/Modified

- `src/mnema/adapters/__init__.py` — adapters package marker (empty)
- `src/mnema/adapters/embedding/__init__.py` — embedding sub-package marker (empty)
- `src/mnema/adapters/embedding/stub.py` — StubEmbedder: async embed() with SHA-256 hash-cycling and L2 normalization, version class attr, no numpy
- `src/mnema/adapters/scheduler/__init__.py` — scheduler sub-package marker (empty)
- `src/mnema/adapters/scheduler/in_process.py` — InProcessScheduler: async wrappers over APScheduler 3.x AsyncIOScheduler, JOB_ID constant, trigger_now() via job.modify()

## Decisions Made

- **Async methods on InProcessScheduler:** The test file (`test_scheduler.py`) uses `await scheduler.start()`, `await scheduler.schedule(...)`, `await scheduler.trigger_now()`, and `await scheduler.shutdown()`. The plan's interface spec showed these as sync, but the canonical test file takes precedence. Implementing as `async def` (wrapping sync APScheduler calls) satisfies both the tests and the D-11 async-first design decision.
- **type: ignore[no-untyped-call] for APScheduler 3.x:** APScheduler 3.x has no type stubs. Targeted suppression on `add_job`, `get_job`, and `job.modify` call sites keeps pyright strict clean without affecting type safety on MNEMA's own code.
- **StubEmbedder stdlib-only:** Using only `hashlib` and `math` from stdlib ensures the stub is a zero-external-dependency test helper, preventing any platform-specific import failures in CI.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Scheduler methods made async to match test signatures**
- **Found during:** Task 2 (InProcessScheduler implementation)
- **Issue:** The plan's interface spec listed `schedule()`, `trigger_now()`, `start()`, `shutdown()` as sync `def`. The actual test file (`test_scheduler.py`) and conftest.py use `await scheduler.start()`, `await scheduler.schedule(...)`, `await scheduler.trigger_now()`, `await scheduler.shutdown()`. Implementing as sync would cause `TypeError: object NoneType cannot be awaited` at test runtime.
- **Fix:** Implemented all four methods as `async def` with synchronous APScheduler 3.x calls inside — zero functional change, matches the test contract.
- **Files modified:** src/mnema/adapters/scheduler/in_process.py
- **Verification:** `uv run pytest tests/test_scheduler.py -x -q` passes (1 passed)
- **Committed in:** 47082bc (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — async/sync contract mismatch between plan spec and test file)
**Impact on plan:** Required for test_scheduler.py to pass GREEN. No scope change. Consistent with D-11 async-first design.

## Issues Encountered

- APScheduler 3.x (`apscheduler==3.11.2`) ships no type stubs (`py.typed` absent, no bundled `.pyi` files). Pyright strict mode reported 4 "partially unknown member type" errors on `add_job`, `get_job`, and `job.modify`. Resolved with targeted `# type: ignore[no-untyped-call]` on three lines; all other code remains strictly typed.

## User Setup Required

None — no external services, no environment variables required.

## Next Phase Readiness

- Both `StubEmbedder` and `InProcessScheduler` are ready for use as constructor arguments to `MemoryEngine` (Plan 04).
- `test_scheduler.py` is GREEN; `test_providers.py` remains RED (requires `MemoryEngine` from Plan 04 and `SqliteT1` from Plan 02).
- The `src/mnema/adapters/` package tree is initialized and ready to receive Plan 02's `vector_store/` and `object_store/` sub-packages.

## Threat Surface Scan

No new security-relevant surface introduced. Both adapters are purely local/in-process with no network endpoints, no auth paths, no file access patterns (StubEmbedder is pure computation; InProcessScheduler fires in-process callables only). No additions to the threat model required.

## Known Stubs

None — both adapters are fully functional implementations, not placeholders.

---
*Phase: 01-schema-ports-local-core-foundation*
*Completed: 2026-06-10*
