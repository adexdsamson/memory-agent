---
phase: 03-forgetting-salience-floor-budget-packer-mcp
reviewed: 2026-06-14T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - src/mnema/core/engine.py
  - src/mnema/core/consolidation.py
  - src/mnema/core/packer.py
  - src/mnema/core/recall.py
  - src/mnema/adapters/vault/local_fs_vault.py
  - src/mnema/ports/vault.py
  - src/mnema/adapters/object_store/local_fs.py
  - src/mnema/ports/object_store.py
  - src/mnema/mcp/server.py
  - tests/test_forgetting.py
  - tests/test_recall_packer.py
  - tests/test_vault.py
  - tests/test_mcp_server.py
findings:
  critical: 5
  warning: 6
  info: 3
  total: 14
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-06-14T00:00:00Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Phase 3 ships forgetting/eviction, the two-pass budget packer, LocalFSVault, and the
MCP server surface. The large-scale architectural guarantees (no hard DELETE, protected
structural skip via decay_pass, Pitfall-8 vault-before-eviction ordering, D3-14 explicit
user_id on every MCP tool) are correctly implemented and the load-bearing invariants
described in RESEARCH.md hold in the code as written.

However, five critical-class defects were found that can cause silent data loss or
corruption in production paths, and six warnings that degrade robustness or introduce
subtle behavioral bugs.

---

## Critical Issues

### CR-01: LocalFSVault.promote() writes without atomicity — partial write corrupts the vault file

**File:** `src/mnema/adapters/vault/local_fs_vault.py:110`

**Issue:** `path.write_text(updated.lstrip(), encoding="utf-8")` overwrites the existing
vault file in a single non-atomic call. If the process is killed between the OS opening
the file for write and flushing the final bytes, the user's entire vault markdown is
truncated to zero bytes. Unlike the JSONL stores (which are append-only and therefore
crash-safe), the vault reads the whole file, mutates the string in memory, and rewrites
it. A crash mid-write destroys all previously promoted facts — including allergies and
other protected content — with no recovery path (the T2 vault has no journal).

**Fix:** Write to a sibling temp file first, then atomically rename it over the target.
`Path.rename()` is atomic on POSIX; on Windows use `os.replace()` (also atomic):

```python
import os
import tempfile

tmp_fd, tmp_path = tempfile.mkstemp(dir=self._base, suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
        fh.write(updated.lstrip())
    os.replace(tmp_path, path)
except Exception:
    os.unlink(tmp_path)
    raise
```

---

### CR-02: LocalFSVault dedup uses substring match — false positive silences legitimate promotions

**File:** `src/mnema/adapters/vault/local_fs_vault.py:91`

**Issue:** The dedup check is `if summary in existing: return`. This is a raw substring
search over the entire file content, not a line-by-line bullet equality check. Consider a
vault file that already contains the bullet `- has low blood pressure`. A new record with
summary `"blood pressure"` will match as a substring and be silently dropped, even though
it is a distinct record. More concretely: once a section header like `## Facts` is in the
file, any summary that happens to contain `"Facts"` (case-insensitive overlap aside) will
also false-positive. Any summary that is a substring of a longer existing summary will be
permanently suppressed without any notification.

**Fix:** Match against the bullet string instead of the raw file content:

```python
# Replace the current substring check:
if summary in existing:
    return

# With an exact bullet-line check:
bullet_line = f"- {summary}\n"
if bullet_line in existing:
    return
```

---

### CR-03: recall.py — `last_accessed` is updated in the DB but NOT updated on the in-memory record before re-ranking, causing stale recency scores

**File:** `src/mnema/core/recall.py:162-178`

**Issue:** Step 5 updates `access_count` and `last_accessed` in the DB and uses
`object.__setattr__` to patch `access_count` on the in-memory record. However,
`last_accessed` is never patched on the in-memory object. The in-memory record's
`last_accessed` is still `None` (the default for records that have never been
accessed). The `re_rank()` call at line 178 then computes `recency_decay` using the
stale `last_accessed=None`, falling back to `created_at`, which may be much older
than `now`. The DB is correct; the in-memory representation fed to the ranker is not.

This means: a record accessed for the first time in this recall call will be re-ranked
as if it is old (using `created_at`), producing a lower composite score and potentially
incorrect ordering. After a second recall call it will rank correctly (because then
`last_accessed` is set in the DB and will be returned via `.get()`). The error is subtle
and session-persistent.

