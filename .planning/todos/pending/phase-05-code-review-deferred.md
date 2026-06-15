---
id: phase-05-code-review-deferred
type: tech-debt
status: pending
created: 2026-06-15
source: 05-REVIEW.md
origin_phase: "05"
priority: low
---

# Phase 5 code-review findings — deferred

From `/gsd-code-review 05`. **CR-01, CR-02, WR-01, WR-02, WR-03, IN-01 were FIXED** (commits 9512bba, 24890ed, 379b42c). Deferred (cosmetic only):

| ID | File | Issue |
|----|------|-------|
| IN-02 | coach.py | `run_session` docstring mentions `engine._t1.close()` but code correctly uses `engine.t1.close()` — update docstring. |
| IN-03 | eval/baseline.py | `_assemble_naive_context` is recomputed per-probe (same result after seeding); the per-probe naive-token column implies a query-dependence that doesn't exist — compute once + note it. |
