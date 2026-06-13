---
phase: 02-consolidation-supersession
plan: "02"
subsystem: core/decay
tags: [decay, keep_score, forg-01, forg-03, tdd, pure-sync, d-12]
dependency_graph:
  requires:
    - "02-01"  # walking-skeleton + test_decay.py stubs
  provides:
    - keep_score  # consumed by Phase 3 eviction pass
    - decay_pass  # async generator over live records
  affects:
    - "02-04"  # ConsolidationPipeline calls decay_pass at end of consolidate()
    - "03-*"   # Phase 3 eviction path uses keep_score and decay_pass
tech_stack:
  added: []
  patterns:
    - "Pure sync D-12 module with TYPE_CHECKING-only MemoryRecord import"
    - "AsyncGenerator[tuple[MemoryRecord, float], None] producer annotation"
    - "FORG-03 skip-before-score (not score=1.0) as the protected-record guarantee"
    - "Static method mock for async generator protocol in tests"
key_files:
  created:
    - src/mnema/core/decay.py
  modified:
    - tests/test_decay.py
decisions:
  - "FORG-03 implemented as skip-before-score in decay_pass (stronger than yielding score=1.0 — eviction caller cannot act on what it never sees)"
  - "TYPE_CHECKING-only import of MemoryRecord keeps decay.py runtime-free of Pydantic (D-12 purity)"
  - "Mock fixture uses @staticmethod to avoid implicit self injection when live_records is called through the duck-typed record_store interface"
metrics:
  duration_minutes: 15
  completed_date: "2026-06-13"
  tasks_completed: 1
  files_created: 1
  files_modified: 1
---

# Phase 02 Plan 02: Decay Module (keep_score + decay_pass) Summary

**One-liner:** Pure-sync keep_score using W_RECENCY=0.4/W_REINFORCE=0.3/W_SALIENCE=0.3 exponential-decay formula with FORG-03 skip-before-score protection gate in decay_pass async generator.

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED  | cc868ae | PASS — 2 tests fail with ModuleNotFoundError before implementation |
| GREEN | ff05a6d | PASS — 2 tests pass; 25-test suite passes; pyright 0 errors |

## What Was Built

### `src/mnema/core/decay.py`

A D-12-compliant pure module with two exports:

**`keep_score(record, now=None) -> float`**

Pure synchronous function. Formula:
```
recency   = exp(-0.05 * age_days)
reinforce = log(1 + access_count)
score     = 0.4*recency + 0.3*reinforce + 0.3*salience
return    = clamp(score, 0.0, 1.0)
```

Reference time is `last_accessed` if set, else `created_at` (D2-15). The `max(0.0, age_days)` clamp handles clock skew (T-02-04).

**`decay_pass(record_store, user_id, now=None) -> AsyncGenerator[tuple[MemoryRecord, float], None]`**

Async generator. Iterates `record_store.live_records(user_id)` and yields `(record, score)` for every non-protected record. Protected records are `continue`d before any math — FORG-03 structural guarantee.

### `tests/test_decay.py`

Two test cases in `TestDecay`:

- `test_keep_score_values`: verifies fresh=0.55, 14-day decay ≈ 0.347, high-access clamped to 1.0
- `test_protected_skipped_before_score_math`: verifies keep_score itself does not raise on protected input, AND that decay_pass yields nothing for a protected-only record store

## Verification Results

| Check | Result |
|-------|--------|
| `pytest tests/test_decay.py -q` | 2 passed |
| `pytest -q --ignore=tests/test_consolidation.py` | 25 passed |
| `pyright src/mnema/core/decay.py` | 0 errors, 0 warnings |
| `inspect.iscoroutinefunction(keep_score)` | False (confirmed sync) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed mock fixture implicit-self injection**
- **Found during:** GREEN phase — `test_protected_skipped_before_score_math` failed with `TypeError: _mock_live_records() takes 1 positional argument but 2 were given`
- **Issue:** The test assigned a module-level async generator function `_mock_live_records` as a class attribute of `_MockStore`. When `decay_pass` called `record_store.live_records(user_id)`, Python's descriptor protocol injected `self` as the first positional argument, making it a 2-argument call to a 1-argument function.
- **Fix:** Replaced bare function assignment with `@staticmethod` on `live_records` inside `_MockStore`. Static methods bypass descriptor binding and receive only the explicitly passed arguments.
- **Files modified:** `tests/test_decay.py`
- **Commit:** `ff05a6d` (included in GREEN commit)

## Known Stubs

None. `keep_score` and `decay_pass` are fully implemented with real logic.

## Threat Flags

No new security surface beyond what the threat model documents. Mitigations applied:

| Threat | File | Mitigation |
|--------|------|------------|
| T-02-03 (Tampering — protected record eviction) | decay.py:155 | `if record.protected: continue` — protected records never yielded |
| T-02-04 (DoS — negative age_days) | decay.py:120 | `max(0.0, age_days)` clamp applied before `math.exp` |

## Self-Check

Files exist:
- `src/mnema/core/decay.py` — FOUND
- `tests/test_decay.py` — FOUND (modified)

Commits exist:
- `cc868ae` — RED test commit
- `ff05a6d` — GREEN implementation commit

## Self-Check: PASSED
