# Project Research Summary

**Project:** MNEMA
**Domain:** Portable, provider-agnostic AI agent memory engine (MCP server + embeddable SDK)
**Researched:** 2026-06-10
**Confidence:** HIGH (stack/architecture/pitfalls verified against current docs, papers, and the project's own build plan; FEATURES consumer-expectation framing is MEDIUM-HIGH)

## Executive Summary

MNEMA is a tiered, dual-phase agent memory engine whose differentiator is not any single memory trick but the **combination of provable safety (a protected fact can never be forgotten), active supersession (the agent never acts on a stale preference), budget-aware recall, and full provider portability** — LLM, embedding, storage, and compute each behind a swappable adapter. Every comparable system (Mem0, Zep/Graphiti, Letta, MemoryOS) already ships scoping, CRUD+search, change history, and an MCP/SDK surface; those are table stakes. The way experts build this class of system is a **hexagonal (ports & adapters) core**: a backend-agnostic orchestrator depending only on abstract ports, with concrete adapters wired at a single config-keyed composition root (Mem0's factory + dual-surface pattern, LiteLLM's provider unification, LlamaIndex's independent storage ports, Zep's bitemporal *semantics* without its Neo4j backend).

The single most load-bearing finding, agreed by all four researchers, is the **inside-out build order**: write the record schema first, then the six port Protocols, then in-memory/local reference adapters, and build and test the *entire core* (write path, recall, consolidation, forgetting) against those local adapters **before any cloud or provider code exists**. This is what makes portability mechanical rather than aspirational — the core is provably backend-agnostic by the time the first cloud adapter lands, and the local stack (local-embed + sqlite-vec + LocalFS + APScheduler) doubles permanently as the CI/laptop/demo path. The recommended language is **Python 3.12+** (both mandatory provider SDKs — `anthropic`, `dashscope` — plus the de-facto MCP framework `fastmcp` are Python-first), with **pgvector** (cloud default) and **sqlite-vec** (local) behind one `VectorStore` port, and **hand-rolled adapter Protocols** rather than LiteLLM-as-the-public-seam (LiteLLM is fine *inside* default adapters, but coupling LLM+embedding under one client would kill the independent-axis requirement).

The two highest-risk areas, also agreed across researchers, are (1) the **consolidation correctness surface** — entity resolution, contradiction detection, and reconciling provisional records by `t0_id` identity — where false supersession could retire a still-valid safety constraint and concurrency could produce duplicate/dangling records; and (2) the **embedding axis as a first-class provider axis** — dimension and normalization are model properties that leak into the vector schema, so an embedder swap must be treated as a reindex migration (provenance columns, dim fixes the vector column, normalize-at-adapter). Critically, the safety guarantee must be enforced **structurally** — an explicit `protected` flag skipped *before* any decay-score math, proven by an invariant test — not by a probabilistic LLM salience score. Mitigation throughout is narrow port contracts plus a conformance test suite every adapter must pass.

## Key Findings

### Recommended Stack

The engine is Python-first because the two mandatory provider SDKs (`anthropic`, `dashscope`) and the dominant MCP framework (`fastmcp`) all live there, as does the richest embedding/vector ecosystem. The portability contract is enforced by **hand-rolled narrow Protocols** for each axis; LiteLLM may be used *inside* default LLM adapters for retry/cost plumbing but must never appear in MNEMA's public API. Two reference configs exist from day one: a **cloud default** (Qwen/DashScope for both LLM + embeddings, Postgres+pgvector, Alibaba OSS via boto3 S3-compat, Function Compute scheduler) and a **fully-local** stack (local `bge-m3`/`nomic` embeddings via sentence-transformers, sqlite-vec, LocalFS, APScheduler in-process). See STACK.md.

**Core technologies:**
- **Python 3.12+** — implementation language — both mandatory SDKs + FastMCP are Python-first; richest vector/embedding ecosystem.
- **fastmcp 3.4.2** (on `mcp` 1.12.4) — MCP server framework — de-facto standard; same decorated functions back both the MCP server and the SDK.
- **PostgreSQL 16/17 + pgvector >= 0.8.2** — default T1 store (relational + `tsvector` FTS + vector + adjacency table) — one engine gives all three indexes; pin >= 0.8.2 for CVE-2026-3172; HNSW iterative scan makes `valid_until IS NULL` filtered search reliable.
- **sqlite-vec** — local/embeddable vector index — zero-dependency, runs in CI/on a laptop; the permanent local test backend.
- **anthropic 0.107.1 / dashscope** — the two v1 LLM adapters (Claude reasoning, Qwen flash-curate + plus-reason).
- **voyageai (`voyage-3.5`)** — the canonical answer to "Claude ships no embedder" (Anthropic's officially recommended partner); local `bge-m3`/`nomic` is the zero-cost offline option.
- **Hybrid retrieval = native `tsvector` + pgvector + hand-rolled RRF (k=60), ranks only** — portable across pgvector and sqlite-vec; do NOT depend on `pg_search`/ParadeDB for the default path (absent on Alibaba RDS and SQLite).

### Expected Features

Competitor convergence (FEATURES.md) confirms scoping, CRUD+search, change history, and MCP/SDK are table stakes — MNEMA's edge is elsewhere, aligned to Core Value.

**Must have (table stakes):**
- Tenant/scope isolation (`user_id`/`agent_id`/`session_id`) — foundational, threads into every table and `WHERE`; retrofitting is a rewrite.
- `remember`/`recall`/`forget`/`expand` (+ `consolidate`) on both MCP and SDK — the integration surface; SDK is the source of truth, MCP is a thin wrapper.
- Typed records + metadata, dense semantic recall, async/non-blocking write path, some provider/backend config.

**Should have (differentiators — MNEMA's edge):**
- **Salience floor — provably unforgettable protected facts** — no competitor guarantees this by construction; the safety story.
- **Active supersession without the Neo4j tax** — Zep-grade `valid_until`/`superseded_by` on a Postgres adjacency table; the lead demo.
- **Full provider portability (LLM ⊥ embedding ⊥ storage ⊥ compute)** — the independent LLM/embedding axis (Claude reasoning + Qwen embeddings) is rare; the central modification.
- **Budget-aware recall** (RRF-fused hybrid → re-rank → greedy pack under a token budget, `expand(id)` for verbatim) + **dual-phase write** (provisional closes the read-after-write hole) + **tiered T0/T1/T2 git-versioned vault** + **recoverable eviction**.

**Defer (v2+):**
- Hybrid recall (BM25 + 1-hop graph + RRF) is the v1.x upgrade over dense-only; T2 git vault, extra storage/compute adapters, richer metadata filtering, `list`/`get` inspection follow.
- Public benchmark (LongMemEval/LoCoMo), cross-tenant/shared memory, multi-modal, autonomous self-editing — all v2+ or explicitly out of scope (autonomous edits conflict with provable forgetting).

### Architecture Approach

Hexagonal core: `core/` imports only from `ports/` (six Protocols: LLM, Embedding, ObjectStore, VectorStore, Vault, Scheduler), `adapters/` are grouped by axis (the only place a vendor SDK is imported), and a config-`type`-keyed `from_config()` factory is the single composition root. Two driving surfaces — the SDK (which *is* the core `MemoryEngine`) and a ~50-line MCP translation layer — sit over the same core. Domain logic (RRF fusion, salience floor, supersession, budget packer) lives only in `core/`; surfaces translate and adapters do I/O only. An import lint rule ("core may not import adapters or vendor SDKs") makes the seam mechanical. See ARCHITECTURE.md.

**Major components:**
1. **MemoryEngine (core API / SDK)** — public typed `remember/recall/forget/consolidate/expand`; owns no I/O.
2. **WritePath + RecentSessionBuffer** — fast online write: append T0, push buffer, optional single-embedding provisional T1 upsert, enqueue staging.
3. **ConsolidationPipeline** — slow offline: extract → judge salience → entity-resolve → merge/supersede/confirm (reconcile provisional by `t0_id`) → decay → promote to T2.
4. **RecallPath** — hybrid retrieve (dense+BM25+graph), RRF fuse, union buffer (buffer-wins dedupe), salience/recency re-rank, budget-aware two-pass pack.
5. **Six ports + per-axis adapters + factory** — the swappable seam; EmbeddingPort exposes `dim` so the core provisions the vector column.

### Critical Pitfalls

1. **Salience floor fails silently — guarantee asserted, not proven.** Make `protected` a **structural boolean** set by deterministic classification, skipped as the *first line* of the decay loop *before* any score math; the salience floor is only a backstop. Prove with an **invariant/property test** ("no `protected` record is ever archived under any decay input"), not an example. Forbid any hard-delete path and any merge that lowers protected salience.
2. **Embedding axis silently couples to one embedder (dimension/normalization lock-in).** Store provenance (`embedding_model`/`embedding_dim`/`embedding_version`), normalize-at-adapter to unit vectors so the core sees one distance operator, assert dim at startup, and treat an embedder swap as a **reindex migration** (provide a `reindex()` path) — never a config flip.
3. **Consolidation race / false supersession (highest domain risk).** Reconcile provisional records **by `t0_id` identity, upgrading in place** (never re-extract into a parallel record); make consolidation idempotent + single-writer per subject. Separate "same subject+predicate?" (entity resolution) from "does it contradict?" (supersession); **never auto-supersede a protected/`fact` type on an LLM contradiction alone** — require explicit `forget`. Set `valid_until`/`superseded_by` in the same transaction; no dangling pointers.
4. **Leaky provider/storage abstraction — backend quirks bleed into core.** Define ports by capabilities/guarantees, not the default backend's behavior; consume **ranks not scores** from retrieval adapters; ship a **conformance suite** every adapter must pass on >=2 backends/axis (pgvector+sqlite-vec, OSS+LocalFS). No backend name may appear in core.
5. **Freshness hole + RRF/budget critical-constraint loss.** Buffer-wins dedupe; bias `looks_like_durable_claim` toward recall; apply `valid_until IS NULL` uniformly across dense/BM25/graph; **two-pass budget packer** that packs protected/active constraints first, then RRF-relevance fill (adversarial test: large off-topic history must still surface the allergy within budget). Plus eval/demo discipline: custom 5→20 harness first, never demo wall-clock decay (seed backdated timestamps), always show the supersession *mechanism* (`valid_until`+`superseded_by`), not just the chat outcome.

## Implications for Roadmap

Research points to a strict **inside-out** structure. Phases 1-2 build the portable core with zero cloud dependencies; only then do real cloud adapters land. The build-plan milestones (W1-W4) map onto these phases. The local stack is not throwaway — it is the permanent CI/laptop/demo backend.

### Phase 1: Schema, Ports & Local Core Foundation (W1)
**Rationale:** Every component references the Record type; the six Protocols depend only on schema; in-memory/local adapters let the entire core be built and tested with zero cloud deps. Scope isolation and the structural `protected` flag and embedding-provenance columns must be in the schema *before any data is written* — retrofitting any of them is a rewrite. This is the load-bearing inside-out order.
**Delivers:** `core/schema.py`; six port Protocols; local reference adapters (LocalFS object store, in-memory/sqlite-vec vector store, in-process scheduler); WritePath + RecentSessionBuffer + dense recall; the first 5-test custom harness.
**Addresses:** scope isolation, `remember`/`recall(dense)`, T0+buffer, within-session freshness (table stakes + freshness differentiator).
**Avoids:** Pitfall 1 (`protected` + provenance columns foundational), Pitfall 2 (capability-defined ports from day one), Pitfall 7 (within-session freshness test), Pitfall 10 (custom harness first).

### Phase 2: Consolidation, Supersession & Hybrid Recall (W2)
**Rationale:** The highest domain-risk surface. Consolidation produces salience, entity resolution, and supersession; provisional reconciliation by `t0_id` closes the cross-session freshness hole; hybrid RRF + uniform `valid_until` filter make recall correct. Still built against local adapters.
**Delivers:** ConsolidationPipeline (extract/salience/entity-resolve/merge/supersede, reconcile provisional in place); active supersession (`valid_until`/`superseded_by`); BM25 + 1-hop graph + RRF (ranks-only, k=60); conformance suite running on >=2 backends/axis; expanded invariant tests.
**Implements:** ConsolidationPipeline + RecallPath hybrid; the adjacency-table graph inside VectorStorePort.
**Avoids:** Pitfall 3 (per-provider retry, fast path never blocks on reasoning model — fast-path boundary also from W1), Pitfall 4 (idempotent, identity-based reconciliation), Pitfall 5 (separate ER from contradiction; protected carve-out from auto-supersession), Pitfall 8/9 (ranks-only RRF, uniform live filter).

### Phase 3: Forgetting, Salience Floor, Budget Packer & MCP (W3)
**Rationale:** Forgetting + the provable safety guarantee + the budget packer are the headline differentiators; they depend on consolidation existing. The MCP surface is a thin translator over the now-complete core.
**Delivers:** decay pass with structural `protected` skip + salience floor backstop + recoverable eviction; two-pass budget packer (protected-first) with summary injection + `expand(id)`; recency/salience re-rank tuning; MCP server; before/after baseline on the harness.
**Avoids:** Pitfall 6 (invariant test that no `protected` record is ever archived; merge can't lower protected salience; no hard-delete path), Pitfall 8 (protected-first two-pass packer, adversarial budget test).

### Phase 4: Cloud Adapters & Configuration (real Qwen + Alibaba + Claude/Voyage)
**Rationale:** Only now, with a provably backend-agnostic core, do real cloud adapters land — each swap-tested against the same conformance + core suites the local adapters already pass. The factory wires what exists.
**Delivers:** Qwen LLM + Qwen embedder + Anthropic LLM + Voyage embedder adapters; Postgres+pgvector adapter (HNSW + tsvector/GIN + adjacency + partial index); Alibaba OSS/S3 adapters; Function Compute scheduler; git markdown VaultPort (T2 promotion); config system with documented default (Qwen+Alibaba) and the fully-local config; `reindex()` migration path.
**Uses:** STACK.md — pgvector >= 0.8.2, dashscope, anthropic+voyageai, boto3 S3-compat, psycopg 3.
**Avoids:** Pitfall 1 (reindex path + startup dim-assert), Pitfall 2 (conformance suite gates each new adapter), Pitfall 3 (per-adapter retry taxonomy).

### Phase 5: Reference Demo & Eval (W4)
**Rationale:** The nutrition coach consumes the SDK only — proving the seam holds — and the eval harness validates any adapter combo. Demo discipline (seeded backdated timestamps, surface supersession mechanism) was designed into W2-W3 fixtures.
**Delivers:** nutrition-coach demo (cross-session recall, supersession lead, seeded decay + surviving protected fact, budget packing); grown 20+ test suite; before/after baseline writeup; one public benchmark (LongMemEval/LoCoMo) **only as a stretch, gated behind everything else**.
**Avoids:** Pitfall 10 (own numbers + methodology, no "beat 96.6%"), Pitfall 11 (no wall-clock decay; show mechanism not just outcome; protected fact visibly survives).

### Phase Ordering Rationale

- **Dependencies (inside-out):** schema → ports → local adapters → core orchestrators → cloud adapters → surfaces → demo/eval. The core is provably portable *before* the first cloud adapter exists, not hopefully after. All four researchers independently surfaced this as the single most load-bearing finding.
- **Risk-front-loading:** the hardest correctness surface (consolidation/supersession/provisional reconciliation, Phase 2) and the safety guarantee (Phase 3) land while the system is small and fully local/deterministic — cheaper to test invariants on seeded fixtures than against cloud backends.
- **Foundational-first:** scope isolation, the structural `protected` flag, and embedding-provenance columns are all schema-level and must exist in Phase 1; each is a rewrite if retrofitted.
- **Portability as a gate, not a hope:** the conformance suite (Phase 2 onward) means an adapter that hasn't passed is not a supported backend; cloud adapters (Phase 4) must pass the same suite the local ones do.

### Research Flags

Phases likely needing deeper research during planning (`/gsd-research-phase`):
- **Phase 2 (Consolidation/Supersession):** highest domain risk — entity-resolution thresholds, contradiction-vs-refinement distinction, idempotency/locking strategy, and the provisional→confirmed reconciliation state machine are novel to MNEMA's design and corroborated only at MEDIUM confidence. The protected-carve-out rule and RRF `k` sensitivity also warrant a focused look.
- **Phase 4 (Cloud Adapters):** verify a few stack edge cases flagged at MEDIUM — sqlite-vec extension loading on Windows demo machines, exact `dashscope`/`voyageai`/`litellm` pins at `uv lock` time, and whether native `tsvector` RRF is "good enough" vs true BM25 on keyword-heavy recall (focused eval if recall underperforms).

Phases with standard patterns (can skip research-phase):
- **Phase 1 (Schema/Ports/Local Core):** hexagonal ports & adapters, Protocol-based seams, and factory composition root are well-documented and verified against Mem0/LlamaIndex/LiteLLM.
- **Phase 3 (MCP surface):** FastMCP decorator-to-tool mapping is a thin, well-trodden translation layer. (The salience-floor *invariant test* itself is novel but the mechanism is simple and structural.)
- **Phase 5 (Demo/Eval):** the custom harness and demo discipline come directly from the build plan's own hard-won guidance.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core picks (Python, FastMCP 3.4.2/mcp 1.12.4, pgvector 0.8.2, anthropic 0.107.1, Voyage-for-Claude) verified against PyPI/official docs Jun 2026. MEDIUM only on fast-moving exact pins and sqlite-vec on Windows. |
| Features | MEDIUM-HIGH | Competitor capabilities verified via official docs + papers (Mem0, Zep, Letta, MemoryOS); consumer-expectation framing synthesized from cross-product convergence. |
| Architecture | HIGH | Pattern lineage verified against Mem0, LiteLLM, LlamaIndex, Zep/Graphiti; internals are the project's own build-plan spec. |
| Pitfalls | HIGH | Provider-abstraction, retrieval, and eval/demo traps verified against current docs/papers and the build plan; MEDIUM on the consolidation race-condition specifics (MNEMA's provisional design is novel). |

**Overall confidence:** HIGH

### Gaps to Address

- **Consolidation correctness specifics (MEDIUM):** entity-resolution match thresholds, the contradiction-vs-refinement boundary, and the concurrency/locking model are the riskiest, least-externally-validated area. Handle via Phase 2 deep research + invariant tests on seeded fixtures before trusting auto-supersession.
- **RRF `k` and tsvector-vs-true-BM25 (MEDIUM):** RRF is parameter-sensitive and native `ts_rank` is not true BM25. Treat `k` as a documented, tested constant; add a focused keyword-recall eval and only adopt ParadeDB as an optional adapter if recall underperforms.
- **Token counting (MEDIUM):** Claude's tokenizer != tiktoken; use the configured provider's official counter or budget conservatively with a margin. Resolve when the budget packer lands (Phase 3).
- **sqlite-vec on Windows + fast-moving pins (MEDIUM):** verify the wheel ships the extension for Windows demo machines and resolve exact `dashscope`/`voyageai`/`litellm` versions at `uv lock` time rather than from the research doc. Resolve in Phase 4.
- **Tension noted (not a blocker):** provider portability multiplies the integration/test matrix combinatorially — the agreed mitigation (narrow port contracts + conformance suite + ranks-not-scores) is sound, but the test-matrix cost is real and should be scoped explicitly in Phases 2 and 4.

## Sources

### Primary (HIGH confidence)
- `mnema-build-plan.md` + `.planning/PROJECT.md` — tier definitions, v2 record schema, two-phase + recall pseudocode, MCP contracts, eval/demo discipline (project's own authoritative spec).
- Context7 `/modelcontextprotocol/python-sdk` + https://pypi.org/project/fastmcp/ + https://jlowin.dev/blog/fastmcp-3 — FastMCP 3.4.2 / mcp 1.12.4.
- https://pypi.org/project/anthropic/ + https://platform.claude.com/docs/en/build-with-claude/embeddings — anthropic 0.107.1; Claude ships no embedder, recommends Voyage.
- https://pypi.org/project/dashscope/ + https://www.alibabacloud.com/help/en/model-studio/embedding — DashScope SDK + text-embedding-v4.
- https://www.postgresql.org/about/news/pgvector-082-released-3245/ + pgvector CHANGELOG — 0.8.2, CVE-2026-3172, halfvec, HNSW iterative scan.
- https://blog.voyageai.com/2025/05/20/voyage-3-5/ + https://docs.voyageai.com/docs/embeddings — voyage-3.5 dims/pricing.
- DeepWiki Mem0 overview; LiteLLM docs + DeepWiki completion/embedding; LlamaIndex Storing/StorageContext — hexagonal core, factory, dual surface, independent storage ports.
- Zep arXiv 2501.13956 + Graphiti repo — bitemporal supersession semantics (kept without Neo4j).
- https://github.com/asg017/sqlite-vec — embeddable local vector index.

### Secondary (MEDIUM confidence)
- Mem0 paper (arXiv 2504.19413), MemoryOS paper (arXiv 2506.06326), Letta/MemGPT docs, Simon Willison Claude/ChatGPT memory comparison — competitor feature convergence.
- ACM TOIS "Analysis of Fusion Functions for Hybrid Retrieval" + RRF score-normalization writeups — RRF parameter sensitivity, ranks-only rule.
- OpenAI Embeddings FAQ + cosine-normalization arXiv 2602.19393 — dimension/normalization mismatch across providers.
- Hindsight/Vectorize consolidation problem + AWS AgentCore long-term memory + Tilores LLM entity resolution + generative-NER arXiv 2601.17898 — consolidation race + entity-resolution error modes.
- Hexagonal-architecture-in-Python writeups; tiktoken/tokenizer comparison articles — Protocol ports + per-provider token counting.

### Tertiary (LOW confidence)
- MemPalace explainer posts (96.6%/100% headline numbers) — cited only as a disputed anchor to *avoid*, not a target.

---
*Research completed: 2026-06-10*
*Ready for roadmap: yes*
