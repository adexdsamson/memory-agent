---
phase: 4
slug: cloud-providers-backends
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-14
---

# Phase 4 — Validation Strategy

> Per-phase validation contract. The conformance suite is the linchpin — local backends run ALWAYS (hermetic gate); cloud/Postgres gated.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio; parametrized conformance suite; testcontainers (gated) |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run --extra dev pytest -q` (local backends only — hermetic) |
| **Full matrix command** | `MNEMA_TEST_PG=1 MNEMA_TEST_DASHSCOPE=1 ... uv run --extra dev --extra cloud pytest -q` (gated, opt-in) |
| **Estimated runtime** | ~10s hermetic; +minutes when cloud/Docker gates are enabled |

---

## Sampling Rate

- **After every task commit:** `uv run --extra dev pytest -q`
- **After every plan wave:** `uv run --extra dev pytest -q && uv run --extra dev pyright`
- **Before `/gsd-verify-work`:** hermetic suite green (conformance on local backends + factory + reindex + cron)
- **Max feedback latency:** 12 seconds (hermetic)

---

## Per-Task Verification Map

| Requirement | Success Criterion | Test Focus | Automated Command | Status |
|-------------|-------------------|------------|-------------------|--------|
| STORE-06 | shared conformance suite, ≥2 backends/axis | parametrized contract per port; local backends always, cloud/PG skip-gated | `uv run --extra dev pytest tests/conformance -q` | ⬜ pending |
| PROV-03 | Qwen LLM + embedder pass conformance | dashscope adapters satisfy Protocols; gated live test | `MNEMA_TEST_DASHSCOPE=1 ... pytest -q` (gated) | ⬜ pending |
| PROV-04 | Anthropic Claude LLM passes conformance | anthropic adapter satisfies LLMProvider; gated live | `MNEMA_TEST_ANTHROPIC=1 ... pytest -q` (gated) | ⬜ pending |
| PROV-05 | Claude-compatible embedder ships | Voyage adapter; independent-axis (claude+voyage) config builds | `uv run --extra dev pytest tests/conformance -q` (mock) | ⬜ pending |
| PROV-07 | embedder switch → reindex, not silent flip | dim-change triggers reindex/migration; startup dim assert | `uv run --extra dev pytest tests/test_reindex.py -q` | ⬜ pending |
| STORE-01 | object store swappable (OSS + local-FS) | ObjectStorePort conformance on LocalFS + moto-S3 (hermetic 2nd) + OSS (gated) | `uv run --extra dev pytest tests/conformance -q` | ⬜ pending |
| STORE-02 | vector store swappable (pgvector + sqlite-vec) | RecordStore+VectorIndex conformance on sqlite-vec always + pgvector (testcontainers-gated) | `uv run --extra dev pytest tests/conformance -q` | ⬜ pending |
| STORE-03 | git-versioned markdown vault | LocalFSVault satisfies VaultStore conformance (already shipped Phase 3) | `uv run --extra dev pytest tests/conformance -q` | ⬜ pending |
| STORE-04 | config-keyed factory wires each axis | build_engine(config) constructs the engine from config keys | `uv run --extra dev pytest tests/test_factory.py -q` | ⬜ pending |
| STORE-05 | local + Qwen/Alibaba configs run end-to-end | local config runs the suite; default config builds (gated live) | `uv run --extra dev pytest tests/test_factory.py -q` | ⬜ pending |
| SCHED-03 | generic cron adapter | cron-string scheduler satisfies Scheduler Protocol | `uv run --extra dev pytest tests/test_cron.py -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — add a `[project.optional-dependencies] cloud` extra: `anthropic`, `dashscope`, `voyageai`, `psycopg[binary,pool]`, `pgvector`, `boto3`; dev: `testcontainers`, `moto[s3]`
- [ ] `tests/conformance/` — parametrized contract suites per port (LLM, embedding, object-store, record/vector, vault, scheduler) with skip-if-unavailable fixtures + safety-invariant assertions
- [ ] `src/mnema/config.py` — Pydantic config model + factory stub
- [ ] `tests/test_factory.py`, `tests/test_reindex.py`, `tests/test_cron.py` — RED stubs

*The conformance suite is the linchpin; build its fixtures + the local-backend parametrization first.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Qwen + Alibaba default config runs end-to-end | STORE-05/PROV-03 | Requires DashScope + OSS credentials | Set `MNEMA_TEST_DASHSCOPE=1 MNEMA_TEST_OSS=1` + creds, run the gated conformance suite |
| pgvector adapter passes conformance on live Postgres | STORE-02 | Requires Docker (testcontainers) | `MNEMA_TEST_PG=1 uv run --extra dev --extra cloud pytest tests/conformance -q` |
| Anthropic / Voyage adapters live | PROV-04/05 | Requires API keys | Set `MNEMA_TEST_ANTHROPIC=1` / `MNEMA_TEST_VOYAGE=1` + keys |

*The hermetic suite (local backends + moto-S3 + sqlite-vec) covers swappability + the safety invariants without network. Cloud/PG paths are gated.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (cloud extra, conformance suite, config/factory, test stubs)
- [ ] No watch-mode flags
- [ ] Feedback latency < 12s (hermetic)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
