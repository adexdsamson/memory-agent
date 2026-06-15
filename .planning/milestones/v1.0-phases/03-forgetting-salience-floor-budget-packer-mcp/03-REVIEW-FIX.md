---
phase: 03-forgetting-salience-floor-budget-packer-mcp
fixed_at: 2026-06-14T00:00:00Z
review_path: .planning/phases/03-forgetting-salience-floor-budget-packer-mcp/03-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-06-14
**Source review:** `.planning/phases/03-forgetting-salience-floor-budget-packer-mcp/03-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (5 critical + 2 warnings + 2 info/warning)
- Fixed: 9
- Skipped: 0

**Gate results (post-fix):**
- `pytest tests/ -q`: **56 passed** (was 54; 2 new tests added)
- `pyright`: **0 errors, 0 warnings**
- `ruff check src/ tests/`: **All checks passed**

---

## Fixed Issues

### CR-01: LocalFSVault atomic write

**Files modified:** `src/mnema/adapters/vault/local_fs_vault.py`
**Commit:** `ad0df86`
**Applied fix:** Replaced `path.write_text()` with `tempfile.mkstemp()` + `os.fdopen()` + `os.replace()`. The temp file is written to the same directory as the vault (so the rename is on the same filesystem), and on failure the temp file is unlinked. `os.replace()` is atomic on both POSIX and Windows. A crash mid-write can no longer truncate the vault to zero bytes.

---

### CR-02: LocalFSVault exact bullet dedup

**Files modified:** `src/mnema/adapters/vault/local_fs_vault.py`
**Commit:** `ad0df86` (combined with CR-01)
**Applied fix:** Replaced `if summary in existing` (raw substring search over full file) with `if f"- {summary}\n" in existing` (exact bullet-line match). A short summary like `"blood pressure"` is no longer silently suppressed just because a longer existing bullet contains that substring. Also tightened `lstrip()` to apply only when `existing == ""` (WR-02 intent).

---

### CR-03: recall.py patch last_accessed in-memory

**Files modified:** `src/mnema/core/recall.py`
**Commit:** `e35944a`
**Applied fix:** Added `object.__setattr__(record, "last_accessed", now)` alongside the existing `access_count` patch. Without this, `re_rank()` would compute `recency_decay` from `created_at` (the None-fallback) for any record accessed for the first time in a recall call, producing a lower composite score and incorrect result ordering.

---

### CR-04: ConsolidationPipeline eviction requires t0 (FORG-04)

**Files modified:** `src/mnema/core/consolidation.py`
**Commit:** `45779bc`
**Applied fix:** Replaced the silent `if self._t0 is not None:` guard around the eviction archive+audit with a `RuntimeError` raised immediately before any eviction that would have proceeded without t0. The error message explicitly references FORG-04. Every eviction must produce a cold-store archive entry and JSONL audit entry; silently skipping them is not acceptable. This aligns the ConsolidationPipeline eviction path with the unconditional guarantee in `engine.evict()`.

---

### CR-05: engine.consolidate() try/finally for scheduler

**Files modified:** `src/mnema/core/engine.py`
**Commit:** `a0bf9ec`
**Applied fix:** Wrapped `await self._consolidation_pipeline.run(user_id=user_id)` in `try/finally` so `await self._scheduler.trigger_now()` is always called even when the pipeline raises. Without this, any exception mid-pipeline left the scheduler in an inconsistent "in-progress" state that could gate all future consolidation calls.

---

### WR-03: packer.py never silently drops protected records

**Files modified:** `src/mnema/core/packer.py`
**Commit:** `f573f3f`
**Applied fix:** Protected records (`rec.protected is True`) are now unconditionally appended to the packed output in Pass 1, even when their token cost would exceed the budget. Non-protected critical records (live FACT-type) still respect the budget limit. If any non-protected critical records are dropped, a `warnings.warn()` is emitted so operators can detect misconfigured budgets. The "never forget a protected fact" guarantee is now structurally enforced at the packer level.

**New test:** `test_protected_fact_retained_when_budget_smaller_than_critical_set` in `tests/test_recall_packer.py` — asserts both protected allergy facts are present in output when budget is smaller than the cost of a single record.

---

### WR-04: ConsolidationPipeline vault/eviction runs for requested user even when queue is empty

**Files modified:** `src/mnema/core/consolidation.py`
**Commit:** `45779bc` (combined with CR-04/IN-03)
**Applied fix:** Added `if user_id is not None: processed_user_ids.add(user_id)` immediately after building `processed_user_ids` from queue items. This ensures vault promotion and eviction passes always run for the explicitly-scoped user, regardless of whether the queue had any items for them in this call.

**New test:** `test_vault_pass_runs_with_empty_queue` in `tests/test_vault.py` — seeds a high-salience record directly into T1 with no `remember()` call (queue stays empty), calls `consolidate(user_id="u1")`, and asserts the record appears in the vault.

---

### WR-06: test_vault_promotion_before_eviction uses explicit user_id

**Files modified:** `tests/test_vault.py`
**Commit:** `8faed37`
**Applied fix:** Changed `await engine.consolidate()` to `await engine.consolidate(user_id="u1")` in `test_vault_promotion_before_eviction`. This makes the test independent of the staging item format — it no longer relies on `processed_user_ids` being populated from the dummy `remember()` call's queue item. Also updated `test_promotion_on_consolidation` to use explicit `user_id="u1"` and removed the no-longer-needed dummy `remember()` call (WR-04 ensures the vault pass runs even with an empty queue).

---

### IN-03: ConsolidationPipeline RecordType() wrapped in try/except

**Files modified:** `src/mnema/core/consolidation.py`
**Commit:** `45779bc` (combined with CR-04/WR-04)
**Applied fix:** Wrapped the `RecordType(...)` call in `_apply_verdict()` (supersession path) and `_insert_new_confirmed()` in `try/except ValueError` with `RecordType.PREFERENCE` as the default, matching the pattern already used in `_process_turn()`. A malformed LLM response with an invalid `record_type` string no longer raises an unhandled `ValueError` that aborts the entire consolidation run.

---

## Skipped Issues

None — all 9 in-scope findings were fixed.

---

## Deferred (not in scope per instructions)

- **WR-01** — vault bullet ordering (reverse chronological within section)
- **WR-02** — `lstrip()` scope too broad (partially addressed as a side-effect of CR-01/CR-02 fix)
- **WR-05** — `now`-capture comment in recall.py
- **IN-01** — archive() input validation comment
- **IN-02** — magic-number constant for 80-char truncation

---

_Fixed: 2026-06-14_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
