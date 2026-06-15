---
phase: 2
slug: consolidation-supersession
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-13
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] (from Phase 1) |
| **Quick run command** | `uv run --extra dev pytest -q` |
| **Full suite command** | `uv run --extra dev pytest -q && uv run --extra dev pyright` |
| **Estimated runtime** | ~5 seconds (hermetic StubLLM + StubEmbedder + in-memory sqlite-vec) |

---

## Sampling Rate

- **After every task commit:** Run `uv run --extra dev pytest -q`
- **After every plan wave:** Run `uv run --extra dev pytest -q && uv run --extra dev pyright`
- **Before `/gsd-verify-work`:** Full suite green (consolidation + supersession + decay tests + type check)
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

> Populated by the planner. Each Phase 2 requirement maps to a deterministic test exercised against StubLLM + StubEmbedder (no network).

| Requirement | Success Criterion | Test Focus | Automated Command | Status |
|-------------|-------------------|------------|-------------------|--------|
| CONS-01 | drains staging queue, extracts typed records via (stub) LLM | extraction yields 0..N typed records from drained turns | `uv run --extra dev pytest tests/test_consolidation.py -q` | ⬜ pending |
| CONS-02 | judges salience; safety/medical pinned `protected` | safety content → protected=True + salience 1.0 via content rule, not LLM | `uv run --extra dev pytest -q` | ⬜ pending |
| CONS-03 | entity resolution: same subject + predicate | dense cosine match (L2-dist threshold) finds the near record | `uv run --extra dev pytest -q` | ⬜ pending |
| CONS-04 | contradiction actively superseded (valid_until + superseded_by + supersedes edge, one txn) | seeded contradiction → old record superseded atomically | `uv run --extra dev pytest -q` | ⬜ pending |
| CONS-05 | non-contradicting refinement merged in place | refinement updates existing record, no new live record | `uv run --extra dev pytest -q` | ⬜ pending |
| CONS-06 | provisional reconciled by `t0_ref`, flag cleared, no duplicate | provisional upgraded in place; one live record | `uv run --extra dev pytest -q` | ⬜ pending |
| CONS-07 | idempotent re-run (no dup live records, no dangling pointers) | run consolidate twice → identical live set | `uv run --extra dev pytest -q` | ⬜ pending |
| CONS-08 | protected/FACT never auto-superseded on LLM contradiction alone | seeded contradiction on protected record → stays live, contradiction_pending edge | `uv run --extra dev pytest -q` | ⬜ pending |
| FORG-01 | decay pass computes keep_score over all live records | pure keep_score(recency, reinforcement, salience) deterministic values | `uv run --extra dev pytest tests/test_decay.py -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_consolidation.py` — extraction, reconcile-by-t0_ref, idempotency, supersession, merge stubs
- [ ] `tests/test_supersession.py` (or in test_consolidation.py) — CONS-04 atomic supersede + CONS-08 protected guard (seeded contradiction)
- [ ] `tests/test_decay.py` — keep_score pure-function value assertions (FORG-01)
- [ ] `tests/conftest.py` — extend with StubLLM fixture + seeded consolidation fixtures
- [ ] `src/mnema/adapters/llm/stub.py` — deterministic StubLLM (Wave 0 dependency for all extraction tests)

*Framework already installed (Phase 1) — Wave 0 here adds StubLLM + the consolidation/decay test files.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| (none) | — | All Phase 2 behavior is deterministic + hermetic (StubLLM/StubEmbedder) | — |

*All phase behaviors have automated verification — determinism is a hard Phase 2 constraint.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (StubLLM + test files)
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
