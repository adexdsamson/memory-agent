---
phase: 02-consolidation-supersession
plan: "01"
subsystem: adapters/llm + tests
tags: [stub, tdd, walking-skeleton, llm-adapter, consolidation, decay]
dependency_graph:
  requires:
    - 01-04-SUMMARY.md  # Phase 1 complete: schema, ports, sqlite_t1, engine
  provides:
    - src/mnema/adapters/llm/stub.py (StubLLM satisfying LLMProvider Protocol)
    - tests/test_consolidation.py (8 RED stubs CONS-01..08)
    - tests/test_decay.py (2 RED stubs FORG-01, FORG-03 partial)
  affects:
    - tests/conftest.py (extended with stub_llm + engine_with_llm fixtures)
tech_stack:
  added: []
  patterns:
    - sentinel-dispatch pattern for deterministic stub LLM (EXTRACT_RECORDS:, JUDGE_CONTRADICTION:)
    - sha256-hash-mod-3 for deterministic contradiction verdicts
    - deferred imports in fixtures for walking-skeleton collection before implementation
key_files:
  created:
    - src/mnema/adapters/llm/__init__.py
    - src/mnema/adapters/llm/stub.py
    - tests/test_consolidation.py
    - tests/test_decay.py
  modified:
    - tests/conftest.py
decisions:
  - "StubLLM uses structural subtyping (no LLMProvider base class, D-08)"
  - "EXTRACT_RECORDS sentinel produces keyword-driven extraction; safety keywords -> protected=True + salience=1.0"
  - "JUDGE_CONTRADICTION sentinel uses sha256(body) % 3 for reproducible verdicts in seeded tests"
  - "engine_with_llm fixture raises TypeError at execution (not collection) because llm= not yet accepted by MemoryEngine -- correct RED state"
  - "test_decay.py tests are plain def (no async) reflecting D-12 sans-I/O keep_score contract"
metrics:
  duration: "291 seconds (~5 min)"
  completed: "2026-06-13"
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 1
---

# Phase 02 Plan 01: StubLLM + RED Test Stubs Summary

**One-liner:** Deterministic StubLLM adapter (sentinel-dispatch + sha256 judgment) with 10 RED test stubs covering all Phase 2 requirements (CONS-01..08, FORG-01).

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | StubLLM adapter + llm package init | 5d2b9bf | src/mnema/adapters/llm/__init__.py, src/mnema/adapters/llm/stub.py |
| 2 | RED test stubs + conftest extensions | bae273e | tests/conftest.py, tests/test_consolidation.py, tests/test_decay.py |

## Verification Results

- `pytest --collect-only -q`: **33 tests collected** (23 Phase 1 + 10 new RED stubs)
- `pytest --ignore=test_consolidation.py --ignore=test_decay.py`: **23 passed** (Phase 1 green)
- `pytest tests/test_consolidation.py tests/test_decay.py`: **2 failed, 8 errors** (correct RED state)
- `pyright src/mnema/adapters/llm/`: **0 errors, 0 warnings**
- StubLLM importable and deterministic for extraction and judgment modes

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

The test files are intentional RED stubs -- all methods raise `NotImplementedError`. This is the required walking-skeleton state for Phase 2 Wave 0. No unintentional stubs introduced.

## Threat Flags

No new threat surface introduced. Both files are test infrastructure (no network endpoints, no auth paths, no schema changes). T-02-02 mitigated: each test gets a fresh `tmp_path` + in-memory SQLite via the fixture yield pattern.

## Self-Check: PASSED

Files exist:
- src/mnema/adapters/llm/__init__.py: FOUND
- src/mnema/adapters/llm/stub.py: FOUND
- tests/test_consolidation.py: FOUND
- tests/test_decay.py: FOUND
- tests/conftest.py (modified): FOUND

Commits exist:
- 5d2b9bf (Task 1): FOUND
- bae273e (Task 2): FOUND
