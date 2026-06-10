# Stack Research

**Domain:** Portable, provider-agnostic AI agent memory engine (MCP server + embeddable SDK)
**Researched:** 2026-06-10
**Confidence:** HIGH (core stack verified against PyPI/official docs; MEDIUM on a few version-pin edge cases noted inline)

---

## TL;DR — The Opinionated Picks

1. **Language: Python 3.12+.** Both first-party SDKs you must ship (`anthropic`, `dashscope`) are Python-first, the de-facto MCP framework (`fastmcp`) is Python, and the entire embedding/vector ecosystem (voyageai, pgvector bindings, sqlite-vec) has its richest support in Python. TypeScript is a viable second SDK target later, but Python is where the engine lives.
2. **Provider abstraction: hand-rolled adapter Protocols, NOT LiteLLM as the core seam.** LiteLLM is excellent and you should use it *inside* the default adapters as a convenience, but your portability contract (independent LLM vs embedding axes, swappable per-provider) must be your own narrow `interface`. Don't let a 100+-provider mega-dependency define your public contract.
3. **Vector store: pgvector for the default/cloud path, sqlite-vec for the local path — behind one `VectorStore` adapter.** Both speak the same "store float[] + ANN search + metadata filter" contract. Avoid Qdrant/LanceDB as the *default* (extra service / extra heavy dep); offer them as optional adapters.
4. **Hybrid retrieval: native Postgres `tsvector` + pgvector + hand-rolled RRF.** Do NOT depend on `pg_search`/`pg_textsearch` extensions for the default path — they won't exist on Alibaba RDS or in sqlite. Keep RRF in application code so it works identically across every vector backend.
5. **Embedding-for-Claude: Voyage AI `voyage-3.5` is the canonical pairing** (Anthropic's officially recommended partner), with `nomic-embed-text` / `bge-m3` via a local adapter as the zero-cost offline option. This is the answer to "Claude has no embedder."

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | 3.12+ | Implementation language | Both mandatory provider SDKs (`anthropic`, `dashscope`) and the dominant MCP framework are Python-first. The memory/RAG ecosystem (vector bindings, rerankers, eval harnesses) is Python-native. 3.12 for fast startup + improved typing; cap at 3.13 for now (some C-extension wheels lag on 3.14). |
| **fastmcp** | 3.4.2 | MCP server framework | The de-facto standard — powers ~70% of MCP servers, ~4M downloads/day (Mar 2026). One decorator turns a typed function into an MCP tool with auto schema/validation. Lets `remember/recall/forget/consolidate/expand` be the *same* Python functions exposed by both the MCP server and the SDK. Also offers server composition + an in-process client for tests. |
| **mcp** (official SDK) | 1.12.4 | Protocol primitives | `fastmcp` builds on the official `modelcontextprotocol/python-sdk`; pulled transitively. Pin it only if you need low-level transport control. For MNEMA, stay on FastMCP's high-level API. |
| **PostgreSQL** | 16 or 17 | Default T1 store (relational + vector + FTS) | One engine gives you typed-record rows, `tsvector` keyword search, `pgvector` ANN, and a tiny adjacency table for `graph_edges` — exactly the three indexes the record schema needs, no extra services. Alibaba RDS for PostgreSQL supports pgvector, preserving the "proven on Alibaba Cloud" path. |
| **pgvector** | 0.8.2 | Vector index in Postgres (default) | The standard Postgres vector extension. 0.8.x adds HNSW iterative scan (critical: lets you filter `valid_until IS NULL` *and* still fill k results), `halfvec` (half storage, supports >2000 dims for HNSW). 0.8.2 fixes CVE-2026-3172 (parallel HNSW build buffer overflow) — **pin >= 0.8.2**. |
| **sqlite-vec** | 0.1.x (asg017) | Vector index for the local/embeddable path | Zero-dependency SQLite extension; runs anywhere (laptop, CI, edge), ~30MB memory. Brute-force KNN — slower than HNSW but irrelevant at MNEMA's working-set sizes (thousands of live T1 records, not millions). Makes the SDK genuinely "runs on a laptop with no services." |
| **anthropic** | 0.107.1 | Claude LLM adapter | Official SDK. Powers the Anthropic `LLMProvider` adapter (extraction/salience-judging/reasoning). MIT, Python >=3.9. |
| **dashscope** | latest 1.x (verify on install) | Qwen LLM + Qwen embeddings adapter | Official Alibaba Model Studio SDK. Covers both the **default LLM** (qwen-flash for consolidation, qwen-plus/max for reasoning) and the **default embedder** (`text-embedding-v4`, Qwen3-Embedding). One SDK, both default axes. |
| **voyageai** | latest 0.3.x (verify) | Embedding adapter to pair with Claude | Anthropic's *officially recommended* embedding partner. `voyage-3.5` beats OpenAI text-embedding-3-large by ~8% at ~2.2x lower cost ($0.06/1M tok). This is the clean answer to "Claude ships no embedder": Claude reasoning + Voyage embeddings is a first-class config. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **psycopg** (v3) | 3.2.x | Postgres driver | Async + sync, binary protocol, plays well with pgvector's `register_vector`. Use the `psycopg[binary,pool]` extra. Prefer over the legacy `psycopg2`. |
| **pgvector** (python) | 0.3.x | Postgres ↔ Python vector adapter | `pgvector.psycopg` registers the `vector`/`halfvec` types so you pass `numpy`/`list[float]` directly. |
| **sqlalchemy** | 2.0.x | Optional schema/migrations layer | Only if you want declarative models + Alembic migrations across Postgres/SQLite. Keep it thin — the engine's hot path can use raw SQL for control over RRF/partial-index queries. Skip if you prefer hand-written SQL. |
| **litellm** | 1.7x.x | Convenience layer *inside* default adapters | Use it to implement the Qwen/Anthropic adapters quickly (unified `completion()`/`embedding()`, retries, cost tracking). It supports `dashscope/*` and Anthropic natively. **Wrap it behind your own Protocol — never expose LiteLLM types in MNEMA's public API.** |
| **openai** | 1.x | Optional alt embedding adapter | For an OpenAI `text-embedding-3-large/small` adapter (a common ask). Also the client shape DashScope's OpenAI-compatible endpoint can reuse. |
| **pydantic** | 2.x | Record schema + config validation | The T1 record schema and the provider/backend config map cleanly to Pydantic models; FastMCP already uses Pydantic for tool schemas, so tool I/O types are free. |
| **numpy** | 2.x | Vector math (RRF, recency/salience reweight, cosine) | Needed for in-app fusion + re-rank scoring. |
| **tiktoken** / provider token counters | latest | Budget-aware packing | The packer needs a token count for each `summary`. Use the provider's tokenizer where available; `tiktoken` as a portable approximation for the budget loop. |
| **boto3** | 1.x | S3-compatible object store (T0 cold) | Alibaba OSS exposes an S3-compatible endpoint, so a single `boto3` adapter covers **OSS ↔ S3 ↔ MinIO**; a `LocalFS` adapter covers the laptop path. Avoid a separate OSS-only SDK to keep one code path. |
| **apscheduler** | 4.x | In-process scheduler adapter | Backs the "in-process cron" consolidation trigger for the SDK/laptop path. The cloud path uses Alibaba Function Compute timer / OS cron calling the `consolidate` entrypoint — all behind one `Scheduler` interface. |
| **voyageai / nomic / sentence-transformers** | latest | Local embedding adapter | For the offline embedder option, `sentence-transformers` running `BAAI/bge-m3` or `nomic-ai/nomic-embed-text-v1.5` gives a zero-API-cost embedding adapter — important for "runs on a laptop" and for Claude-without-Voyage configs. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Dependency + venv management | Fast, lockfile-based; ideal for a library that others embed. Produces reproducible installs across the demo/cloud envs. |
| **ruff** | Lint + format | Single fast tool; replaces black+isort+flake8. |
| **pytest** + **pytest-asyncio** | Test + eval harness runner | The custom memory test suite (5→20+ scripted tests) is naturally pytest cases. FastMCP's in-process client lets you test MCP tools without a transport. |
| **pyright/mypy** | Static typing | The adapter Protocols are the contract; type-check them strictly so a new provider that doesn't satisfy the interface fails at CI, not runtime. |
| **testcontainers** | Ephemeral Postgres+pgvector in tests | Spin a real pgvector container so the default-path tests exercise HNSW + partial index, not a mock. |

---

## Installation

```bash
# Engine core (Python project managed with uv)
uv add fastmcp pydantic numpy

# Default provider axis: Qwen (DashScope) for both LLM + embeddings
uv add dashscope

# Anthropic LLM adapter + its recommended embedding partner
uv add anthropic voyageai

# Default vector/relational backend: Postgres + pgvector
uv add "psycopg[binary,pool]" pgvector

# Local/embeddable backend: SQLite + sqlite-vec  (vector extension loaded at runtime)
uv add sqlite-vec

# Object store (OSS/S3/MinIO via one S3 client) + scheduler
uv add boto3 apscheduler

# Optional adapters / convenience
uv add litellm openai sentence-transformers tiktoken

# Dev
uv add --dev pytest pytest-asyncio ruff pyright testcontainers
```

> Version note: pin `pgvector` (the Postgres extension) **>= 0.8.2** in your DB provisioning (CVE-2026-3172). Python package versions for `dashscope`, `voyageai`, `litellm` move fast — resolve exact pins at install time via `uv lock`, don't hardcode from this doc.

---

## The Provider-Abstraction Pattern (the load-bearing design)

This is the core constraint, so it gets its own section. **Define narrow Protocols; ship default implementations that may use LiteLLM/SDKs internally.**

```python
from typing import Protocol, Sequence

class LLMProvider(Protocol):
    def complete(self, prompt: str, *, model: str, **kw) -> str: ...
    def extract_records(self, batch: list[Turn]) -> list[Record]: ...  # consolidation
    def judge_salience(self, record: Record) -> float: ...

class EmbeddingProvider(Protocol):           # INDEPENDENT axis
    @property
    def dim(self) -> int: ...
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

class VectorStore(Protocol):
    def upsert(self, records: list[Record]) -> None: ...
    def vector_search(self, q: list[float], k: int, where: str) -> list[Hit]: ...
    def keyword_search(self, query: str, k: int) -> list[Hit]: ...  # tsvector / FTS5
    def graph_expand(self, ids: list[str], hops: int) -> list[Hit]: ...

class ObjectStore(Protocol): ...   # OSS/S3/MinIO/LocalFS  -> one boto3 + one FS impl
class Scheduler(Protocol): ...     # FunctionCompute / cron / apscheduler in-process
```

**Why hand-rolled and not LiteLLM-as-the-interface:**
- The **independent embedding axis** is the whole point. LiteLLM couples `completion` and `embedding` under one client/config; MNEMA must let `llm=anthropic, embedder=voyage` or `llm=claude, embedder=local-bge` be selected separately. Your two Protocols make that explicit and type-checked.
- `EmbeddingProvider.dim` is a first-class part of the contract — the vector column dimension is fixed at table-create time, so the config system must read `dim` from the embedder and refuse a mismatch. A generic gateway hides this; your interface surfaces it.
- LiteLLM is still the right tool *inside* `QwenLLMProvider`/`AnthropicLLMProvider` to avoid re-writing retry/streaming/cost plumbing. Use it as an implementation detail, not the public seam.

**Config (default = Qwen + Alibaba):**
```yaml
llm:        { provider: dashscope, reasoning_model: qwen-plus, curate_model: qwen-flash }
embedding:  { provider: dashscope, model: text-embedding-v4, dim: 1024 }
vector:     { backend: pgvector, dsn: ${PG_DSN} }
object:     { backend: s3, endpoint: ${OSS_ENDPOINT} }   # OSS via S3-compat
scheduler:  { backend: function_compute }
```
Swap to a fully-local laptop config by flipping `embedding.provider: local`, `vector.backend: sqlite-vec`, `object.backend: localfs`, `scheduler.backend: inprocess` — no code change.

---

## Embedding-for-Claude — the explicit answer

Claude ships **no first-party embedder by deliberate product choice**, so the embedding axis must be decoupled. Recommended pairings, in priority order:

| When | Embedder | Dim | Cost | Confidence | Notes |
|------|----------|-----|------|------------|-------|
| Claude + best quality / managed | **Voyage `voyage-3.5`** | 1024 (also 256/512/2048) | $0.06/1M tok | HIGH | Anthropic's officially recommended partner; ~8% better than OpenAI-3-large at lower cost. The canonical "Claude + embeddings" answer. |
| Claude + already-on-OpenAI | OpenAI `text-embedding-3-large` | 3072 (or reduced) | $0.13/1M tok | HIGH | Fine, slightly pricier/weaker than Voyage. Easy adapter. |
| Claude + zero API cost / offline / privacy | local `bge-m3` or `nomic-embed-text-v1.5` | 1024 / 768 | $0 | MEDIUM | Via `sentence-transformers`/Ollama. Best for the laptop path; pairs with sqlite-vec for a fully-local stack. |
| Default stack (any LLM) | Qwen `text-embedding-v4` | 1024 (64–2048, Matryoshka) | DashScope-priced | HIGH | The default embedder; keeps the Qwen+Alibaba proof path canonical. Can pair with **either** Qwen or Claude as the LLM. |

**Design implication:** because dims differ per embedder (1024 vs 768 vs 3072), the vector column dimension is a config-time decision derived from `EmbeddingProvider.dim`. Switching embedders requires a re-embed + re-index migration — document this and provide a `reindex` utility. Use `halfvec` if you adopt a 2048/3072-dim embedder to stay under HNSW limits and halve storage.

---

## Hybrid Retrieval (BM25 + dense + RRF) — portable approach

| Concern | Recommendation | Why |
|---------|----------------|-----|
| Dense | pgvector HNSW (default) / sqlite-vec KNN (local) | Behind `VectorStore.vector_search`. |
| Keyword/"BM25" | **Postgres native `tsvector` + `ts_rank_cd`** (default); SQLite **FTS5** (local) | Portable, zero extra extensions. `ts_rank` is not true BM25, but for MNEMA's short typed records the difference is negligible — and RRF (rank-based, score-agnostic) makes the absolute scores irrelevant anyway. |
| Fusion | **Hand-rolled RRF in Python**, `k=60` | `score = Σ 1/(60+rank)` across dense/sparse/graph lists. Application-side fusion means it works identically on pgvector and sqlite-vec, and you keep the salience/recency re-rank multiplier from the build plan in the same place. |
| Graph expand | Small `graph_edges` adjacency table, 1-hop SQL | No graph DB needed (see What NOT to Use). |

**Do NOT take a hard dependency on `pg_search` (ParadeDB) or `pg_textsearch` (TigerData) for the default path.** They give true BM25 but are Postgres extensions unavailable on managed Alibaba RDS and absent from the SQLite path — they'd break portability. Offer ParadeDB only as an *optional* high-end vector/FTS adapter for users who self-host it.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Python | TypeScript | If the *primary* consumer is a Node/web app and you can tolerate calling DashScope via its OpenAI-compatible HTTP endpoint (no first-party TS SDK as rich as Python's). Reasonable as a **second** SDK binding later, not the engine core. |
| pgvector (default) | Qdrant | If you need >10M vectors, payload-filtered ANN at scale, or distributed sharding. Overkill for thousands of *live* T1 records; adds a service to operate. Ship as optional adapter. |
| sqlite-vec (local) | LanceDB | If the local path also needs analytical/columnar queries over multimodal data, or millions of local vectors with IVF-PQ speed. Heavier dependency; unnecessary at MNEMA's local scale. |
| Hand-rolled adapters | LiteLLM as the public seam | If you ever drop the independent-embedding-axis requirement and want 100+ providers for free. You don't — keep LiteLLM internal. |
| Native tsvector + RRF | ParadeDB `pg_search` (true BM25) | If a user self-hosts Postgres and wants Elasticsearch-grade lexical relevance at large scale. Optional adapter only. |
| Voyage `voyage-3.5` | OpenAI `text-embedding-3-large` | If the deployment is already standardized on OpenAI infra/billing. |
| boto3 (S3-compat) | Alibaba `oss2` SDK | Only if you need OSS-specific features (e.g. advanced lifecycle rules) the S3-compat layer doesn't expose. One S3 client is the more portable default. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Neo4j / any heavyweight graph DB** | The build plan explicitly rejects the "Neo4j tax." Graph needs are 1-hop edge expansion over `graph_edges`. A full graph DB is an extra service, extra ops, and unportable to the laptop path. | Small adjacency table + 1-hop SQL recursive/JOIN query. |
| **pg_search / pg_textsearch as the *default* FTS** | Postgres extensions unavailable on managed Alibaba RDS and absent in SQLite — breaks the portability contract. | Native `tsvector`/`ts_rank` (PG) + FTS5 (SQLite), RRF in app. |
| **LiteLLM/LangChain as the public abstraction layer** | Couples LLM and embedding under one client (kills the independent-axis requirement), and leaks a huge dependency surface into your contract. LangChain especially adds churn and indirection for a memory engine that needs precise control over packing/fusion. | Narrow hand-rolled Protocols; use LiteLLM internally only. |
| **psycopg2 (legacy)** | Maintenance-mode, sync-only, clumsier type registration. | psycopg 3 (`psycopg[binary,pool]`). |
| **Pinecone / hosted-only vector DB as default** | A network service can't satisfy "runs identically on a laptop"; vendor lock-in contradicts the portability thesis. | pgvector (cloud) + sqlite-vec (local) behind one adapter; Pinecone optional. |
| **Hard DELETE on eviction** | Build plan requires eviction to be recoverable/auditable to cold storage. | Move to T0/OSS cold store; set `valid_until`/archive flag, never destroy. |
| **A second OSS-specific object SDK in the hot path** | Two object-store code paths to maintain. | One boto3 S3-compatible client for OSS/S3/MinIO + a LocalFS impl. |

