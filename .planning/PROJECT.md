# MNEMA

## What This Is

MNEMA is a portable, provider-agnostic **memory engine for AI agents** — a tiered, dual-phase memory layer that stores cheaply, curates offline, forgets deliberately, and recalls within a token budget. It is consumed as an MCP server and/or an importable library/SDK, with the LLM, embedding model, storage backends, and compute/scheduler all behind swappable adapters. A **nutrition & meal coach** ships as the reference demo that proves the engine end-to-end.

One-line thesis: *store cheaply, curate offline, forget deliberately, recall within a token budget — on any provider.*

## Core Value

An agent **never forgets a protected fact (e.g. an allergy) and never acts on a superseded one (e.g. an outdated dietary preference)** — while recalling the right context within a fixed token budget, regardless of which model provider or storage backend is configured.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

**Validated in Phase 1: schema-ports-local-core-foundation (2026-06-10)** — the engine's local-core walking skeleton, proven by a 23-test green harness + pyright strict:
- T0 raw episodic log (verbatim, append-only LocalFS) and `expand(id)` verbatim retrieval
- T1 working-memory record schema — the single-source-of-truth Pydantic model with all un-retrofittable columns (structural `protected` flag, embedding provenance, `valid_until` lifecycle)
- Six async Protocol ports (LLM, embedding, object-store, record-store, vector-index, scheduler) — **independent LLM/embedding axes** confirmed (separate Protocols + constructor params; dim-mismatch guard at startup)
- Local adapters: SqliteT1 (RecordStore + VectorIndex over one aiosqlite + sqlite-vec connection, user-scoped recall), StubEmbedder, InProcessScheduler
- Fast online write (T0 + buffer + provisional T1, **no LLM on the write path**) and recent-session buffer freshness
- Budget-naive recall (dense KNN + buffer union, content-deduped) and the `MemoryEngine`/`ScopedHandle` SDK surface
- **Core-value foundation:** a safety claim (e.g. "I am allergic to peanuts") is stored `protected=True` from content alone, independent of any caller hint

**Validated in Phase 2: consolidation-&-supersession (2026-06-14)** — the offline pipeline, fully local + deterministic, proven by a 33-test green harness + pyright strict:
- Consolidation drains the staging queue, extracts typed records via the (stub) LLM, and pins safety/medical content `protected` + salience 1.0 by the content rule (never the LLM)
- Active supersession: a contradicting claim atomically sets `valid_until` + `superseded_by` + a `supersedes` graph edge in a single transaction; a non-contradicting refinement merges in place
- Provisional reconciliation by `t0_ref` identity (upgrade-in-place, no duplicates); re-running consolidation is idempotent
- **Safety guarantee (load-bearing):** a protected/`fact` record is never auto-superseded on an LLM contradiction alone — it records a `contradiction_pending` edge and requires explicit `forget()`; consolidation never clears `protected`
- A decay pass computes `keep_score` (recency decay + reinforcement + salience) as a pure sync fn over all live records (eviction deferred to Phase 3)

