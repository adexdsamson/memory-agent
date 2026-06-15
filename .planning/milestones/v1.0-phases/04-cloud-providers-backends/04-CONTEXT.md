# Phase 4: Cloud Providers & Backends - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous) — all four grey areas **Accepted as recommended**. Locked for planning; Claude's discretion on tuning/impl details provided the requirement guarantees (PROV-03/04/05/07, STORE-01..06, SCHED-03) and Phase 1–3 locked decisions hold.

<domain>
## Phase Boundary

Real cloud providers and storage backends land behind the EXISTING ports (no Protocol changes — D-07/D-08), each gated by a **shared conformance suite**, with a **config-keyed factory** wiring the documented default (Qwen + Alibaba) and a fully-local config. Covers: Qwen/DashScope LLM+embedder, Anthropic Claude LLM, Voyage (Claude-compatible) embedder, Alibaba OSS object store, Postgres+pgvector vector store, git-versioned markdown vault, a generic cron scheduler, the config factory, and the embedder-switch reindex path.

**Out of scope:** the nutrition-coach demo + eval baseline (Phase 5); hybrid retrieval (HYBRID-01/02/03) and extra providers OpenAI/Ollama (PROV-08) remain later/additive.

**Hard constraint (load-bearing):** the **CI phase gate stays hermetic** — local backends run always; cloud + Postgres adapters are implemented and verified by the SAME conformance suite but **skip cleanly when credentials/Docker are absent**. "Done" for Phase 4 = adapters shipped + conformance suite green on local backends + cloud/Postgres paths verified when creds/Docker present (gated, not required).
</domain>

<decisions>
## Implementation Decisions

### Area 1 — Conformance suite + CI strategy (STORE-06) [Accepted: ship + gate]
- **D4-01:** A **parametrized pytest conformance suite** — one contract per port (LLMProvider, EmbeddingProvider, ObjectStorePort, RecordStore+VectorIndex, VaultStore, Scheduler) — runs across whichever backends are available.
- **D4-02:** **CI hermeticity:** local backends (sqlite-vec, LocalFS, markdown vault, StubLLM, StubEmbedder) run ALWAYS and are the phase gate. Cloud/Postgres backends are **credential/Docker-gated** with `pytest.skip` when unavailable. The phase gate NEVER requires network.
- **D4-03:** "≥2 backends per axis" (STORE-06): satisfied in CI where two local-capable backends exist; for axes with one local backend the 2nd is gated (Postgres via testcontainers if Docker; OSS via creds). Document the gating in the suite + SUMMARY.
- **D4-04:** Real-API tests are **opt-in via env vars** (`MNEMA_TEST_DASHSCOPE=1`, `MNEMA_TEST_ANTHROPIC=1`, `MNEMA_TEST_VOYAGE=1`, `MNEMA_TEST_OSS=1`, `MNEMA_TEST_PG=1`); never required for the gate.

### Area 2 — Cloud LLM/embedding adapters (PROV-03/04/05/06) [Accepted: direct SDKs]
- **D4-05:** Implement via **direct official SDKs** — `anthropic` (Claude LLM), `dashscope` (Qwen LLM + Qwen embedder), `voyageai` (Voyage embedder) — each behind the existing `LLMProvider`/`EmbeddingProvider` Protocols. Lean deps; LiteLLM NOT used (keeps the independent-axis contract explicit).
- **D4-06:** Claude-compatible embedder (PROV-05) = **Voyage `voyage-3.5`** (primary); an optional local sentence-transformers embedder may ship if cheap. Independent embedding axis confirmed (llm=anthropic + embedder=voyage is a first-class config).
- **D4-07 (PROV-06):** Embeddings are **L2-normalized at the adapter**; the startup dim assertion (already enforced in MemoryEngine) gates mismatch.
- **D4-08:** Adapters carry retry/timeout; the conformance contract uses a mock transport for hermetic runs, real calls gated (D4-04). Sync SDKs wrapped in `asyncio.to_thread` at the leaf (D-13).

### Area 3 — Postgres+pgvector backend (STORE-02) [Accepted: ship + gate]
- **D4-09:** Postgres+pgvector adapter via **psycopg3 async**, satisfying the same `RecordStore`+`VectorIndex` Protocols as SqliteT1; **HNSW index + partial index `WHERE valid_until IS NULL`** for live-record filtering; pin pgvector ≥0.8.2 (CVE).
- **D4-10:** Live run uses **testcontainers-pgvector when Docker is available; skips cleanly otherwise** (this env likely lacks Docker). Parity with sqlite-vec proven by the shared conformance suite running on both when possible.
- **D4-11:** Ship the adapter + conformance; **gate the live run** rather than blocking the phase on a live Postgres here.