**Fix:** Patch `last_accessed` alongside `access_count`:

```python
for record in t1_records:
    await self._record_store.update(
        record.id,
        access_count=record.access_count + 1,
        last_accessed=now,
    )
    object.__setattr__(record, "access_count", record.access_count + 1)
    object.__setattr__(record, "last_accessed", now)  # <-- add this line
```

---

### CR-04: ConsolidationPipeline.run() eviction pass silently skips the JSONL audit (FORG-04) when `t0` is None — existing tests never exercise the guarded path

**File:** `src/mnema/core/consolidation.py:239-251`

**Issue:** The eviction path inside `ConsolidationPipeline.run()` guards both the cold
archive write and the JSONL audit append with `if self._t0 is not None`. This guard was
introduced to support "older tests that omit t0". The consequence is that any eviction
triggered through `ConsolidationPipeline.run()` without a `t0` adapter silently produces
zero audit entries. FORG-04 mandates that every eviction is auditable. A
`ConsolidationPipeline` constructed without `t0` (e.g. by a future test that wires vault
but forgets t0) will evict records silently and without cold-store archiving, violating
FORG-04 and the "never hard-delete" guarantee simultaneously.

By contrast, `engine.evict()` calls `self._t0.archive(record)` and
`self._t0.append_audit(entry)` unconditionally — there is no None guard there. The two
eviction paths have divergent safety guarantees.

**Fix:** Either (a) make `t0` a required parameter of `ConsolidationPipeline.__init__`
with no default, or (b) if backward compatibility with legacy tests is needed, raise
`RuntimeError` if eviction is attempted with `t0 is None`:

```python
# In the eviction loop, replace the silent guard:
if self._t0 is not None:
    await self._t0.archive(record)
    ...

# With an assertion that surfaces the misconfiguration:
if self._t0 is None:
    raise RuntimeError(
        "ConsolidationPipeline: t0 is required for eviction (FORG-04). "
        "Pass t0= to ConsolidationPipeline or disable eviction."
    )
await self._t0.archive(record)
...
```

---

### CR-05: `engine.consolidate()` calls `scheduler.trigger_now()` AFTER the pipeline completes — but if `ConsolidationPipeline.run()` raises, `trigger_now()` is never called and the scheduler state is left inconsistent

**File:** `src/mnema/core/engine.py:399-400`

**Issue:**

```python
await self._consolidation_pipeline.run(user_id=user_id)
await self._scheduler.trigger_now()
```

`trigger_now()` is the scheduler's signal that a consolidation cycle completed. If
`_consolidation_pipeline.run()` raises an exception (e.g. a DB error mid-eviction, an
embedder timeout during entity resolution, a vault write error), `trigger_now()` is never
called. The scheduler will be stuck believing a consolidation pass is still "in progress"
or that one has not completed, depending on `InProcessScheduler`'s implementation. Future
invocations of `consolidate()` may then be gated on that scheduler state.

More concretely: in the `test_vault_promotion_before_eviction` test, a vault write error
would leave the scheduler in a bad state for all subsequent test operations.

**Fix:** Wrap with `try/finally` so `trigger_now()` is always called:

```python
try:
    await self._consolidation_pipeline.run(user_id=user_id)
finally:
    await self._scheduler.trigger_now()
```

---

## Warnings

### WR-01: `LocalFSVault.promote()` inserts the bullet at the TOP of its section (immediately after the header), not the bottom — repeated promotions reverse chronological order within a section

**File:** `src/mnema/adapters/vault/local_fs_vault.py:98-104`

**Issue:** The `str.replace()` call inserts the new bullet immediately after the section
header line, pushing all prior bullets down. Each new promotion prepends to the section
rather than appending. The net effect is that the vault file reads in reverse-insertion
order within each section. This is a quality defect — vault files are intended to be
human-readable and git-versioned; a reverse-chronological within-section order is
confusing and non-obvious.

**Fix:** Append the bullet after the last bullet in the section rather than inserting
after the header. The simplest correct approach is to append to the end of the section
block, or simply always append to end-of-file within the section when the section exists:

```python
if section_header + "\n" in existing:
    # Append after the last line of this section instead of prepending
    updated = existing + bullet
else:
    updated = existing + f"\n{section_header}\n{bullet}"
```

(A fully correct implementation requires scanning for the section's end, but even
simple append-to-file is correct for the MVP.)

---

