---
phase: 1
slug: schema-ports-local-core-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | none — Wave 0 installs (`pyproject.toml` [tool.pytest.ini_options], `asyncio_mode = "auto"`) |
| **Quick run command** | `uv run pytest -q` |
| **Full suite command** | `uv run pytest -q && uv run pyright` |
| **Estimated runtime** | ~10 seconds (hermetic stub embedder, local sqlite-vec) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q`
- **After every plan wave:** Run `uv run pytest -q && uv run pyright`
- **Before `/gsd-verify-work`:** Full suite must be green (5-test harness + type check)
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

> Populated by the planner during PLAN.md authoring. Each task that produces verifiable behavior maps to an automated command. The 5-test harness (EVAL-01) covers the 5 ROADMAP success criteria.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD by planner | — | — | EVAL-01 | — | scope isolation never leaks across user_id | unit | `uv run pytest tests/test_harness.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — uv project scaffold + pytest/pytest-asyncio/pyright dev deps, `asyncio_mode = "auto"`
- [ ] `tests/conftest.py` — shared fixtures (in-memory/temp sqlite-vec engine, deterministic stub EmbeddingProvider, temp LocalFS T0)
- [ ] `tests/test_harness.py` — 5-test stubs mapping to the 5 ROADMAP success criteria (EVAL-01)

*Framework not yet installed — Wave 0 establishes the pytest harness this greenfield phase depends on.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| sqlite-vec loadable-extension loads on the Windows dev machine | TIER-02 | Extension loading is platform/wheel-dependent; CLAUDE.md flags MEDIUM confidence on Windows | `uv run python -c "import sqlite3, sqlite_vec; c=sqlite3.connect(':memory:'); c.enable_load_extension(True); sqlite_vec.load(c); print(c.execute('select vec_version()').fetchone())"` — expect a version string, not an error |

*All other phase behaviors have automated verification via the 5-test harness.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