---

## Stack Patterns by Variant

**If default / hackathon-proof / cloud (Qwen + Alibaba):**
- LLM+embeddings: DashScope (`qwen-flash` curate, `qwen-plus` reason, `text-embedding-v4` @ 1024d)
- Vector+relational: Postgres 16 + pgvector 0.8.2 (HNSW, partial index `WHERE valid_until IS NULL`)
- Object store: Alibaba OSS via boto3 S3-compat; Scheduler: Function Compute timer → `consolidate`
- Because: preserves the "proven on Alibaba Cloud" submission path with one SDK covering both model axes.

**If fully local / embeddable SDK / laptop demo:**
- LLM: any (Claude or Qwen via API); embeddings: local `bge-m3`/`nomic-embed-text` via sentence-transformers
- Vector: SQLite + sqlite-vec; relational+FTS: same SQLite (FTS5); object store: LocalFS; scheduler: APScheduler in-process
- Because: zero external services, runs in CI and on a plane; proves the portability thesis.

**If reasoning-quality-first (Claude) with managed infra:**
- LLM: Anthropic `claude` (reasoning + extraction); embeddings: Voyage `voyage-3.5` @ 1024d
- Vector: Postgres + pgvector; rest as cloud default
- Because: best reasoning + best-recommended embeddings; demonstrates the independent-axis design directly.

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| fastmcp 3.4.2 | mcp 1.12.4 | FastMCP builds on the official SDK; let FastMCP pin it. Don't dual-pin a conflicting `mcp`. |
| pgvector (ext) >= 0.8.2 | PostgreSQL 13–18 | 0.8.2 fixes CVE-2026-3172. HNSW iterative scan (0.8.0+) is what makes `valid_until IS NULL` filtered search reliably return k results. |
| pgvector (py) 0.3.x | psycopg 3.2.x | Use `pgvector.psycopg.register_vector`; supports `vector` + `halfvec`. |
| sqlite-vec 0.1.x | Python 3.12 sqlite3 | Load via `db.enable_load_extension(True); sqlite_vec.load(db)`. Ensure the bundled SQLite supports loadable extensions (Linux/macOS fine; on Windows verify the wheel ships the extension). |
| anthropic 0.107.1 | Python >=3.9 | MIT. |
| voyageai 0.3.x | voyage-3.5 / voyage-4 family | `output_dimension` ∈ {256,512,1024,2048}; pick once, fix the vector column to match. |
| halfvec | HNSW up to 4000 dims | Use if you adopt a 2048+/3072-dim embedder; minimal recall loss, half storage. |