### WR-02: `LocalFSVault.promote()` emits `lstrip()` on the full updated content — strips leading whitespace from the first section header on subsequent writes

**File:** `src/mnema/adapters/vault/local_fs_vault.py:110`

**Issue:** `path.write_text(updated.lstrip(), ...)` strips all leading whitespace from
the full file content on every write. The `lstrip()` is documented as removing "leading
whitespace from an initially-empty file". However, if `existing` is non-empty and
`updated` does not start with whitespace (the normal case after the first write), this is
a no-op. But if `existing` starts with whitespace for any reason (e.g. concurrent
modification, a vault file edited by the developer), `lstrip()` will silently strip
legitimate content. The intent (clean first write) is correct but the scope of the strip
is too broad; it should be applied only when `existing == ""`.

**Fix:**

```python
final = updated.lstrip() if not existing else updated
path.write_text(final, encoding="utf-8")
```

---

### WR-03: `pack_records()` Pass 1 silently truncates the critical set when it exceeds budget — a budget too small to hold all critical records produces a partial critical set with no caller notification

**File:** `src/mnema/core/packer.py:188-193`

**Issue:** If the budget is smaller than the total token cost of all critical records,
Pass 1 includes as many critical records as fit and silently drops the rest. A caller
that sets `budget=50` while holding 3 allergy facts totaling 60 tokens will receive only
a subset of their critical facts. The RECALL-05 spec says "Critical records are always
included (up to budget)" — the "up to budget" qualification is correct but the silent
truncation is hazardous for callers who rely on the guarantee that all protected records
are returned.

This is especially dangerous for an allergy engine: two allergies that together exceed a
very tight budget would cause one to be silently omitted.

**Fix:** Either log a warning when the critical set is truncated, or document the budget
minimum (at least max(critical_set_token_cost)) in the function contract. At minimum,
raise a warning log line so operators can detect misconfigured budgets:

```python
# After Pass 1 loop:
dropped_critical = [r for r in critical if r.id not in packed_ids]
if dropped_critical:
    import warnings
    warnings.warn(
        f"pack_records: budget={budget} too small to include all critical records; "
        f"{len(dropped_critical)} critical record(s) dropped.",
        stacklevel=2,
    )
```

---

### WR-04: `ConsolidationPipeline.run()` vault+eviction passes only run for `processed_user_ids` — a user whose staged items were ALL filtered out (wrong user_id) gets no vault or eviction pass

**File:** `src/mnema/core/consolidation.py:186-199`

**Issue:** `processed_user_ids` is built from the items that survived the `user_id`
filter at line 171. If `user_id="u1"` is passed but all items in the queue belong to
`"u2"` (because the caller staged turns under the wrong user), `processed_user_ids` will
be empty and no vault or eviction pass runs for any user — including users who have
stale T1 records that need eviction.

More subtly: if `user_id=None` is passed (global consolidation) but the queue is empty
because it was already drained by a prior run, `processed_user_ids` is empty and the
vault/eviction pass is skipped entirely for all users. This means that calling
`consolidate()` twice in quick succession (e.g. in tests) causes the second call to skip
the vault and eviction passes even for users who have records eligible for both.

The vault and eviction passes should be user-scope-aware but not gated solely on "what
was in the queue in this call".

**Fix:** Separate the "which users to run vault/eviction for" decision from "which items
were staged this call". When `user_id` is provided, always run the vault+eviction pass
for that user regardless of queue contents:

```python
# Replace:
processed_user_ids: set[str] = {
    item.get("user_id", "")
    for item in items
    if item.get("user_id")
}

# With:
processed_user_ids: set[str] = {
    item.get("user_id", "")
    for item in items
    if item.get("user_id")
}
# When scoped, always include the requested user_id even if queue was empty
if user_id is not None:
    processed_user_ids.add(user_id)
```

---

### WR-05: `re_rank()` in `packer.py` uses `now` captured at function-call time, but `RecallPath.execute()` computes its own `now` after the DB update round-trip — tiny clock skew between the two `now` values

**File:** `src/mnema/core/recall.py:162,178`

**Issue:** `now = _utcnow()` is called at line 162 (before the DB update loop). Then
`re_rank(combined, similarity_scores, now)` passes that same `now` to the ranker at
line 178. The `last_accessed` field written to the DB at line 167 uses this same `now`,
so the recency decay computation is self-consistent for updated records. This is actually
correct as written. However, it relies on `now` being captured once before the update
loop — if the `now` call were moved inside the loop or after the re_rank call, a subtle
bug would be introduced. This is fragile code structure worth a comment documenting
the dependency.

