---
id: phase-01-code-review-deferred
type: tech-debt
status: pending
created: 2026-06-10
source: 01-REVIEW.md
origin_phase: "01"
priority: medium
---

# Phase 1 code-review findings — deferred to gap-closure / Phase 2

Surfaced by `/gsd-code-review 01` (see `.planning/phases/01-schema-ports-local-core-foundation/01-REVIEW.md`).
**CR-04 (safety flag) and CR-01 (Scheduler Protocol async) were fixed in Phase 1**
(commits `3e4c7c4`, `f77fb19`). The findings below were consciously deferred — none
breaks the Phase 1 gate (23 tests green, pyright + ruff clean) and most are latent
or only manifest under concurrency / future change.

## Remaining findings

| ID | Severity | File | Issue |
|----|----------|------|-------|
| CR-02 | Critical(fragile) | `sqlite_t1.py` | `cursor.row_factory = None` set *after* `execute()`; should clear before. Works now (per-row apply at fetch), fragile under aiosqlite internals. |
| CR-03 | Critical(latent) | `local_fs.py` | `append()` TOCTOU: counts lines then re-opens to append → wrong `t0_ref` offset under concurrent `gather` writes. Correct under sequential awaits (Phase 1). Fix: single-handle append + atomic offset. |
| CR-05 | Low | `recall.py` | `object.__setattr__` bypass for `access_count` increment; record isn't frozen — use normal assignment so future field validators apply. |
| WR-01 | Low-Med | `sqlite_t1.py` | `get_latest()` missing `AND valid_until IS NULL` → can return evicted/dead records. |
| WR-02 | Low | `buffer.py` | `as_candidates(session_id=...)` leaks cross-user turns if two users share a session_id string. Unused by RecallPath (which uses `as_candidates_for_user`), but the unsafe method is public — remove or guard. |
| WR-03 | Low | `in_process.py` | Hardcoded `JOB_ID="consolidate"` → second `schedule()` raises APScheduler `ConflictingIdError`. |
| WR-04 | Low | `engine.py` | PROV-06 dim guard reads private `t1._dim` instead of public `t1.dim`; a future adapter without `_dim` silently bypasses the guard. |
| WR-05 | Low | `sqlite_t1.py` | `upsert()` + `upsert_vector()` commit independently → crash between them leaves a record invisible to vector search. Wrap in one transaction. |
| IN-01 | Info | `sqlite_t1.py` | `_ALLOWED_COLUMNS` includes `user_id/session_id/agent_id` → `update()` can re-scope a record to another user. Consider removing scope keys from the whitelist. |
| IN-02 | Info | `buffer.py`,`classifier.py` | `Optional[...]` vs project-standard `X | None` on 3.12+. |
| IN-03 | Info | `conftest.py` | engine fixture never closes the aiosqlite connection → `ResourceWarning`. |
| — | cosmetic | `in_process.py` | APScheduler emits "Event loop is closed" at interpreter-exit GC after `shutdown(wait=False)`. All work completes first. Tied to [[mnema-python-314-cap-deviation]]. |

## How to apply

Run `/gsd-code-review 01 --fix` (Critical+Warning) once Phase 1 is closed, or fold
WR-01/WR-04/WR-05/IN-01 into a Phase 2 hardening slice (they touch consolidation/decay
surfaces Phase 2 builds on anyway). CR-03 should be fixed before any concurrent-write
path is introduced.