---

## Confidence Assessment

| Recommendation | Confidence | Basis |
|----------------|------------|-------|
| Python as engine language | HIGH | Both mandatory SDKs + FastMCP are Python-first (PyPI/GitHub verified). |
| fastmcp 3.4.2 / mcp 1.12.4 | HIGH | PyPI + jlowin.dev + Context7 (mcp 1.12.4) verified Jun 2026. |
| pgvector 0.8.2 + CVE pin | HIGH | postgresql.org news + pgvector CHANGELOG verified. |
| Voyage as Claude's embedder | HIGH | Anthropic official docs (platform.claude.com/docs/.../embeddings) recommend Voyage; partnership, not acquisition. |
| anthropic 0.107.1 / dashscope text-embedding-v4 | HIGH | PyPI + Alibaba Model Studio docs (updated Mar 2026). |
| voyageai/litellm/sentence-transformers exact pins | MEDIUM | Fast-moving; resolve at `uv lock` time rather than trusting a pinned number here. |
| sqlite-vec Windows extension loading | MEDIUM | Generally supported; verify the wheel ships the extension for Windows demo machines. |
| Hand-rolled RRF over native tsvector being "good enough" vs true BM25 | MEDIUM | RRF is rank-based so absolute scores don't matter; true BM25 only matters at larger lexical scale — flag for a focused eval if recall on keyword-heavy queries underperforms. |