### Area 4 — Config factory + reindex + cron (STORE-04/05, PROV-07, SCHED-03) [Accepted: all]
- **D4-12:** A **Pydantic config model** + **config-keyed factory** (`build_engine(config)`) wiring each of the six axes from configuration (e.g. `{"llm":"qwen","embedder":"voyage","vector":"pgvector","object_store":"oss","vault":"markdown","scheduler":"cron"}`).
- **D4-13:** Two documented configs (STORE-05): **fully-local** (always-on, runs the suite end-to-end) and **Qwen+Alibaba default** (credential-gated). Both drive the same suite.
- **D4-14 (PROV-07):** Switching embedders/dim triggers an **explicit reindex/migration path** (re-embed all live records into the new vector column/table) — refusing a silent config flip; the startup dim assertion is the backstop.
- **D4-15 (SCHED-03):** A **generic cron-string adapter** behind the `Scheduler` Protocol (cron expression → scheduled consolidate), alongside the existing InProcessScheduler.

### Carried-forward locked decisions
- D-07/D-08/D-10 segregated Protocols, static-checked, NEW adapters add zero Protocol changes; D-11 async; D-13 sync-SDK containment via `asyncio.to_thread`; the independent LLM/embedding axes are the whole point (PROV-05/D4-06); never hard-delete; protected/CONS-08 guarantees intact. The conformance suite must include the safety invariants (a protected record survives + is recoverable) on every backend.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- All six port Protocols exist (`src/mnema/ports/`): the cloud adapters implement them unchanged.
- `src/mnema/adapters/`: embedding/ (StubEmbedder), llm/ (StubLLM), object_store/ (LocalFS), scheduler/ (InProcessScheduler), vault/ (LocalFSVault), vector_store/ (SqliteT1) — the local backends + stubs that anchor the conformance suite and CI.
- `src/mnema/adapters/vector_store/sqlite_t1.py` — the reference RecordStore+VectorIndex impl the pgvector adapter must match (DDL, partial index, supersede(), find_by_t0_ref(), delete_vector()).
- `src/mnema/core/engine.py` — MemoryEngine constructor is the wiring target for the config factory; dim assertion already present (PROV-06 backstop).
- No config module or factory yet — `src/mnema/config.py` + a factory are new.
- No conformance/contract test harness yet — new `tests/conformance/` (or `tests/test_conformance_*.py`).

### Established Patterns
- Async Protocol + structural-typing adapters; pyright strict; pytest-asyncio; hermetic stubs; `uv run --extra dev`; never hard-delete.
- New deps (runtime, behind optional extras to keep the local install lean): `anthropic`, `dashscope`, `voyageai`, `psycopg[binary,pool]`, `pgvector`, `boto3` (OSS/S3); dev: `testcontainers`. Consider grouping cloud deps under an optional extra (e.g. `[project.optional-dependencies] cloud = [...]`) so the laptop/local path stays minimal.

### Integration Points
- Config factory wires MemoryEngine; conformance suite parametrizes over backend fixtures; reindex path touches the vector store + a migration entrypoint; cron adapter behind Scheduler.

### Open code-review carryover
- Phase 1/2/3 deferred todos (`.planning/todos/pending/phase-0{1,2,3}-code-review-deferred.md`) — fold relevant items (e.g. provider error handling) if convenient.
</code_context>

<specifics>
## Specific Ideas
- The **conformance suite is the linchpin** — it is what proves "swappable behind a port" and must assert the safety invariants (protected survives, eviction recoverable, scope isolation) on EVERY backend, not just the happy path.
- Keep cloud deps behind an optional `cloud` extra so `uv sync` (local/laptop path) stays lean and the "runs on a plane" thesis holds.
- The default-stack proof (Qwen + Alibaba) is the canonical hackathon submission path — the config + suite must make it a one-config-flip run when creds are present.
</specifics>

<deferred>
## Deferred Ideas
- Hybrid retrieval (BM25 + graph + RRF) — HYBRID-01/02/03 (KeywordIndex/GraphStore/HybridSearch Protocols), a later additive phase.
- Extra providers OpenAI / Ollama (PROV-08).
- The nutrition-coach demo + before/after eval baseline (Phase 5).
- HTTP/SSE MCP transport.
</deferred>
