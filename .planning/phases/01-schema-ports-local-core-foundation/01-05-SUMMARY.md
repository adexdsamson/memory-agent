---
phase: 01-schema-ports-local-core-foundation
plan: "05"
status: complete
completed: 2026-06-10
requirements: [EVAL-01, CORE-01, CORE-02, CORE-03, CORE-04, CORE-05, RECALL-06, RECALL-07]
---

# Plan 01-05 Summary — Full harness GREEN, schema unit tests, phase gate

## What was built

The verification-and-close plan for Phase 1. Confirmed every ROADMAP success
criterion (SC-1…SC-5) has a passing automated test, added dedicated schema unit
tests, made the `expand()` path exercise for real, fixed a recall-duplicate bug
surfaced at the human-verify checkpoint, and ran the full phase gate clean.

## Key changes

- **`tests/test_schema.py`** (new) — 7 synchronous Pydantic unit tests locking the
  un-retrofittable column contract: minimal construction, `protected` is `bool`
  (CORE-04), `valid_until is None` on new records (CORE-05), embedding provenance
  unset at construction (CORE-03), `record_type="fact"` coerced to `RecordType.FACT`
  StrEnum (CORE-02), `access_count == 0` baseline (RECALL-07), and presence of all
  un-retrofittable columns.
- **`tests/test_remember_recall.py`** — `test_expand_and_access_count` now asserts
  `t0_ref is not None` and calls `expand()` **unconditionally**, asserting the Turn
  content is returned verbatim (was previously guarded by `if t0_ref is not None`,
  so the real expand path could be skipped). Added `test_recall_dedupes_same_session_fact`.
- **`src/mnema/core/recall.py`** — **bug fix:** recall returned a just-written fact
  twice because it lives in both the buffer (`Turn`, `turn_*` id) and T1
  (`MemoryRecord`, `mem_*` id); id-only dedup never matched across that id boundary.
  Now dedups by **content** — the T1 record (full provenance + `t0_ref` + embedding)
  wins; a buffer turn is emitted only if its content is not already in T1 and not
  duplicated within the buffer.
- **`tests/test_providers.py`** — extracted long `pytest.raises` regex to a local var
  (ruff E501).
- **`.gitignore`** (new) — Python/uv/test-cache/sqlite artifacts; untracked the
  `__pycache__/*.pyc` files that the scaffold had accidentally committed.
- **`01-VALIDATION.md`** — finalized: `status: validated`, `nyquist_compliant: true`,
  per-requirement → test map, TIER-02 sqlite-vec Windows load verified (`v0.1.9`),
  Python 3.14 env note, sign-off complete.

## Verification (final phase gate)

| Check | Result |
|-------|--------|
| `uv run pytest tests/ -q` | **21 passed** |
| `uv run pyright` (strict) | **0 errors, 0 warnings** |
| `uv run ruff check src/ tests/` | **All checks passed** |
| sqlite-vec load (TIER-02, Windows) | **v0.1.9** |
| E2E smoke: remember→recall | single result, content correct |
| Scope isolation: u2 recall of u1 data | `[]` (no leak) |

Human-verify checkpoint: **approved** (user elected to fix the recall-duplicate
before close).

## Deviations

- **Recall-duplicate fix (in-scope correction):** not a planned task, but caught at
  the blocking human-verify checkpoint; fixed with the user's explicit approval since
  duplicates waste the recall token budget (counter to the core thesis).
- **`.gitignore` + `__pycache__` untracking:** hygiene fix; the Wave-1 scaffold
  shipped without a `.gitignore` and `git add tests/` had captured compiled files.

## Known follow-ups (Phase 2+)

- **Python 3.14.2**: uv resolved 3.14 (pyproject has no upper cap; CLAUDE.md mandates
  ≤3.13). All Phase 1 passes, but pgvector/other C-extension wheels may lag on 3.14 —
  add `requires-python = ">=3.12,<3.14"` if a wheel fails.
- **Scheduler teardown noise**: `InProcessScheduler.shutdown()` emits "Event loop is
  closed" at interpreter teardown on 3.14 (cosmetic; all work completes first).