---

## Sources

- `/modelcontextprotocol/python-sdk` (Context7) — MCP SDK v1.12.4 confirmed
- https://pypi.org/project/fastmcp/ + https://jlowin.dev/blog/fastmcp-3 — FastMCP 3.4.2 (Jun 6 2026), 70% of MCP servers — HIGH
- https://pypi.org/project/anthropic/ — anthropic 0.107.1 (Jun 7 2026) — HIGH
- https://pypi.org/project/dashscope/ + https://www.alibabacloud.com/help/en/model-studio/embedding — DashScope SDK + text-embedding-v4 (64–2048d, 1024 default), docs updated Mar 2026 — HIGH
- https://www.postgresql.org/about/news/pgvector-082-released-3245/ + https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md — pgvector 0.8.2, CVE-2026-3172, halfvec, HNSW iterative scan — HIGH
- https://platform.claude.com/docs/en/build-with-claude/embeddings + https://docs.claude.com/en/docs/build-with-claude/embeddings — Anthropic recommends Voyage; ships no embedder — HIGH
- https://blog.voyageai.com/2025/05/20/voyage-3-5/ + https://docs.voyageai.com/docs/embeddings — voyage-3.5 dims/pricing, +8% vs OpenAI-3-large — HIGH
- https://docs.litellm.ai/docs/providers/dashscope — LiteLLM supports dashscope/* + Anthropic — HIGH
- https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual + https://www.softwareseni.com/replacing-elasticsearch-with-postgres-using-bm25-hybrid-search-and-rrf/ — RRF k=60, BM25+pgvector hybrid pattern — MEDIUM
- https://github.com/asg017/sqlite-vec — sqlite-vec embeddable, cross-platform, ~30MB — HIGH
- https://elephas.app/blog/best-embedding-models + Milvus/pecollective embedding comparisons (Apr 2026) — embedder MTEB/cost landscape — MEDIUM

---
*Stack research for: portable provider-agnostic AI agent memory engine (MNEMA)*
*Researched: 2026-06-10*