**Validated in Phase 3: forgetting, salience floor, budget packer & MCP (2026-06-14)** — proven by a 56-test green harness (incl. a Hypothesis property test + adversarial packer test) + pyright strict:
- **Deliberate, recoverable forgetting:** eviction sets `valid_until` + deletes the vector row + archives to recoverable cold storage + appends a JSONL audit — **no hard-delete path exists** (eviction without a cold store now raises rather than silently dropping)
- **Provable protected-fact guarantee (FORG-03):** a Hypothesis property test proves no input can evict a protected record (it's skipped before any score math, by construction)
- **Budget-aware recall:** relevance×salience×recency re-rank + a two-pass packer that reserves protected/critical slots first — a protected fact is never pushed out of budget, even when budget < the critical set
- **T2 canonical vault:** new `VaultStore` Protocol (6th adapter axis) + LocalFS atomic-write markdown user-model; confirmed high-salience records promoted during consolidation (vault BEFORE eviction)
- **MCP surface (IFACE-02):** FastMCP thin wrapper exposing the 5 verbs over the same engine; `user_id` required + passed through on every tool (hard isolation real)

**Validated in Phase 4: cloud providers & backends (2026-06-15)** — proven by a 118-test green hermetic harness + pyright-strict(--extra cloud) + a parametrized conformance suite:
- Real cloud adapters behind the existing ports (ZERO Protocol changes): **Qwen/DashScope** LLM + embedder, **Anthropic Claude** LLM, **Voyage** embedder, **Alibaba OSS** (boto3 S3-compat) object store, **Postgres+pgvector** (psycopg3 async, HNSW, partial index) vector store, **CronScheduler**
- **Shared conformance suite** asserts the safety invariants (scope isolation, protected-survival, no-hard-delete) on EVERY backend; ≥2 backends/axis (local always-on + cloud/Postgres gated by env/Docker) — the CI gate stays hermetic
- **Config-keyed factory** `build_engine(LocalConfig | QwenAlibabaConfig)` wires all six axes (API keys as `SecretStr`); the documented default is Qwen DashScope (LLM + embeddings) + Alibaba; the fully-local config runs the same suite end-to-end
- **PROV-07 reindex/migration:** switching embedder/dim triggers an explicit `migrate_embedder()` (store-wide reindex, protected records preserved) — never a silent flip; startup dim assertion is the backstop
- Independent LLM/embedding axes confirmed (Claude+Voyage is a first-class combo); cloud deps isolated behind an optional `cloud` extra so the laptop path stays lean

**Validated in Phase 5: reference demo & evaluation (2026-06-15)** — proven by a 124-test green hermetic harness + a committed `EVAL.md`:
- A **CLI nutrition coach** runs end-to-end on the engine through the SDK alone (`build_engine(LocalConfig)` + the five verbs)
- The four core behaviors are each a deterministic test: **cross-session recall** (constraint stated in session 1, honored in session 2 over a persistent store), **supersession** (a diet change retires the old record, surfacing `valid_until`/`superseded_by`), **decay + protected** (a backdated transient is evicted then recovered via `expand()` while a pinned allergy survives untouched), **budget packing** (a large history packed under a token budget + one verbatim `expand`)
- **EVAL-02 before/after baseline (our own honest numbers):** MNEMA passes **3/3** containment probes; naive transcript-stuffing passes **2/3** — it *fails superseded-fact avoidance* (it includes both the old and new diet), the exact "never act on a superseded fact" failure MNEMA prevents — at **~38% fewer context tokens**

---

## 🎉 Milestone v1.0 complete — all 5 phases shipped & verified.

*The core thesis is proven end-to-end: store cheaply (T0/buffer/provisional T1), curate offline (consolidation + supersession), forget deliberately (recoverable eviction with a provable protected-fact guarantee), recall within a token budget (two-pass packer) — on any provider (six swappable adapter axes, conformance-gated). Deferred to a future milestone: hybrid retrieval (BM25 + graph + RRF, HYBRID-01/02/03) and extra providers (OpenAI/Ollama, PROV-08).*

### Active

<!-- v1.0 shipped all founding hypotheses (see the per-phase Validated entries above). The items below are the v1.1 candidate scope, deferred from v1.0. -->

**Deferred to v1.1 (candidates — run `/gsd-new-milestone` to scope):**
- [ ] **Hybrid retrieval** — sparse/BM25 keyword recall + 1-hop graph expand over the adjacency table + RRF fusion (ranks-only, k=60) of dense + sparse + graph (HYBRID-01/02/03). v1.0 shipped dense + buffer only.
- [ ] **Additional providers** — OpenAI and Ollama adapters behind the existing LLM/embedding axes (PROV-08).
- [ ] **Tech-debt cleanup** — the tracked per-phase code-review deferred items (`.planning/todos/pending/phase-0{1..5}-code-review-deferred.md`): mostly INFO/cosmetic + a couple of latent-concurrency hardening items (e.g. LocalFS append TOCTOU, `all_live_records` on the RecordStore Protocol), and flipping the Nyquist `nyquist_compliant` flag on phases 02/03/04.

**v1.0 founding scope — all shipped & validated** (full detail in the Validated section above): the tiered T0/T1/T2 + buffer architecture, fast online write, offline consolidation + supersession, recoverable forgetting with a provable protected-fact guarantee, budget-aware recall (dense + buffer, two-pass packer), six swappable adapter axes (LLM/embedding/object/vector/vault/scheduler) with Qwen+Alibaba and fully-local configs, the MCP server + SDK, and the nutrition-coach demo + before/after eval baseline.

### Out of Scope

<!-- Explicit boundaries with reasoning. -->

- **Qwen-only / Alibaba-only lock-in** — explicitly replaced by the adapter layer; Qwen+Alibaba remains the default, not the only option
- **Public benchmarks (LongMemEval / LoCoMo) as a primary deliverable** — ~53 sessions/question is heavy wiring; custom suite comes first, benchmark is a stretch only
- **Hitting the July 9 hackathon deadline as a hard gate** — hackathon is a bonus; clean portable architecture takes priority over the date
- **Neo4j / heavyweight graph database** — keep Zep-style fact-validity supersession without the Neo4j tax (small adjacency table instead)
- **Hard-deleting memories** — eviction is always recoverable/auditable to cold storage
- **Anchoring on MemPalace's 96.6%/100% headline numbers** — disputed; report our own numbers with methodology
- **Nutrition coach as a shippable end-user product** — it is a reference demo for the engine, not a maintained consumer app

## Context

- **Origin:** Forked from the MNEMA v2 build plan (`mnema-build-plan.md`), originally scoped for the Qwen Cloud hackathon (Track 1: MemoryAgent). The user's directive: keep the memory engine, but decouple it from Qwen-only models so providers can be coupled/decoupled freely.
- **Design lineage:** Borrows the strongest idea from each prior system and drops its flaw — MemPalace's "keep everything" → cold safety net; Zep's fact-validity supersession → kept without Neo4j; Obsidian/GSD's portable human-readable layer → canonical T2 tier; Mem0's compact extraction → working tier; Letta's paging → explicit token budget.
- **Biological framing:** Complementary learning systems — T0 is the hippocampal episode store; T1+T2 are neocortical consolidation (patterns, entities, recency-weighting).
- **Track capabilities the engine targets:** efficient storage/retrieval, timely forgetting of outdated information, recall within a limited context window — each must be *demonstrable*, not just described.
- **Demo discipline:** Lead with supersession (instant, legible). Never demo time-decay on a wall clock — seed backdated timestamps and run the decay pass on stage. Inject summaries by default; expand verbatim only on demand.
- **Hackathon submission (if pursued as bonus):** public repo + OSS license, backend proven on Alibaba Cloud (separate recording), architecture diagram, ~3-min demo video, feature description, Track 1 identified.

## Constraints

- **Architecture**: LLM and embedding providers must be *independently* configurable — the embedding axis cannot be coupled to the chosen LLM (Claude ships with no embedder).
- **Portability**: Models, storage (object/vector/vault), and compute/scheduler must each sit behind an adapter so MNEMA runs identically on a laptop or any cloud.
- **Default stack**: Out-of-box default is Qwen (DashScope) + Alibaba (OSS/Postgres/Function Compute) to keep the hackathon proof path canonical; local/other backends are opt-in via config.
- **Cost model**: Cheap model curates (consolidation/salience on a flash-tier model), expensive model only reasons — keep the agent fast *and* cheap.
- **Safety/impact**: A protected fact (allergy → salience 1.0) must survive every decay pass by construction — the architecture *provably cannot* forget it.
- **Freshness**: No read-after-write hole — a stated preference must be recallable within-session (buffer) and cross-session-pre-consolidation (provisional write).
- **Timeline**: No hard deadline; build it right. July 9 is an optional hackathon target for a working slice, not a gate.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Portable memory engine is the product; nutrition coach is a reference demo | User pivoted from a single hackathon app to a reusable, provider-agnostic engine | — Pending |
| Full-stack portability (models + storage + compute) | User wants to run identically on laptop or any cloud, no lock-in | — Pending |
| LLM and embedding as independent provider axes | Claude has no first-party embedder; forces decoupling of the two axes | — Pending |
| v1 providers: Qwen + Anthropic | Qwen = hackathon-native + embeddings; Claude = strong reasoning | — Pending |
| Default = Qwen + Alibaba | Preserves the hackathon "proven on Alibaba Cloud" path as canonical | — Pending |
| Interfaces: MCP server + library/SDK | Engine must be embeddable both as a server and an in-process library | — Pending |
| Keep tiered + dual-phase + supersession + salience-floor core unchanged | This is the valuable IP from the build plan; decoupling is additive | — Pending |
| Custom test harness before public benchmarks | LongMemEval/LoCoMo wiring is heavy; custom suite doubles as demo script | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-15 after v1.0 milestone — shipped & archived*
