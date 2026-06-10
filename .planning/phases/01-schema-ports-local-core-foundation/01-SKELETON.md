# Walking Skeleton — MNEMA

**Phase:** 1
**Generated:** 2026-06-10

## Capability Proven End-to-End

A developer calls `await engine.remember("I am allergic to peanuts", user_id="u1", session_id="s1")` and then `await engine.recall("food allergies", user_id="u1")` on the local stack and gets back the stored record — scoped, typed, vector-indexed, with embedding provenance populated — without any network call or cloud dependency.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language + runtime | Python 3.12+, uv-managed src-layout library | Both mandatory provider SDKs (anthropic, dashscope) + FastMCP are Python-first; uv for fast reproducible installs |
| Abstraction pattern | Hand-rolled `typing.Protocol` per axis (not ABC, not LiteLLM as public seam) | Structural typing allows one physical class to satisfy two roles; pyright strict is the enforcement gate; keeps LLM and embedding axes independent |
| Record schema source of truth | Pydantic 2 `MemoryRecord` model; SQL DDL is derived from it | `model_validate(row_dict)` is the single round-trip; no ORM needed; future adapters re-implement the same DDL |
| Local T1 vector store | sqlite-vec 0.1.9 via `aiosqlite` 0.22.1; `vec0` virtual table | Verified working on Windows 11; zero external services; brute-force KNN is sufficient at MNEMA's working-set size |
| T0 object store | `LocalFS` — JSONL-per-session in a temp directory | `t0://session_id/line_offset` ref scheme; append is O(1); deterministic offset for `expand(id)` |
| In-process scheduler | APScheduler 3.11.2 `AsyncIOScheduler`; `trigger_now()` via `job.modify(next_run_time=datetime.now())` | v4.x is alpha with an explicit "do not use in production" warning; v3.x is stable; Scheduler Protocol hides the version |
| Embedding (Phase 1) | `StubEmbedder` — deterministic SHA-256 hash to unit vector, dim=128 | Hermetic and CI-fast; no API calls in the 5-test harness; real embedders (Voyage, bge-m3) land in Phase 4 |
| Async strategy | `async def` for all five verbs and all Protocol methods; pure logic (scoring) stays sync | Avoids the sync→async retrofit trap; native fit for FastMCP (Phase 3) and async cloud adapters (Phase 4) |
| Scope isolation | `user_id` non-defaulted kwarg at Protocol level; enforced centrally in the store query builder composited with `WHERE valid_until IS NULL` | Omission raises `TypeError`; no adapter or future tool can issue an unscoped read |
| Safety column | `protected` is a DDL boolean column, checked before any score math | Structural guarantee; cannot be averaged away by an LLM salience judge; Phase 3 decay loop reads this column first |
| Type checking | pyright strict; ruff lint + format | Adapter Protocols are the contract; a new provider that does not satisfy the interface fails at CI, not runtime |
| Test framework | pytest 8.x + pytest-asyncio 1.4.0, `asyncio_mode = "auto"` | Eliminates `@pytest.mark.asyncio` boilerplate; in-memory SqliteT1 keeps the harness sub-10s |

## Stack Touched in Phase 1

- [x] Project scaffold (uv init --lib, pyproject.toml, src/mnema/ package layout, pytest harness, ruff + pyright config)
- [x] Six async `typing.Protocol` ports (LLMProvider, EmbeddingProvider, ObjectStorePort, RecordStore, VectorIndex, Scheduler)
- [x] Pydantic `MemoryRecord` schema — all un-retrofittable columns present before any data is written
- [x] Database — `SqliteT1` adapter: one real write (upsert + vector upsert) AND one real read (KNN + scope filter)
- [x] T0 — `LocalFS` adapter: JSONL append + line-offset read for `expand(id)`
- [x] Fast write path: T0 append + buffer push + `looks_like_durable_claim` heuristic + provisional T1 write + staging enqueue
- [x] Recall path: dense KNN unioned with session buffer + access-count update
- [x] In-process scheduler: `InProcessScheduler` with `trigger_now()`
- [x] SDK surface: `MemoryEngine` (5 async verbs) + `ScopedHandle` ergonomic front door
- [x] 5-test harness green (`uv run pytest tests/ -v`)

## Out of Scope (Deferred to Later Slices)

- Consolidation, supersession, entity resolution (Phase 2)
- Forgetting, decay pass, salience floor, budget packer (Phase 3)
- MCP server surface — `FastMCP` wiring (Phase 3)
- Cloud providers: Qwen/DashScope LLM, Voyage embeddings, real bge-m3 local embedder (Phase 4)
- Cloud storage: Postgres + pgvector, Alibaba OSS, git vault (Phase 4)
- Config-keyed factory, conformance suite, second backend per axis (Phase 4)
- Hybrid retrieval: BM25 keyword, 1-hop graph expand, RRF fusion (HYBRID-* — v2)
- `KeywordIndex`, `GraphStore`, `HybridSearch` Protocols (additive in v2)
- Dual sync/async SDK surface via unasync codegen
- Trained embedding-head classifier for `looks_like_durable_claim`
- SQLite-backed staging queue (in-memory `asyncio.Queue` in Phase 1)
- Reference demo, evaluation baseline (Phase 5)

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- Phase 2: Offline consolidation pipeline — staging queue drain, typed-record extraction (cheap LLM), salience judgement, entity resolution, active supersession, provisional reconciliation, idempotency
- Phase 3: Decay pass + protected-fact invariant + budget-aware recall packer + T2 vault promotion + MCP server surface (FastMCP)
- Phase 4: Real cloud adapters — Qwen/DashScope, Anthropic/Claude, Voyage, pgvector, OSS/S3, config factory, conformance suite
- Phase 5: Nutrition-coach reference demo + before/after evaluation baseline
