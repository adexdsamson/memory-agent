---
phase: 5
slug: reference-demo-evaluation
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-15
---

# Phase 5 — Validation Strategy

> Per-phase validation contract. The 4 demo behaviors + the eval are deterministic, hermetic pytest scenarios (StubLLM/StubEmbedder, no network).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run --extra dev pytest -q` |
| **Full suite command** | `uv run --extra dev pytest -q && uv run --extra dev pyright` |
| **Estimated runtime** | ~12 seconds |

---

## Sampling Rate

- **After every task commit:** `uv run --extra dev pytest -q`
- **After every plan wave:** `uv run --extra dev pytest -q && uv run --extra dev pyright`
- **Before `/gsd-verify-work`:** full hermetic suite green (4 demo scenarios + eval + coach smoke)
- **Max feedback latency:** 12 seconds

---

## Per-Task Verification Map

| Requirement | Success Criterion | Test Focus | Automated Command | Status |
|-------------|-------------------|------------|-------------------|--------|
| DEMO-01 | coach runs on the engine (chat + meal loop) | coach module imports + a scripted turn produces a constraint-respecting suggestion | `uv run --extra dev pytest tests/test_demo_coach.py -q` | ✅ green |
| DEMO-02 | cross-session recall | engine#1 states constraint over a persistent store → engine#2 (reopened) recall honors it | `uv run --extra dev pytest tests/test_demo_coach.py -q` | ✅ green |
| DEMO-03 | supersession surfaces valid_until/superseded_by | diet change → old record has valid_until set + superseded_by pointer | `uv run --extra dev pytest tests/test_demo_coach.py -q` | ✅ green |
| DEMO-04 | decay + protected | backdated transient evicted then recovered via expand; pinned allergy survives | `uv run --extra dev pytest tests/test_demo_coach.py -q` | ✅ green |
| DEMO-05 | budget packing + expand | large history packed under token budget; one verbatim expand() | `uv run --extra dev pytest tests/test_demo_coach.py -q` | ✅ green |
| EVAL-02 | before/after baseline | naive full-transcript vs MNEMA recall(budget): containment metrics + token counts; EVAL.md written | `uv run --extra dev pytest tests/test_eval_baseline.py -q` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `SqliteT1.close()` — add `async def close(self): await self._db.close()` (research-flagged gap; needed for the cross-session reopen in DEMO-02)
- [ ] `tests/test_demo_coach.py` — RED stubs for DEMO-01…05 scenarios
- [ ] `tests/test_eval_baseline.py` — RED stubs for EVAL-02 metrics
- [ ] `src/mnema/demo/__init__.py`, `src/mnema/eval/__init__.py` — package markers

*No new dependencies (tiktoken/aiosqlite/sqlite-vec already pinned).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Interactive coach feel | DEMO-01 | Real interactivity is human-judged; the scripted scenario covers correctness | `uv run python -m mnema.demo.coach` — chat, state an allergy, change diet, observe recall |

*All correctness behaviors have deterministic automated coverage; only the interactive feel is manual.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (SqliteT1.close, test stubs, packages)
- [ ] No watch-mode flags
- [ ] Feedback latency < 12s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
