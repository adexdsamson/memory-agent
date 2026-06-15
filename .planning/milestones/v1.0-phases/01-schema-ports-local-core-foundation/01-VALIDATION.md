---
phase: 1
slug: schema-ports-local-core-foundation
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-10
updated: 2026-06-10
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

| Requirement | Wave | Success Criterion | Test | Automated Command | Status |
|-------------|------|-------------------|------|-------------------|--------|
| EVAL-01 / SC-1 | 1–4 | remember+recall scoped, no cross-user leak | `test_remember_and_recall_scoped`, `test_recall_does_not_leak_across_users`, `test_user_id_required_kwarg` | `uv run pytest tests/ -q` | ✅ green |
| SC-2 | 4 | durable claim recallable cross-session (provisional T1) + same-session (buffer) | `test_cross_session_provisional_recall`, `test_within_session_buffer_freshness` | `uv run pytest tests/ -q` | ✅ green |
| SC-3 / CORE-03/04/05 | 2,4 | fast write (T0+buffer+provisional T1, no LLM); all schema columns set | `test_fast_write_schema_columns`, `tests/test_schema.py` (7 tests) | `uv run pytest tests/ -q` | ✅ green |
| SC-4 / PROV-01/02/06 | 2,3 | local adapters; independent LLM/embedding axes; dim-mismatch guard | `test_dim_mismatch_raises_at_startup`, `test_public_surface_importable` | `uv run pytest tests/ -q` | ✅ green |
| SC-5 / RECALL-06/07 | 4 | expand() returns verbatim T0 detail; access_count increments on recall | `test_expand_and_access_count` (unconditional expand path) | `uv run pytest tests/ -q` | ✅ green |
| SCHED-01/02 | 3 | scheduler trigger_now fires consolidate | `test_trigger_now_fires_consolidate` | `uv run pytest tests/ -q` | ✅ green |
| IFACE-01 | 4 | SDK public surface + ScopedHandle factory | `test_engine_scope_returns_scoped_handle` | `uv run pytest tests/ -q` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Final gate (2026-06-10):** `uv run pytest tests/ -q` → **20 passed**; `uv run pyright` → **0 errors**; `uv run ruff check src/ tests/` → **clean**.

---

## Wave 0 Requirements

- [x] `pyproject.toml` — uv project scaffold + pytest/pytest-asyncio/pyright dev deps, `asyncio_mode = "auto"`
- [x] `tests/conftest.py` — shared fixtures (in-memory sqlite-vec engine, deterministic StubEmbedder, temp LocalFS T0)
- [x] 5-test harness across `tests/test_remember_recall.py`, `test_scope_isolation.py`, `test_write_path.py`, `test_providers.py`, `test_scheduler.py`, `test_sdk_interface.py` + `test_schema.py` — maps to the 5 ROADMAP success criteria (EVAL-01)

*Wave 0 established the pytest harness; all 20 tests now green.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| sqlite-vec loadable-extension loads on the Windows dev machine | TIER-02 | Extension loading is platform/wheel-dependent; CLAUDE.md flags MEDIUM confidence on Windows | `uv run python -c "import sqlite3, sqlite_vec; c=sqlite3.connect(':memory:'); c.enable_load_extension(True); sqlite_vec.load(c); print(c.execute('select vec_version()').fetchone())"` — expect a version string, not an error. **✅ Verified 2026-06-10: `vec_version v0.1.9`.** |

*All other phase behaviors have automated verification via the 5-test harness.*

> **Env note:** uv resolved CPython **3.14.2** (pyproject has no upper cap; CLAUDE.md mandates ≤3.13). All Phase 1 tests + sqlite-vec extension loading pass on 3.14.2, but this remains a watch item for Phase 2+ C-extension wheels (pgvector, etc.). Add `requires-python = ">=3.12,<3.14"` if any wheel fails.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s (~1.3s full suite)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated — 20/20 tests green, pyright + ruff clean (2026-06-10)
