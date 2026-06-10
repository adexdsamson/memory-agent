# Architecture Research

**Domain:** Portable, provider-agnostic AI agent memory engine (tiered, dual-phase)
**Researched:** 2026-06-10
**Confidence:** HIGH (pattern lineage verified against Mem0, LiteLLM, LlamaIndex, Zep/Graphiti; build-plan internals are the project's own spec)

## Standard Architecture

The dominant pattern across the comparable systems is **a backend-agnostic core orchestrator that depends only on abstract ports, with concrete adapters wired at a single composition root**:

- **Mem0** splits a `Memory` orchestrator from `VectorStoreBase` / `LLMBase` / `EmbeddingBase` / graph-store interfaces, instantiated by a dynamic **factory** (`mem0/utils/factory.py`) keyed on a config `type` field. The *same* `Memory` core powers the OSS SDK (direct instantiation), a FastAPI server wrapper, and the hosted `MemoryClient` — only the wiring differs. ([DeepWiki: Mem0 overview](https://deepwiki.com/mem0ai/mem0/1-overview))
- **LiteLLM** is the reference for the LLM/embedding axis: one `completion()` / `embedding()` surface, OpenAI-shaped responses regardless of provider, exceptions normalized to a common hierarchy. The same SDK is exposed as an in-process library *and* a proxy gateway. ([LiteLLM docs](https://docs.litellm.ai/), [DeepWiki: completion/embedding](https://deepwiki.com/BerriAI/litellm/2.1-completion-functions-and-core-apis))
- **LlamaIndex** is the reference for the storage axis: a `StorageContext` aggregates independent `BaseDocumentStore` (≈ T0), `BasePydanticVectorStore` (≈ T1 vector index), and `BaseIndexStore` ports; you subclass the base to add a backend and it plugs into downstream retrievers unchanged. ([LlamaIndex storing](https://developers.llamaindex.ai/python/framework/module_guides/storing/), [StorageContext](https://developers.llamaindex.ai/python/framework-api-reference/storage/storage_context/))
- **Zep/Graphiti** is the reference for the *domain logic* MNEMA keeps (bitemporal fact validity, edge invalidation/supersession) — but it hard-couples to Neo4j, which is exactly the lock-in MNEMA replaces with a small adjacency table behind a port. ([Zep paper](https://arxiv.org/abs/2501.13956), [Graphiti](https://github.com/getzep/graphiti))

The synthesis: **hexagonal (ports & adapters) core, LiteLLM-style provider unification on the two model axes, LlamaIndex-style independent storage ports, Mem0-style factory + dual surface (SDK = core; MCP server = thin wrapper over the same core).**

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        DRIVING ADAPTERS (surfaces)                     │
│   ┌────────────────────┐                  ┌────────────────────────┐   │
│   │   MCP Server        │                  │   Library / SDK         │   │
│   │ remember/recall/    │                  │  Memory() class,        │   │
│   │ forget/consolidate/ │                  │  typed Python API       │   │
│   │ expand              │                  │                         │   │
│   └─────────┬───────────┘                  └───────────┬─────────────┘   │
│             │            both call the same MemoryEngine API             │
├─────────────┴──────────────────────────────────────────┴──────────────┤
│                      ENGINE CORE  (backend-agnostic)                    │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Orchestrators:  WritePath · ConsolidationPipeline · RecallPath    │ │
│  │  Domain logic:   record schema · keep_score/decay · supersession   │ │
│  │                  RRF fusion · budget packer · salience floor        │ │
│  │  Buffer:         in-process recent-session ring                     │ │
│  │  Depends ONLY on the PORT protocols below — never on a vendor SDK   │ │
│  └──────────────────────────────────────────────────────────────────┘ │
├────────────────────────────── PORTS (interfaces) ──────────────────────┤
│  LLMPort   EmbeddingPort   ObjectStorePort   VectorStorePort   SchedulerPort │
├────────────────────────────── DRIVEN ADAPTERS ─────────────────────────┤
│  Qwen/    Qwen/local/    Alibaba OSS/    Postgres+pgvector/  FC cron/    │
│  Claude   OpenAI         S3 / local FS   (Tablestore/...)    cron/      │
│           embedder                                            in-process│
├─────────────────────────── EXTERNAL SYSTEMS ───────────────────────────┤
│  DashScope · Anthropic · OSS/S3 · Postgres · Function Compute · git vault│
└──────────────────────────────────────────────────────────────────────┘
```

Note: the **canonical T2 vault** (git-versioned markdown) is reached through a sixth, lighter `VaultPort` (read/write/commit markdown) — independent of the object store because its semantics (human-readable, version-controlled) differ from cold blob append.

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **MemoryEngine** (core API) | Public typed operations: `remember/recall/forget/consolidate/expand`; owns no I/O | Plain class composed of orchestrators + ports |
| **WritePath** | Fast online write: append T0, push buffer, classify durable claim, optional single-embedding provisional T1 upsert, enqueue staging | Pure logic over `ObjectStorePort` + `EmbeddingPort` + `VectorStorePort` |
| **ConsolidationPipeline** | Slow offline: drain staging → extract typed records → judge salience → entity-resolve → merge/supersede/confirm → decay → promote-to-T2 | Logic over `LLMPort` + `EmbeddingPort` + `VectorStorePort` + `VaultPort` |
| **RecallPath** | Hybrid retrieve (dense+BM25+graph-expand), RRF fuse, union buffer, salience/recency re-rank, budget-aware pack | Logic over `VectorStorePort` + in-memory buffer |
| **RecentSessionBuffer** | Read-after-write freshness within session | In-process ring buffer (not a port) |
| **LLMPort** | Chat/extraction/reasoning + salience judgement | DashScope (Qwen), Anthropic adapters |
| **EmbeddingPort** | Text → vector (independent axis) | Qwen embeddings, local/OpenAI adapters |
| **ObjectStorePort** | Append/get verbatim T0 blobs; archive cold | OSS, S3, local FS adapters |
| **VectorStorePort** | Upsert/vector-search/bm25/graph-expand/update typed T1 records | Postgres+pgvector adapter |
| **VaultPort** | Read/write/commit canonical T2 markdown | git-backed local FS adapter |
| **SchedulerPort** | Trigger `consolidate()` on a heartbeat | Function Compute cron, generic cron, in-process timer |
| **Factory / Composition Root** | Read config, instantiate one adapter per axis, build MemoryEngine | `from_config()` keyed on `type` field |

## Recommended Project Structure

```
src/mnema/
├── core/                      # backend-agnostic — imports NOTHING vendor-specific
│   ├── engine.py              # MemoryEngine: public typed API (the SDK surface)
│   ├── schema.py              # Record dataclass/pydantic (the v2 schema), enums
│   ├── write_path.py          # fast online write orchestrator
│   ├── consolidation.py       # extract/salience/entity-resolve/merge/supersede/decay/promote
│   ├── recall.py              # hybrid retrieve + RRF + buffer union + budget packer
│   ├── forgetting.py          # keep_score, decay_pass, SALIENCE_FLOOR
│   ├── buffer.py              # recent-session ring buffer
│   └── fusion.py              # RRF, re-rank weights
├── ports/                     # the five+one Protocol contracts — pure interfaces
│   ├── llm.py                 # LLMPort
│   ├── embedding.py           # EmbeddingPort
│   ├── object_store.py        # ObjectStorePort
│   ├── vector_store.py        # VectorStorePort
│   ├── vault.py               # VaultPort
│   └── scheduler.py           # SchedulerPort
├── adapters/                  # concrete implementations — each imports its vendor SDK
│   ├── llm/        { qwen_dashscope.py, anthropic.py }
│   ├── embedding/  { qwen.py, local_sentencetransformers.py }
│   ├── object_store/ { alibaba_oss.py, s3.py, local_fs.py }
│   ├── vector_store/ { postgres_pgvector.py }
│   ├── vault/      { git_markdown.py }
│   └── scheduler/  { function_compute.py, cron.py, in_process.py }
├── config/
│   ├── factory.py             # from_config(): type-keyed adapter instantiation
│   └── defaults.py            # default = Qwen + Alibaba
├── surfaces/
│   ├── mcp_server.py          # thin: maps MCP tools -> MemoryEngine calls
│   └── __init__.py            # SDK re-export = core.engine.MemoryEngine
└── demo/nutrition_coach/      # reference demo consuming the SDK only
```

### Structure Rationale

- **`core/` imports only from `ports/`** — this is the enforced seam. A lint/import rule ("core may not import adapters or vendor SDKs") is what makes portability *mechanical* rather than aspirational. This mirrors Mem0's `Memory` orchestrator and the hexagonal rule that the domain has no outward dependencies.
- **`ports/` are Protocols, not ABCs** — Python `typing.Protocol` gives structural typing so an adapter need not inherit; easier to mock in tests and to adapt third-party clients. ([Hexagonal in Python](https://blog.szymonmiks.pl/p/hexagonal-architecture-in-python/))
- **`adapters/` grouped by axis** — each file is the *only* place a given vendor SDK (`dashscope`, `boto3`, `psycopg`, `anthropic`) is imported. Swapping a backend touches exactly one file + one config line, the Mem0/LiteLLM promise.
- **`surfaces/` are driving adapters** — MCP server and SDK are two thin entry points over one `MemoryEngine`. The SDK *is* the core API; the MCP server is a protocol translation layer (Mem0's "same core, FastAPI wrapper" pattern).

## Architectural Patterns

### Pattern 1: Ports as typed Protocols (the swappable seam)

**What:** Each of the five axes is a `Protocol` the core depends on; adapters satisfy it structurally.
**When to use:** Every external I/O dependency. **Trade-offs:** small upfront interface-design cost; pays back as zero-cost backend swaps and trivial test doubles.

The interface contracts (the heart of this research):

```python
class LLMPort(Protocol):
    def chat(self, messages: list[Msg], *, model: str | None = None,
             temperature: float = 0.0) -> str: ...
    def extract_records(self, batch: list[Turn]) -> list[Record]: ...   # consolidation
    def judge_salience(self, record: Record) -> float: ...              # 0..1, allergy->1.0

class EmbeddingPort(Protocol):            # INDEPENDENT of LLMPort by design
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dim(self) -> int: ...             # core needs this to provision the vector column

class ObjectStorePort(Protocol):          # T0 cold log + cold archive
    def append(self, session_id: str, turn: Turn) -> str: ...   # returns t0:// ref
    def get(self, ref: str) -> Turn: ...                        # backs expand(id)
    def archive(self, record: Record) -> str: ...               # evicted, recoverable

class VectorStorePort(Protocol):          # T1 working memory + its indexes
    def upsert(self, record: Record) -> None: ...
    def vector_search(self, q: list[float], k: int, where_live: bool = True) -> list[Hit]: ...
    def bm25(self, query: str, k: int) -> list[Hit]: ...
    def graph_expand(self, seeds: list[str], hops: int = 1) -> list[Hit]: ...
    def update(self, id: str, **fields) -> None: ...   # set valid_until/superseded_by, access_count
    def live_records(self) -> Iterable[Record]: ...    # decay pass scans WHERE valid_until IS NULL

class VaultPort(Protocol):                # T2 canonical markdown
    def read(self, path: str) -> str: ...
    def write_and_commit(self, path: str, content: str, msg: str) -> None: ...

class SchedulerPort(Protocol):            # consolidation trigger abstraction
    def schedule(self, fn: Callable[[], None], *, every_seconds: int) -> None: ...
    def trigger_now(self) -> None: ...    # backs consolidate(force=True) for the demo
```

Key contract decisions:
- **Embedding is its own port** with an explicit `dim` — the core provisions the pgvector column from `dim`, so Claude-reasoning + Qwen-embedding is a valid config (the project's hard constraint). The LLM and embedding axes never reference each other.
- **`where_live` / `live_records()` push the `valid_until IS NULL` partial-index concern down to the adapter** — the core states intent ("only live records"), the Postgres adapter implements it as the partial index. A non-SQL adapter could filter differently. This keeps the supersession *semantics* in core, the *index strategy* in the adapter.
- **`graph_expand` is a port method, not a separate graph DB** — MNEMA's "no Neo4j tax" decision means the adjacency table lives inside the `VectorStorePort` (Postgres) adapter. If someone later wants a real graph backend, it's a different adapter satisfying the same method.

### Pattern 2: Factory + composition root keyed on config `type`

**What:** One `from_config()` reads `{llm: {type: "qwen"}, embedding: {type: "qwen"}, ...}` and returns concrete adapters; the engine is assembled once. **When to use:** at process start / server boot. **Trade-offs:** centralizes all vendor knowledge in one wiring file (good) but is the one place that must know every adapter (acceptable). Directly mirrors `mem0/utils/factory.py`.

```python
def from_config(cfg: Config) -> MemoryEngine:
    return MemoryEngine(
        llm        = LLM_REGISTRY[cfg.llm.type](cfg.llm),
        embedder   = EMBED_REGISTRY[cfg.embedding.type](cfg.embedding),
        objects    = OBJ_REGISTRY[cfg.object_store.type](cfg.object_store),
        vectors    = VEC_REGISTRY[cfg.vector_store.type](cfg.vector_store),
        vault      = VAULT_REGISTRY[cfg.vault.type](cfg.vault),
        scheduler  = SCHED_REGISTRY[cfg.scheduler.type](cfg.scheduler),
    )   # default cfg == Qwen + Alibaba (preserves the hackathon proof path)
```

### Pattern 3: One core, two surfaces (SDK is the core; MCP is a translator)

**What:** `MemoryEngine` is the SDK. The MCP server is a ~50-line adapter mapping each MCP tool to one engine method. **When to use:** always — never duplicate logic between server and library. **Trade-offs:** none meaningful; this is the Mem0 dual-surface pattern and LiteLLM's SDK-and-gateway pattern.

```python
# surfaces/mcp_server.py
@tool("recall")
def recall(query: str, token_budget: int):
    return engine.recall(query, token_budget)   # all logic lives in core
```

### Pattern 4: Scheduler as a port (cron ↔ Function Compute ↔ in-process)

**What:** The consolidation *trigger* is abstracted; `consolidate()` itself is just a core method. **When to use:** any deferred/batch work. **Trade-offs:** the in-process adapter (timer thread) is great for laptop/tests; Function Compute cron is a thin adapter that calls an HTTP endpoint which invokes `engine.consolidate()`. The demo uses `trigger_now()` so decay/consolidation run on stage instead of on a wall clock.

## Data Flow

### Write path (fast, online, per turn)

```
remember(content, session_id)
   → ObjectStorePort.append      → t0_id              (verbatim, lossless)
   → RecentSessionBuffer.push                          (within-session freshness, zero cost)
   → if looks_like_durable_claim:
        EmbeddingPort.embed(content)                   (ONE embedding, no reasoning LLM)
        VectorStorePort.upsert(provisional=True)       (cross-session-pre-consolidation freshness)
   → staging.enqueue({turn, t0_id})                    (full extraction deferred)
   ⇒ returns {t0_id, provisional_id?}
```

### Consolidation path (slow, offline, heartbeat)

```
SchedulerPort fires  →  engine.consolidate()
   batch = staging.drain()
   records = LLMPort.extract_records(batch)            (Qwen-flash; cheap model curates)
   for r in records:
       EmbeddingPort.embed(r.content)
       LLMPort.judge_salience(r)                       (allergy/medical → 1.0)
       near = VectorStorePort.hybrid_search(r)
       if entity match & contradicts:                  ACTIVE SUPERSESSION
           VectorStorePort.update(match, valid_until=now, superseded_by=r.id)
       elif match: merge; else: upsert(provisional=False)
   forgetting.decay_pass():                            keep_score < FLOOR & salience < SALIENCE_FLOOR
       → ObjectStorePort.archive(r)                    (recoverable, never hard-deleted)
   promote_stable_to_T2 → VaultPort.write_and_commit
```

### Recall path (budget-aware)

```
recall(query, token_budget)
   q = EmbeddingPort.embed(query)
   dense  = VectorStorePort.vector_search(q, where_live=True)
   sparse = VectorStorePort.bm25(query)
   graph  = VectorStorePort.graph_expand(dense[:5])
   fused  = RRF(dense, sparse, graph)
   fused  = dedupe(fused ∪ buffer.as_candidates())     (FRESHNESS union)
   ranked = sort by rrf · (0.5+0.5·salience) · recency_weight
   pack summaries until token_budget; VectorStorePort.update access_count/last_accessed
   ⇒ summaries; verbatim via expand(id) → ObjectStorePort.get
```

### Key Data Flows

1. **Dependency direction is always inward:** surfaces → core → ports ← adapters. Adapters depend on ports; core depends on ports; nothing depends on adapters except the factory.
2. **Freshness is layered:** buffer (within-session) → provisional T1 write (cross-session, pre-consolidation) → consolidated T1 (durable). Each layer is a different code path in `write_path.py` / `recall.py`, none in adapters.

## Build Order (dependency-driven)

This is the load-bearing output for the roadmap. Build inside-out:

1. **`core/schema.py` first.** Every other component references the Record type. No dependencies.
2. **`ports/` (all six Protocols).** Pure interfaces; depend only on schema. Cheap, unblocks everything and all tests.
3. **In-memory / local reference adapters** (local FS object store, in-process scheduler, and a trivial in-memory vector store). This lets the entire core be built and tested with **zero cloud dependencies** — critical for the "runs identically on a laptop" constraint and for fast tests.
4. **Core orchestrators against the in-memory adapters, in this sub-order:**
   a. `write_path` + `buffer` (needs ObjectStore + Embedding + Vector ports) → enables `remember`.
   b. `recall` + `fusion` (needs Vector port) → enables `recall`. *W1 slice = remember + recall(dense) end-to-end.*
   c. `consolidation` (needs LLM + Embedding + Vector + Vault) → extract/merge/supersede.
   d. `forgetting` (decay + salience floor) → needs nothing new.
5. **Factory + config** (`from_config`, defaults). Wires what exists.
6. **Real cloud adapters per axis, independently** — Qwen LLM, Qwen embedder, Alibaba OSS, Postgres+pgvector (this one carries the HNSW + tsvector/GIN + adjacency-table + partial-index work), Function Compute scheduler, git vault. Each is swap-tested against the same core test suite that the in-memory adapters already pass.
7. **Surfaces:** MCP server, then SDK packaging (SDK is mostly already done — it *is* the engine).
8. **Reference demo (nutrition coach)** consumes the SDK only — proves the seam holds.
9. **Eval harness** runs against the SDK; same suite validates any adapter combo.

**Critical ordering insight:** the in-memory adapters (step 3) are not throwaway — they are the permanent test backend and the "laptop default fallback." Building them before the cloud adapters means the core is provably backend-agnostic *by the time the first cloud adapter exists*, not hopefully so afterward.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single user / demo | Everything in-process; in-process scheduler; pgvector on one Postgres; OSS or local FS for T0. Fine. |
| 10s–100s of users | Move consolidation to Function Compute cron (already a port swap). Partition T1 by `subject`/user. Partial index `WHERE valid_until IS NULL` keeps the hot path small. |
| 1k+ users / large histories | pgvector HNSW tuning; consider sharding T1 by user; batch consolidation per-user; T0 stays cheap (append-only blob). The budget packer caps recall cost regardless of history size — the core scaling lever. |

### Scaling Priorities

1. **First bottleneck: consolidation LLM cost/latency.** Mitigated by cheap-model curation (Qwen-flash) + batching + provisional-write decoupling so the hot path never waits on it.
2. **Second bottleneck: T1 vector search over dead records.** Mitigated by the `valid_until IS NULL` partial index — supersession actively shrinks the live set.

## Anti-Patterns

### Anti-Pattern 1: Leaking vendor SDK types through ports

**What people do:** return a `dashscope.Response` or a raw pgvector row from a port method. **Why it's wrong:** the vendor type re-couples the core; swapping backends now ripples into core. **Do this instead:** ports speak the domain language (`Record`, `Hit`, `t0://` refs). This is LiteLLM's lesson — normalize every provider to one response shape and one exception hierarchy.

### Anti-Pattern 2: Coupling the embedding axis to the LLM axis

**What people do:** one `Provider` interface with both `chat()` and `embed()`. **Why it's wrong:** Claude has no first-party embedder — this makes Claude unusable and violates the project's hard constraint. **Do this instead:** two separate ports, configured independently; `EmbeddingPort.dim` provisions storage.

### Anti-Pattern 3: Putting domain logic in the MCP server or in adapters

**What people do:** RRF fusion in the recall tool, salience floor in the Postgres adapter, supersession rules in the consolidation cron handler. **Why it's wrong:** logic duplicates between SDK and server, and becomes un-portable (re-implemented per backend). **Do this instead:** all of it lives in `core/`; surfaces translate, adapters do I/O only. (Mem0's single-`Memory`-core rule.)

### Anti-Pattern 4: Hard-coding the consolidation trigger

**What people do:** call Function Compute / a cron library directly from consolidation code. **Why it's wrong:** can't run on a laptop, can't trigger on-stage for the demo. **Do this instead:** `SchedulerPort` with in-process / cron / Function Compute adapters and a `trigger_now()` for force/demo.

### Anti-Pattern 5: Adopting Graphiti/Neo4j wholesale for the graph axis

**What people do:** pull in a heavyweight graph DB to get Zep-style fact validity. **Why it's wrong:** the Neo4j tax (ops, cost, lock-in) for what MNEMA needs — supersession edges and 1-hop expansion. **Do this instead:** keep bitemporal supersession semantics in core; implement edges as a small adjacency table behind `VectorStorePort.graph_expand`. ([Zep paper](https://arxiv.org/abs/2501.13956) for the *semantics*, not the *backend*.)

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| DashScope (Qwen chat + embed) | `LLMPort` + `EmbeddingPort` adapters | Two separate adapters even though same vendor — keeps axes independent |
| Anthropic (Claude) | `LLMPort` adapter only | No embedder — pair with Qwen/local embeddings |
| Alibaba OSS / S3 / local FS | `ObjectStorePort` adapters | Append-only T0 + cold archive; `t0://` ref scheme is the contract |
| Postgres + pgvector | `VectorStorePort` adapter | Owns HNSW, tsvector/GIN BM25, adjacency table, partial index |
| Function Compute | `SchedulerPort` adapter | Cron → HTTP → `engine.consolidate()`; the Alibaba-cloud proof artifact |
| git (markdown vault) | `VaultPort` adapter | T2 promotion = write + commit; human-readable, versioned |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| surfaces ↔ core | direct method calls to `MemoryEngine` | MCP server and SDK both call the same API |
| core ↔ adapters | through `ports/` Protocols only | enforced by import rule; the portability seam |
| factory ↔ adapters | constructs concretes from config `type` | the *only* module that imports adapter classes |
| WritePath ↔ ConsolidationPipeline | via staging queue + provisional flag | decouples fast path latency from slow LLM work |

## Sources

- [DeepWiki — Mem0 overview](https://deepwiki.com/mem0ai/mem0/1-overview) (core/orchestrator split, factory pattern, dual SDK/server surface) — HIGH
- [LiteLLM docs](https://docs.litellm.ai/) and [DeepWiki — completion/embedding functions](https://deepwiki.com/BerriAI/litellm/2.1-completion-functions-and-core-apis) (unified provider interface, normalized responses/exceptions, SDK + gateway) — HIGH
- [LlamaIndex — Storing module](https://developers.llamaindex.ai/python/framework/module_guides/storing/), [StorageContext API](https://developers.llamaindex.ai/python/framework-api-reference/storage/storage_context/) (independent docstore/vector/index store ports, subclass-to-extend) — HIGH
- [Zep: A Temporal Knowledge Graph Architecture for Agent Memory (arXiv 2501.13956)](https://arxiv.org/abs/2501.13956), [Graphiti repo](https://github.com/getzep/graphiti) (bitemporal fact validity, edge invalidation — semantics MNEMA keeps without Neo4j) — HIGH
- [Hexagonal architecture in Python](https://blog.szymonmiks.pl/p/hexagonal-architecture-in-python/), [Ports and Adapters with DI/composition root](https://elpic.medium.com/hexagonal-architecture-in-python-wiring-adapters-dependency-injection-and-the-application-layer-1f2f83910deb) (Protocol-based ports, composition root, core-has-no-outward-deps) — MEDIUM
- `mnema-build-plan.md` (tier definitions, v2 record schema, two-phase + recall pseudocode, MCP tool contracts) — HIGH (project's own spec)

---
*Architecture research for: portable provider-agnostic AI agent memory engine*
*Researched: 2026-06-10*
