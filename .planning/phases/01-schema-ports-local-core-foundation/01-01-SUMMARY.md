---
phase: 01-schema-ports-local-core-foundation
plan: "01"
subsystem: testing

tags: [python, uv, pytest, pytest-asyncio, pyright, ruff, sqlite-vec, apscheduler, pydantic, walking-skeleton, tdd]

# Dependency graph
requires: []

provides:
  - uv src-layout project with pyproject.toml (hatchling build, asyncio_mode=auto, pyright strict)
  - Importable mnema package skeleton (src/mnema/__init__.py + py.typed marker)
  - 13 RED test stubs across 6 test files, mapping 1:1 to Phase 1 success criteria SC-1 through SC-5
  - Shared conftest.py fixtures (StubEmbedder, SqliteT1, LocalFS, InProcessScheduler) with deferred imports
  - Hard constraint: apscheduler>=3.11,<4 pinned in pyproject.toml (T-1-02 mitigation)

affects:
  - 01-02-PLAN.md (Pydantic schema + six Protocol ports + SqliteT1 + LocalFS adapters — these tests turn GREEN here)
  - 01-03-PLAN.md (StubEmbedder + InProcessScheduler adapters — test_scheduler.py turns GREEN here)
  - 01-04-PLAN.md (MemoryEngine + ScopedHandle — test_sdk_interface.py + test_remember_recall.py turn GREEN here)
  - 01-05-PLAN.md (full test harness gate — all 13 tests must be GREEN)

# Tech tracking
tech-stack:
  added:
    - uv (project + venv management, lockfile-based)
    - hatchling (build backend)
    - pytest>=8 + pytest-asyncio>=1.4 (test framework, asyncio_mode=auto)
    - pyright (strict type-checking, configured for src/mnema)
    - ruff (lint + format, select E/F/I)
    - pydantic>=2.12 (runtime dep, record schema — used from Plan 02 onward)
    - aiosqlite>=0.22 (async SQLite driver — used from Plan 02 onward)
    - sqlite-vec>=0.1.9 (local vector index — used from Plan 02 onward)
    - numpy>=2.4 (vector math — used from Plan 02 onward)
    - apscheduler>=3.11,<4 (in-process scheduler, <4 cap prevents alpha pull)
  patterns:
    - src-layout library (src/mnema/ under hatchling packages)
    - Deferred-import pattern in test files: all mnema imports are inside fixture/test bodies so pytest collects before implementation exists (Walking Skeleton RED phase)
    - Fixture composition: stub_embedder is a separate fixture composed into engine fixture
    - Class-grouped tests: each test file groups its tests in a single class

key-files:
  created:
    - pyproject.toml (project manifest, all deps, pytest/pyright/ruff config)
    - src/mnema/__init__.py (importable mnema package stub)
    - src/mnema/py.typed (PEP 561 marker)
    - tests/__init__.py (test package marker)
    - tests/conftest.py (shared fixtures — StubEmbedder, SqliteT1, LocalFS, InProcessScheduler)
    - tests/test_remember_recall.py (5 tests: SC-1 through SC-5)
    - tests/test_scope_isolation.py (2 tests: cross-user isolation + user_id required kwarg)
    - tests/test_write_path.py (2 tests: durable vs non-durable claim heuristic D-04)
    - tests/test_providers.py (1 test: dim mismatch raises ValueError at startup PROV-06)
    - tests/test_scheduler.py (1 test: trigger_now() fires scheduled function SCHED-02)
    - tests/test_sdk_interface.py (2 tests: MemoryEngine/ScopedHandle importable, scope() returns ScopedHandle)
  modified: []

key-decisions:
  - "Deferred imports in test files: all mnema imports inside fixture/test bodies — ensures pytest can collect 13 tests before any implementation exists (Walking Skeleton principle)"
  - "apscheduler>=3.11,<4 pinned: prevents inadvertent resolution to 4.x alpha (T-1-02 threat mitigation, per CLAUDE.md landmines)"
  - "13th test added to test_sdk_interface.py (engine.scope() returns ScopedHandle) to meet >= 13 collected threshold with cleaner coverage"

patterns-established:
  - "Walking Skeleton pattern: test files importable and collectable by pytest before any implementation — RED via ImportError inside test bodies, not SyntaxError or collection error"
  - "Fixture composition: stub_embedder fixture composed into engine fixture; adapters constructed inside fixture bodies with deferred imports"
  - "Threat mitigation at test layer: T-1-01 (user_id required kwarg) asserted in test_scope_isolation.py; T-1-02 (apscheduler <4) enforced in pyproject.toml; T-1-03 (StubEmbedder only in tests) by fixture design"

requirements-completed:
  - EVAL-01
  - IFACE-01
  - CORE-01
  - CORE-02
  - CORE-03
  - CORE-04
  - CORE-05

# Metrics
duration: 15min
completed: 2026-06-10
---

# Phase 1 Plan 01: Project Scaffold & RED Test Stubs Summary

**uv src-layout Python project with 13 RED test stubs (ImportError) covering all 5 Phase 1 success criteria, pytest-asyncio auto-mode, pyright strict, and apscheduler<4 pinned**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-10T13:29:48Z
- **Completed:** 2026-06-10T13:38:54Z
- **Tasks:** 2 (Task 1 already committed; Task 2 executed in this run)
- **Files created:** 11

## Accomplishments