**Fix:** Add an explicit comment noting the `now` capture is intentional:

```python
# Capture now once — used for both last_accessed DB update and re_rank recency
# computation. These must use the same timestamp for consistency.
now = _utcnow()
```

---

### WR-06: `test_vault_promotion_before_eviction` calls `engine.consolidate()` (no `user_id`) but the test relies on `processed_user_ids` including `"u1"` — this is only guaranteed if the dummy `remember()` call enqueues to the staging queue

**File:** `tests/test_vault.py:176-177`

**Issue:** The test stages a dummy turn via `engine.remember(...)` and then calls
`engine.consolidate()` with no `user_id`. The vault+eviction pass will only run for
`"u1"` if `processed_user_ids` includes `"u1"`, which in turn requires the dummy
staging item to have `user_id="u1"` in it. This is a latent coupling between the test
correctness and `WritePath.execute()`'s staging item format. If `WritePath` stops
including `user_id` in staging items (e.g. a refactor), the test passes the consolidate
call with no error but `processed_user_ids` is empty, the vault pass never runs, and the
assertion at line 180 silently fails because `vault_content` is `""`.

This makes the test fragile — it would produce a confusing failure message ("vault must
contain promoted record") rather than a clear "processed_user_ids was empty" error.

**Fix:** In the test, call `engine.consolidate(user_id="u1")` instead of
`engine.consolidate()` to make the scope explicit and independent of staging item format.
This also exercises the WR-04 fix correctly.

---

## Info

### IN-01: `local_fs.py` — `archive()` does not validate that `record.user_id` is safe before writing

**File:** `src/mnema/adapters/object_store/local_fs.py:119-127`

**Issue:** `archive()` appends the record JSON to a shared `archived.jsonl` file (not a
per-user file), so path traversal via `record.user_id` is not exploitable here. However,
the function does not call `_validate_session_id(record.session_id)` or any other input
validation. If a record with a crafted `session_id` were archived, its session_id would
appear in the JSONL output but cause no filesystem harm. This is low-risk given the
shared flat file, but it is inconsistent with the validation discipline applied everywhere
else in the file.

**Fix:** Either document why no validation is needed (shared flat file, not path-derived)
or add a comment noting this is intentional. No code change required.

---

### IN-02: Magic number `content[:80]` repeated in multiple files without a named constant

**File:** `src/mnema/core/packer.py:190,202`, `src/mnema/core/recall.py:69`, `src/mnema/adapters/vault/local_fs_vault.py:87`

**Issue:** The fallback truncation length `80` (and `60` in `consolidation.py:343`) is
a magic number repeated across files. If the desired summary truncation length changes,
all occurrences must be found and updated manually. The `summary` field docstring says
"<= ~12 tokens" but 80 characters yields ~20 tokens via `ByteLengthCounter` — these
are inconsistent.

**Fix:** Define a module-level constant:

```python
SUMMARY_FALLBACK_CHARS: int = 80  # ~20 tokens; used when record.summary is empty
```

---

### IN-03: `ConsolidationPipeline._insert_new_confirmed()` and `_apply_verdict()` construct `RecordType(...)` from `ext.get(...)` without wrapping in `try/except ValueError` consistently

**File:** `src/mnema/core/consolidation.py:505,462`

**Issue:** In `_insert_new_confirmed()` line 505, `RecordType(ext.get("record_type", "preference"))` is called without a `try/except`. In `_process_turn()` at line 357 the same call is wrapped in `try/except ValueError`. In `_apply_verdict()` at line 462 it is unwrapped again. A malformed LLM response with an invalid `record_type` in the contradiction path will raise an unhandled `ValueError` that propagates up through `_apply_verdict()` and `_process_turn()` silently skipping the turn at the `except (json.JSONDecodeError, ValueError)` handler at line 295 — but only if the exception reaches that handler. Since `_apply_verdict` is called after the try block, the ValueError from `RecordType(...)` at line 462 would NOT be caught by the `except` at line 295 and would propagate uncaught, aborting the entire consolidation run.

**Fix:** Wrap the `RecordType(...)` call in `_apply_verdict()` and `_insert_new_confirmed()` with a `try/except ValueError`, defaulting to `RecordType.PREFERENCE` as done in `_process_turn()`.

---

_Reviewed: 2026-06-14T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
