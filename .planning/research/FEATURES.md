# Feature Research

**Domain:** Provider-agnostic AI agent memory engine (MNEMA)
**Researched:** 2026-06-10
**Confidence:** MEDIUM-HIGH (competitor features verified via official docs + papers; consumer-expectation framing is MEDIUM, synthesized from cross-product convergence)

> Scope note: This document is about the **memory engine** as a consumed product (MCP server + SDK).
> The **nutrition coach** is a reference *demo* that exercises the engine — its features
> (meal planning, recipe suggestion, dietary reasoning) are explicitly **out of engine scope**
> and are tracked separately at the bottom (§ "Reference-Demo Features").

---

## Competitor Snapshot (what each prior-art system actually ships)

| Capability | Mem0 / Mem0g | Zep / Graphiti | Letta (MemGPT) | MemPalace / MemoryOS | OpenAI / Anthropic memory |
|---|---|---|---|---|---|
| **Write / extraction** | LLM extract → add/update/delete/no-op decision engine | LLM extracts entities+relations+facts into temporal KG episodes | Agent self-edits core memory via `core_memory_append/replace`; pages out to archival | Verbatim ingest (MemPalace keeps raw, no summarization); MemoryOS does STM→MTM→LPM rollups | Auto profile/fact extraction (ChatGPT auto, Claude explicit/editable) |
| **Retrieval** | Dense vector + graph (Mem0g entity subgraph / triplet ranking) | Hybrid: vector + full-text (BM25) + graph traversal in one call | Tool-call search over recall (history) + archival (indexed) | Incremental layer loading (L0/L1 first, ~170 tok); ChromaDB semantic + metadata "rooms" | Profile injected at prompt start (ChatGPT) or on-demand (Claude) |
| **Forgetting / decay** | Update engine can delete; no first-class time-decay | No decay — facts invalidated, not aged out | Eviction by paging out of context (no automatic decay) | Heat-based replacement (MemoryOS MTM→LPM); MemPalace keeps everything | User can delete; no automatic decay |
| **Contradiction / supersession** | Conflict detection in update phase | **Bitemporal**: `invalid_at` on old fact, `valid_from` on new — strongest in market | Agent overwrites core block manually | Limited / verbatim retain | Manual edit; no automatic supersession |
| **Multi-tenancy** | `user_id` / `agent_id` / `run_id` scoping, metadata filtering | Per-user/group graphs | Per-agent state; multi-agent shared blocks | Per-user local store | Per-account |
| **Observability** | History endpoint (memory change log) | Provenance per fact + graph explorer | Full message/tool trace; agent dev env | CLI inspection | User-readable/editable memory list |
| **Integration surface** | Python/TS SDK + REST + managed platform + MCP | Python/TS SDK + REST + MCP | Server runtime + SDK + REST + MCP | CLI + MCP | Built into product (no engine API) |

Convergent conclusion: **scoping (user/agent/session), CRUD + search, change history, and an MCP/SDK surface are universal.** They are table stakes, not differentiators. MNEMA's edge must be elsewhere.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Missing any of these and the engine reads as a toy, not a credible Mem0/Zep alternative.