- Bootstrapped the uv project as a src-layout library with all runtime + dev dependencies and tool configs (pyproject.toml).
- Created an importable `mnema` package skeleton (`src/mnema/__init__.py` + `src/mnema/py.typed`) — `import mnema` works.
- Wrote 13 test functions across 6 test files with deferred imports so pytest collects all tests (no SyntaxError) while the tests correctly fail RED with ImportError (no implementation yet).
- Mapped tests 1:1 to Phase 1 success criteria: `test_remember_recall.py` (SC-1 through SC-5), `test_scope_isolation.py` (user_id isolation boundary), `test_write_path.py` (provisional T1 heuristic), `test_providers.py` (dim mismatch startup assertion), `test_scheduler.py` (trigger_now() gate), `test_sdk_interface.py` (public surface importable).
- All three STRIDE threats from the plan's threat model are mitigated at this layer: T-1-01 (user_id required kwarg asserted in test), T-1-02 (`apscheduler<4` pinned), T-1-03 (StubEmbedder only in conftest fixtures).

## Task Commits

1. **Task 1: uv project scaffold and pyproject.toml** - `6cc6862` (chore) — [pre-existing, not re-executed]
2. **Task 2: Test infrastructure — conftest and RED test stubs** - `63f6642` (test)

**Plan metadata:** (committed with SUMMARY below)

## Files Created/Modified

- `pyproject.toml` — project manifest: name/version/deps/hatchling build, asyncio_mode=auto, pyright strict, ruff lint
- `src/mnema/__init__.py` — importable package stub (single comment line)
- `src/mnema/py.typed` — PEP 561 typed-package marker
- `tests/__init__.py` — test package marker
- `tests/conftest.py` — shared async fixtures: `stub_embedder` (StubEmbedder dim=128), `engine` (SqliteT1+LocalFS+InProcessScheduler+MemoryEngine); all imports deferred into fixture bodies
- `tests/test_remember_recall.py` — 5 tests for SC-1 through SC-5 (remember/recall scoped, cross-session provisional, within-session buffer, schema columns, expand + access_count)
- `tests/test_scope_isolation.py` — 2 tests: cross-user isolation (len==0), user_id required kwarg raises TypeError
- `tests/test_write_path.py` — 2 tests: durable claim produces provisional T1 record, interrogative skips T1
- `tests/test_providers.py` — 1 test: StubEmbedder(dim=128) vs SqliteT1(dim=64) raises ValueError at startup
- `tests/test_scheduler.py` — 1 test: trigger_now() fires sentinel function, asyncio.sleep(0.2) wait
- `tests/test_sdk_interface.py` — 2 tests: MemoryEngine+ScopedHandle importable, engine.scope() returns ScopedHandle

## Decisions Made

- **Deferred imports in test files:** All `from mnema import ...` imports are placed inside fixture and test method bodies rather than at module scope. This lets pytest collect all 13 tests before any implementation exists (Walking Skeleton), while still failing RED with ImportError at runtime.
- **apscheduler>=3.11,<4 pinned:** Prevents inadvertent resolution to 4.x alpha (documented landmine in CLAUDE.md memory). Direct mitigation of T-1-02 from the plan threat model.
- **13th test in test_sdk_interface.py:** Added `test_engine_scope_returns_scoped_handle` to reach the >=13 collected threshold; also provides cleaner coverage of the ScopedHandle factory method (D-01 ergonomic handle design).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Deferred imports to fix conftest collection failure**
- **Found during:** Task 2 verification
- **Issue:** conftest.py imported `from mnema import MemoryEngine` at module scope; since `MemoryEngine` does not yet exist in `src/mnema/__init__.py`, pytest itself failed to load conftest, producing exit code 4 ("no tests collected") rather than the expected 13 collected / RED failures. The plan's `done` criterion requires "at least 13 test functions collected."
- **Fix:** Moved all `from mnema import ...` and all adapter imports into the fixture bodies (deferred imports). Same fix applied consistently to all 6 test files for uniformity.
- **Files modified:** tests/conftest.py + all 6 test files
- **Verification:** `uv run pytest tests/ --collect-only -q` shows 13 collected, 0 collection errors
- **Committed in:** 63f6642 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in conftest import strategy)
**Impact on plan:** Required for the `done` criterion (>=13 collected). No scope change.

## Issues Encountered

- `uv run pytest` failed on first sync because dev extras weren't installed — needed `uv sync --extra dev` before pytest was available. Fixed inline; subsequent runs use `uv run pytest` which picks up the venv correctly.

## User Setup Required

None — no external services, no environment variables required for the scaffold + test stubs.

## Next Phase Readiness

Plans 02 and 03 (Wave 2) are now unblocked:
- **01-02-PLAN.md** implements the Pydantic record schema, six Protocol ports, SqliteT1, and LocalFS adapters — these are the concrete types conftest.py and the test files reference.
- **01-03-PLAN.md** implements StubEmbedder and InProcessScheduler.
- Once Wave 2 complete, Wave 3 (01-04-PLAN.md — MemoryEngine + WritePath + RecallPath + ScopedHandle) can turn the test stubs GREEN.
- Wave 4 (01-05-PLAN.md) runs the full harness and gates Phase 1 completion.

**Blockers:** None. The deferred-import approach means all 13 tests are ready to receive implementations.

---
*Phase: 01-schema-ports-local-core-foundation*
*Completed: 2026-06-10*
