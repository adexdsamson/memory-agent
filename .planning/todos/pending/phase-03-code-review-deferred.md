---
id: phase-03-code-review-deferred
type: tech-debt
status: pending
created: 2026-06-14
source: 03-REVIEW.md
origin_phase: "03"
priority: low
---

# Phase 3 code-review findings — deferred

From `/gsd-code-review 03` (see `03-REVIEW.md` + `03-REVIEW-FIX.md`).
**All 5 criticals (CR-01..05) + WR-03/04/06 + IN-03 were FIXED in Phase 3** (commits ad0df86, e35944a, 45779bc, a0bf9ec, f573f3f, 8faed37; gate 56 green / pyright 0 / ruff clean). The cosmetic items below were deferred.

| ID | Severity | File | Issue |
|----|----------|------|-------|
| WR-01 | Low | local_fs_vault.py | Vault bullets insert at top of section (reverse-chronological). Append to end for natural reading order. |
| WR-05 | Info | recall.py | The `now` capture timing relative to the DB-update loop + re_rank() is correct but undocumented; add a comment so a future refactor doesn't break self-consistency. |
| IN-01 | Info | local_fs.py | `archive()` skips user_id input validation (low risk — flat shared cold-store file, not path-derived). |
| IN-02 | Info | multiple | Magic summary-truncation numbers (80, 60) repeated; inconsistent with the "~12 tokens" docstring. Extract a named constant. |

(WR-02 lstrip tightening was folded into the CR-02 fix.)

## How to apply
Trivial cleanups via `/gsd-code-review 03 --fix` anytime, or fold into a later polish pass. None affects correctness or the safety guarantees.
