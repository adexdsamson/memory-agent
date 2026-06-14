---
id: phase-02-code-review-deferred
type: tech-debt
status: pending
created: 2026-06-14
source: 02-REVIEW.md
origin_phase: "02"
priority: low
---

# Phase 2 code-review findings — deferred

From `/gsd-code-review 02` (see `.planning/phases/02-consolidation-supersession/02-REVIEW.md`).
**4 criticals (CR-01..04) + 3 warnings (WR-01/04/05) were FIXED in Phase 2** (commits b0cb333, 1752eff, cd277b4, fa48ee5). The items below were deferred — none affects the Phase 2 gate (33 tests green, pyright + ruff clean) and they mostly concern the Phase-4 real-LLM path or test ergonomics.

| ID | Severity | File | Issue |
|----|----------|------|-------|
| WR-02 | Low | stub.py / test_consolidation.py | StubLLM judge hashes *extracted* content; test pre-computes verdict from *raw* content — equal only because `_extract` returns content verbatim. If extraction ever reformats, verdict pre-computations diverge → flaky. Tighten when the real LLM lands (Phase 4). |
| WR-03 | Low (Phase 4) | consolidation.py | A malformed LLM response in `_process_turn` returns silently — staging item already drained, turn unrecoverable. Benign with StubLLM; a silent data-loss vector for the real LLM. Add error logging / dead-letter handling in Phase 4. |
| IN-01 | Info | decay.py | `decay_pass` annotated `AsyncGenerator` on an `async def…yield`; pyright is clean either way. Cosmetic — `AsyncIterator` reads better. Leave unless pyright complains. |
| IN-02 | Info | consolidation.py / stub.py | `_EXTRACT_SENTINEL` / `_JUDGE_SENTINEL` defined as constants in consolidation.py but checked as inline literals in stub.py — a rename in one breaks the other silently. Share the constants when the real LLM adapter is added (Phase 4). |
| IN-03 | Info | test_consolidation.py | `_find_new_content_for_verdict` has a magic 1000-iteration cap with no comment on the probability bound. Add a one-line comment. |

## How to apply
Fold WR-02/WR-03/IN-02 into Phase 4 (real Qwen/Claude LLM adapter) since they concern the LLM seam; IN-01/IN-03 are trivial cosmetic cleanups anytime via `/gsd-code-review 02 --fix`.
