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

*Full index set (keyword/graph), forgetting/eviction + salience floor + budget packer + MCP (Phase 3), cloud providers (Phase 4), and the demo (Phase 5) remain Active.*

### Active

<!-- Current scope. Building toward these. Hypotheses until shipped. -->

**Memory architecture (the engine)**
- [ ] T0 raw episodic log — verbatim, append-only, cold storage; pulled only on explicit `expand`
- [ ] T1 working memory — typed records (fact/preference/event/procedure) with the v2 record schema, vector + keyword + graph-edge indexes
- [ ] T2 canonical knowledge — merged, deduped, human-readable, version-controlled user model
- [ ] Recent-session buffer — in-context recent turns, the read-after-write freshness fix (within-session)
- [ ] Fast online write — append T0 + buffer push + optional single-embedding provisional T1 write for durable-looking claims
- [ ] Slow offline consolidation — batch extract typed records, judge salience, entity-resolve, merge/supersede/confirm, clear provisional flag
- [ ] Multi-signal forgetting — keep-score (recency decay + reinforcement + salience) with a **salience floor** that provably protects high-importance facts; eviction is to cold storage and recoverable, never hard-deleted
- [ ] Active supersession — contradicting claims set `valid_until` + `superseded_by` so contradictions never accumulate
- [ ] Budget-aware recall — hybrid retrieval (dense + BM25 + graph expand, RRF-fused), union with buffer, salience/recency re-rank, pack summaries under a token budget, `expand(id)` for verbatim on demand

**Provider & backend portability (the modification)**
- [ ] LLM provider abstraction — chat/extraction/reasoning behind one interface; ships **Qwen (DashScope)** and **Anthropic (Claude)** adapters
- [ ] Embedding provider abstraction — **independent axis** from the LLM (Claude has no first-party embedder, so e.g. Claude reasoning + Qwen/local embeddings is a valid config)
- [ ] Storage adapters — object store (Alibaba OSS ↔ S3 ↔ local FS), vector DB (Postgres+pgvector ↔ alternatives), canonical vault (git-versioned markdown)
- [ ] Compute/scheduler adapters — consolidation trigger behind an interface (Alibaba Function Compute cron ↔ generic cron ↔ in-process)
- [ ] Configuration system — select providers/backends per axis; documented **default = Qwen + Alibaba** (preserves the hackathon proof path)

**Interfaces**
- [ ] MCP server — `remember`, `recall`, `forget`, `consolidate`, plus `expand(id)`
- [ ] Library/SDK — typed, importable API exposing the same memory operations without a server

**Evaluation & demo**
- [ ] Custom memory test harness — 5 tests growing to 20+, mapped 1:1 to storage/recall, freshness, forgetting/supersession, protected-fact, and budget capabilities
- [ ] Before/after baseline — naive "stuff the whole transcript" vs MNEMA on the same suite
- [ ] Nutrition coach reference demo — proves cross-session recall, supersession, decay + protected fact, and budget packing

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
*Last updated: 2026-06-14 — Phase 2 (consolidation & supersession) complete; next: Phase 3 forgetting, salience floor, budget packer & MCP*