| Feature | Why Expected | Complexity | Notes / Dependencies |
|---------|--------------|------------|-------|
| `remember` / write (store an utterance or claim) | Every memory engine has this; the minimum verb | LOW | Maps to T0 append + buffer push. Already in MCP contract. |
| `recall` / semantic search with relevance ranking | Dense retrieval is the floor; no one ships keyword-only | MEDIUM | Needs embedding adapter + vector index (pgvector HNSW). |
| Tenant/scope isolation (`user_id` / `agent_id` / `session_id`) | Universal across Mem0/Zep/Letta; data bleed between users is a dealbreaker | MEDIUM | Must thread scope through every tier and every query `WHERE`. **Foundational — affects schema everywhere.** Easy to retrofit *wrong*; design in from day 1. |
| Typed records / metadata (fact/preference/event/procedure) | Mem0 categories, Letta blocks, Zep entity types — structure is expected | LOW-MEDIUM | v2 record schema already defines this. |
| CRUD on memories (read one, list, update, delete/forget) | Consumers expect to inspect and correct what's stored | LOW | `forget` covers delete-as-archive; need a `get(id)`/`list(scope)` too (gap — see below). |
| Change history / audit of memory mutations | Mem0 history endpoint, Claude "see what's remembered" — table stakes for trust | MEDIUM | Falls out of append-only T0 + supersession edges if surfaced. |
| Metadata filtering on recall (filter by type, time, scope) | Mem0's enhanced metadata filtering is now expected | MEDIUM | Layer on top of hybrid retrieval. |
| MCP tool surface | The 2025-26 default integration path for agents | LOW-MEDIUM | `remember/recall/forget/consolidate/expand` already specced. |
| Library/SDK (in-process, no server) | Mem0/Zep/Letta all ship SDKs; embedding without a network hop is expected | MEDIUM | Same core, two entry points. SDK is the source of truth; MCP wraps it. |
| Async / non-blocking write path | Mem0 ships AsyncMemory; blocking on every turn is a latency dealbreaker | MEDIUM | Fast online write must not block on consolidation. Dual-phase already addresses this. |
| Provider/backend configuration (don't hardcode OpenAI) | Mem0/Letta let you swap LLM + vector store; lock-in is a known pain | MEDIUM | MNEMA elevates this to a differentiator (see below) but *some* config is table stakes. |

### Differentiators (Competitive Advantage — MNEMA's Edge)

Aligned directly to Core Value: *never forget a protected fact, never act on a superseded one, recall within budget, on any provider.*

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Salience floor — provably unforgettable protected facts** | No competitor guarantees by *construction* that an allergy-class fact survives every decay pass. This is a safety/impact story none of Mem0/Zep/Letta tell. | MEDIUM | `keep_score` gated by `salience >= SALIENCE_FLOOR`. The guarantee is the differentiator, not the decay math. Must be demonstrable, not asserted. |
| **Active supersession without the Neo4j tax** | Zep's bitemporal invalidation is the gold standard but ships on Neo4j/Graphiti. MNEMA gets `valid_until`/`superseded_by` with a small adjacency table on Postgres. | MEDIUM-HIGH | Requires entity resolution + contradiction detection in consolidation. The hardest correctness surface — flag for deep research. Depends on consolidation phase. |
| **Recoverable eviction (cold safety net, never hard-delete)** | MemPalace keeps everything (bloats); others hard-delete (loses audit). MNEMA evicts to T0/cold and can recover — auditable + safe. | LOW-MEDIUM | `forget`/decay archive to OSS; recovery path needed. Differentiator only if recovery is real and demoed. |
| **Full provider portability (LLM ⊥ embedding ⊥ storage ⊥ compute)** | Mem0/Letta swap *some* pieces; the **independent LLM/embedding axis** (Claude reasoning + Qwen embeddings) is rare. Run identical on laptop or any cloud. | HIGH | Four adapter axes. High surface area; the central "modification" of the fork. Test matrix grows combinatorially — keep adapter contracts narrow. |
| **Budget-aware recall (token-budget packer)** | Letta pages by context pressure; MNEMA packs *summaries* under an explicit caller-supplied token budget, with `expand(id)` for verbatim on demand. Predictable cost. | MEDIUM | RRF-fused hybrid → re-rank → greedy pack under budget. Depends on summaries existing on records. |
| **Dual-phase write (fast provisional + slow consolidation) closing read-after-write** | The freshness hole (state a preference, recall misses it pre-consolidation) is a known "feels broken" failure. MNEMA closes it cheaply (buffer + one-embedding provisional). | MEDIUM | Buffer fixes within-session; provisional fixes cross-session-pre-consolidation. Provisional flag reconciled by consolidation. |
| **Tiered storage (T0 raw / T1 working / T2 canonical git-versioned vault)** | The human-readable, version-controlled T2 vault (Obsidian/GSD lineage) is portable and inspectable in a way DB-only systems aren't. | MEDIUM | Three backends. T2 promotion logic depends on consolidation. |
| **Cost-tiered curation (flash model curates, smart model reasons)** | Consolidation/salience on a cheap model keeps the agent fast *and* cheap — an operating-cost differentiator. | LOW (given adapters) | Falls out of the LLM adapter abstraction; document as a recommended config. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Neo4j / heavyweight graph DB** | "Real" knowledge graphs feel rigorous; Zep uses one | Operational tax, another backend to host/port, breaks laptop-portability goal | Small Postgres adjacency table for `graph_edges`; 1-hop expand is enough for recall |
| **Hard-delete of memories** | Privacy/cleanup intuition; "delete means delete" | Loses audit trail, breaks recoverability, makes supersession history un-reconstructable | Always archive-to-cold; offer a separate explicit purge only if compliance demands it |
| **Public benchmark wiring (LongMemEval/LoCoMo) as a primary deliverable** | External credibility, leaderboard numbers | ~53 sessions/question = a week of wiring with nothing to show; not a product feature | Custom 5→20+ test harness first (doubles as demo script); benchmark is a stretch only |
| **Full autonomous self-editing memory (Letta-style agent rewrites its own blocks)** | Powerful, "the agent manages itself" | Non-deterministic, hard to test, hard to guarantee the salience floor; conflicts with provable forgetting | Deterministic consolidation pipeline with LLM only for extraction/salience judgement |
| **Real-time/streaming consolidation on every turn** | "Always up to date" | Expensive (LLM per turn), defeats the cheap-curation cost model, reintroduces latency | Dual-phase: cheap provisional now, batch consolidation later |
| **Anchoring on MemPalace's 96.6%/100% headline accuracy** | Marketing parity | Disputed (tuned on specific failing questions); sets a trap | Report MNEMA's own numbers with stated methodology |
| **Arbitrary multi-modal memory (images/audio) in v1** | "Agents see and hear now" | Embedding/storage complexity explodes across the portable adapter matrix | Text-first; design record schema to *allow* future modalities without committing |
| **Cross-tenant shared/global memory in v1** | "Teams want shared knowledge" | Isolation is hard enough to get right per-user; sharing multiplies the leak surface | Strict per-scope isolation first; shared graphs are a v2+ consideration |

---

## Feature Dependencies

```
Tenant/scope isolation
    └──underpins──> ALL tiers, ALL queries, MCP, SDK   (foundational — earliest phase)

T0 raw log + recent buffer
    └──enables──> Fast online write
                      └──enables──> read-after-write freshness (within-session)

T1 typed schema + vector index
    └──requires──> Embedding adapter
    └──enables──> dense recall  ── then ──> hybrid recall (+BM25 +graph)
                                                └──requires──> RRF fusion
                                                      └──enables──> Budget-aware packer
                                                                        └──requires──> per-record summaries

Slow consolidation (LLM adapter, flash tier)
    ├──produces──> salience scores ──> Salience floor (forgetting guarantee)
    ├──produces──> entity resolution ──> Active supersession (valid_until/superseded_by)
    ├──clears────> provisional flag (reconciles fast-path writes)
    └──promotes──> stable records to T2 canonical vault

Decay pass
    └──requires──> salience (floor check) + access_count + recency
    └──evicts to──> cold storage (recoverable; never hard-delete)

Provider adapters (LLM ⊥ embedding ⊥ storage ⊥ compute)
    └──cross-cut──> every feature above; widen the test matrix
```

### Dependency Notes

- **Scope isolation is foundational:** it threads into every table and query `WHERE` clause. Retrofitting it later is a rewrite. Must land in the earliest schema/storage phase.
- **Hybrid recall requires the embedding adapter + BM25 index + graph table** all present; dense-only is a valid intermediate milestone (W1) before hybrid (W2).
- **Budget-aware packer requires summaries** on records — summary generation is part of extraction/consolidation, so the packer depends on consolidation being live (or on provisional records carrying a cheap summary).
- **Salience floor and supersession both depend on consolidation** (salience judgement + entity resolution + contradiction detection). They cannot be demoed before the consolidation pipeline exists — though supersession can be triggered manually for the demo.
- **Provider portability conflicts with shipping speed:** every adapter axis multiplies the integration test surface. Narrow, well-specified adapter contracts are the mitigation. (See PITFALLS.)
- **Provisional write conflicts subtly with supersession:** a provisional record must be reconcilable (merge/supersede/confirm) by consolidation; the provisional flag is the join point. Get the reconciliation state machine right or contradictions leak.

---

## MVP Definition

### Launch With (v1) — proves the thesis end-to-end on the default stack

- [ ] Scope isolation (`user_id`/`agent_id`/`session_id`) — foundational; everything else assumes it
- [ ] T0 append + recent buffer — within-session freshness, cheapest fix
- [ ] T1 typed schema + pgvector dense recall — the minimum credible retrieval
- [ ] `remember` / `recall` / `forget` / `expand` MCP tools + matching SDK calls — the integration surface
- [ ] Fast online write with provisional flag — cross-session freshness
- [ ] Slow consolidation (extract + salience + entity-resolve + supersede) on a flash-tier model
- [ ] Active supersession (`valid_until`/`superseded_by`) — the lead demo, most legible differentiator
- [ ] Decay pass + salience floor + recoverable eviction — the protected-fact safety story
- [ ] Budget-aware packer with summary injection + `expand(id)` verbatim-on-demand
- [ ] At least two LLM adapters (Qwen + Claude) and an independent embedding adapter — proves the portability claim
- [ ] Custom test harness (5→20 tests) mapping to storage/freshness/forgetting/protected-fact/budget

### Add After Validation (v1.x)

- [ ] Hybrid recall = dense **+ BM25 + 1-hop graph + RRF** (dense-only ships first; fusion is the upgrade)
- [ ] T2 canonical git-versioned vault + stable-record promotion
- [ ] Additional storage adapters (S3, local FS, alternative vector stores) beyond the default
- [ ] Richer metadata filtering on recall (time ranges, type combinations)
- [ ] `list(scope)` / `get(id)` inspection endpoints + memory-change history surface
- [ ] Compute/scheduler adapters beyond in-process (Function Compute cron, generic cron)

### Future Consideration (v2+)

- [ ] One public benchmark (LongMemEval or LoCoMo) for external credibility — heavy wiring, defer
- [ ] Cross-tenant / shared-team memory — isolation must be rock-solid first
- [ ] Multi-modal memory (images/audio) — schema designed to allow, not built
- [ ] Autonomous agent-managed memory edits — conflicts with provable-forgetting guarantee

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Scope isolation | HIGH | MEDIUM | P1 |
| Dense recall (`recall`) | HIGH | MEDIUM | P1 |
| `remember` + T0 + buffer | HIGH | LOW | P1 |
| Active supersession | HIGH | MEDIUM-HIGH | P1 |
| Salience floor + recoverable eviction | HIGH | MEDIUM | P1 |
| Budget-aware packer | HIGH | MEDIUM | P1 |
| MCP + SDK surface | HIGH | MEDIUM | P1 |
| Dual-phase / provisional write | MEDIUM-HIGH | MEDIUM | P1 |
| Provider portability (≥2 LLM + 1 embed) | HIGH | HIGH | P1 (core to the fork) |
| Hybrid recall (BM25 + graph + RRF) | MEDIUM | MEDIUM | P2 |
| T2 canonical vault | MEDIUM | MEDIUM | P2 |
| Metadata filtering on recall | MEDIUM | MEDIUM | P2 |
| Inspection/history endpoints | MEDIUM | LOW-MEDIUM | P2 |
| Extra storage/compute adapters | MEDIUM | MEDIUM | P2 |
| Public benchmark wiring | LOW (engine), MEDIUM (credibility) | HIGH | P3 |
| Multi-modal / shared / autonomous edits | LOW (now) | HIGH | P3 |

---

## Competitor Feature Analysis (MNEMA's positioning)

| Feature | Mem0 | Zep / Graphiti | Letta (MemGPT) | MNEMA Approach |
|---------|------|----------------|----------------|----------------|
| Supersession | Conflict detection in update engine | Bitemporal `invalid_at`/`valid_from` (best in class) | Manual block overwrite | Zep-grade `valid_until`/`superseded_by` **without Neo4j** — Postgres adjacency table |
| Forgetting | Delete via update engine, no time-decay | No decay (invalidate only) | Page-out, no decay | Multi-signal `keep_score` + **provable salience floor** + recoverable eviction |
| Retrieval | Dense + graph | Vector + BM25 + graph in one call | Tool-search over recall/archival | RRF hybrid (dense+BM25+graph) unioned with buffer, **packed to token budget** |
| Provider lock-in | Swappable LLM/store, OpenAI-leaning | Hosted + open-source Graphiti | OpenAI/Anthropic-leaning runtime | **Independent LLM ⊥ embedding ⊥ storage ⊥ compute** adapters; laptop-or-cloud parity |
| Storage model | Vector store + optional graph | Temporal KG | RAM/recall/archival OS metaphor | **Tiered T0 raw / T1 working / T2 git-versioned human-readable vault** |
| Write cost | LLM per add | LLM per episode | LLM-driven self-edit | **Cheap provisional now, batch flash-tier consolidation later** |

---

## Reference-Demo Features (Nutrition Coach — explicitly OUT of engine scope)

Tracked here only to keep the boundary crisp for requirements. These exercise the engine; they are **not** engine features and the coach is **not** a shippable end-user product.

| Demo Feature | Engine Capability It Proves |
|---|---|
| Avoids peanuts across sessions | Cross-session recall + salience-floor protected fact |
| "I eat fish now" → switches from vegetarian to pescatarian | Active supersession (the lead demo) |
| Decays a stale "wanted pasta last Tuesday" but keeps allergy | Multi-signal forgetting + salience floor + recoverable eviction |
| Plans a week of dinners under a token budget with months of history | Budget-aware packer + `expand(id)` |
| Honors a preference stated this turn / this session | Buffer + provisional write (read-after-write freshness) |

---

## Sources

- Mem0 architecture / extraction / update engine — [Mem0 paper (arXiv 2504.19413)](https://arxiv.org/pdf/2504.19413), [Mem0 graph memory docs](https://docs.mem0.ai/platform/features/graph-memory), [Dwarves breakdown](https://memo.d.foundation/breakdown/mem0)
- Mem0 REST/async/metadata/CRUD/scoping — [Mem0 API reference](https://docs.mem0.ai/api-reference), [Async memory](https://docs.mem0.ai/open-source/features/async-memory), [Enhanced metadata filtering](https://docs.mem0.ai/open-source/features/metadata-filtering), [Entity-scoped memory](https://docs.mem0.ai/platform/features/entity-scoped-memory)
- Zep bitemporal supersession / Graphiti hybrid retrieval — [Zep paper (arXiv 2501.13956)](https://arxiv.org/html/2501.13956v1), [Graphiti / Zep open-source](https://www.getzep.com/product/open-source/), [Neo4j Graphiti blog](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)
- Letta/MemGPT core/recall/archival + paging — [Letta agent memory](https://www.letta.com/blog/agent-memory), [MemGPT legacy guide](https://docs.letta.com/guides/legacy/memgpt_agents_legacy), [Monigatti MemGPT](https://www.leoniemonigatti.com/blog/memgpt.html)
- MemPalace verbatim/incremental layers + MemoryOS hierarchy — [MemoryOS paper (arXiv 2506.06326)](https://arxiv.org/pdf/2506.06326), [MemPalace explained](https://www.analyticsvidhya.com/blog/2026/05/mempalace-explained/), [MemPalace 170-token recall](https://recca0120.github.io/en/2026/04/08/mempalace-ai-memory-system/)
- OpenAI vs Anthropic memory behavior — [Simon Willison: comparing Claude and ChatGPT memory](https://simonwillison.net/2025/Sep/12/claude-memory/), [Anthropic memory import (MacRumors)](https://www.macrumors.com/2026/03/02/anthropic-memory-import-tool/)
- Multi-tenancy / isolation / observability / MCP surface — [MCP multi-tenant isolation (Prefactor)](https://prefactor.tech/blog/mcp-security-multi-tenant-ai-agents-explained), [Memory MCP servers](https://mcpservers.org/category/memory), [Bedrock AgentCore multi-tenant](https://aws.amazon.com/blogs/machine-learning/building-multi-tenant-agents-with-amazon-bedrock-agentcore/)

---
*Feature research for: provider-agnostic AI agent memory engine*
*Researched: 2026-06-10*
