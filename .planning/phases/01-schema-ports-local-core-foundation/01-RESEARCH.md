# Phase 1: Schema, Ports & Local Core Foundation - Research

**Researched:** 2026-06-10
**Domain:** Python async typed memory engine — sqlite-vec/aiosqlite local stack, hand-rolled typing.Protocol ports, Pydantic 2 record schema, APScheduler in-process, pytest-asyncio harness
**Confidence:** HIGH (all critical claims verified by direct code execution on the target Windows 11 machine or official docs; MEDIUM items flagged inline)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Scope Model & Recall Boundary (D-01, D-02, D-03)**
- `remember(content, *, user_id, session_id, agent_id=None)` + `recall(query, *, user_id, agent_id=None)` as the explicit required-kwarg wire format.
- `engine.scope(user_id=..., agent_id=None)` as the ergonomic SDK front door (thin view; carries `user_id`/`agent_id`; `session_id` is per-`remember`).
- `user_id` = hard isolation boundary, non-defaulted at the Protocol level (`TypeError` on omission), enforced centrally in the store's query builder.
- `session_id` = stamped at write, never in the recall WHERE-clause.
- `agent_id` = optional narrowing filter inside the user boundary.

**Provisional-Write Trigger (D-04, D-05, D-06)**
- Ship the always-on heuristic floor (first-person + stative-verb cues, no `?`, modal filtering) plus honor a caller-supplied `type=` / `durable=True` hint.
- Design the classifier seam but DEFER the trained embedding-head.
- Bias toward recall on safety/`fact` claims; precision on `event` chit-chat.
- Flash-tier LLM micro-classify REJECTED on the write path.

**Port Seam Granularity (D-07, D-08, D-09, D-10)**
- Ship `RecordStore` + `VectorIndex` as segregated role Protocols NOW (dense-only).
- `KeywordIndex`, `GraphStore`, `HybridSearch` are deferred, purely additive later.
- One physical class (e.g. `class SqliteT1(RecordStore, VectorIndex)`) satisfies both roles.
- Static checking (pyright/mypy strict) is the enforcement; no `@runtime_checkable` yet.

**SDK Concurrency & API Style (D-11, D-12, D-13)**
- `async def` for all five verbs and all Protocol methods.
- Pure logic (scoring, budget packing) stays synchronous / event-loop-free.
- Sync adapters wrapped in `asyncio.to_thread` at the leaf inside the adapter.

### Claude's Discretion
- Exact heuristic cue lexicon and thresholds for D-04 (tune against the harness).
- Record persistence representation (JSON-blob + projected index columns vs normalized columns) — constrained by D-07's role split and cross-backend portability.
- Whether local vector path uses `aiosqlite` vs `sqlite3` + `asyncio.to_thread` (D-13 governs either way).
- Buffer implementation details (in-memory per-session deque; K turns) and staging-queue representation on the local stack.

### Deferred Ideas (OUT OF SCOPE for Phase 1)
- Hybrid retrieval (BM25, graph, RRF fusion — HYBRID-01/02/03, v2).
- Trained embedding-head classifier for the provisional-write trigger.
- Dual sync/async SDK surface via `unasync`-style codegen.
- Flash-tier LLM judgement of durable claims (belongs in Phase 2 offline consolidation).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-01 | Every record carries scope ids (`user_id`/`agent_id`/`session_id`); all reads and writes filter by scope | Schema section; scope enforcement pattern; vec0 JOIN filter verified |
| CORE-02 | Every record is a typed document following the v2 schema | Pydantic model pattern; normalized-columns approach |
| CORE-03 | Every record stores embedding provenance (`embedding_model`, `embedding_dim`, `embedding_version`) | Schema column list; startup dim-assert pattern |
| CORE-04 | Every record carries a structural `protected` boolean independent of salience | Schema section; `protected` as a first-class column |
| CORE-05 | T1 uses a live filter so only `valid_until IS NULL` records are on the hot retrieval path | vec0 KNN + JOIN filter verified; partial index DDL |
| TIER-01 | T0 raw episodic log appends verbatim turns, append-only, cold object storage | LocalFS ObjectStore adapter pattern |
| TIER-02 | T1 working memory stores typed records with a vector index for dense retrieval | SqliteT1 class; vec0 DDL; KNN query pattern — all verified |
| TIER-04 | A recent-session buffer holds the last K turns | In-memory deque pattern; buffer-union recall |
| WRITE-01 | On each turn, engine appends to T0 and pushes to buffer at zero model cost | Write-path orchestrator; T0 append + deque.append |
| WRITE-02 | A durable-looking claim is written as provisional T1 record with single embedding call | looks_like_durable_claim heuristic; provisional upsert pattern |
| WRITE-03 | Fast write path never blocks on a reasoning LLM | Architecture guarantee enforced by Protocol design |
| WRITE-04 | Each write enqueues the turn to a staging queue for deferred extraction | In-memory staging deque on local path |
| RECALL-01 | `recall` embeds the query and runs dense vector search over live records | vec0 KNN + `valid_until IS NULL` JOIN filter verified |
| RECALL-02 | `recall` unions vector results with the recent-session buffer | Buffer-union + dedup pattern |
| RECALL-06 | `expand(id)` returns verbatim T0 detail on demand | LocalFS ObjectStore.get pattern |
| RECALL-07 | Accessing a record updates `access_count` and `last_accessed` | SQLite UPDATE pattern in RecordStore |
| PROV-01 | LLM provider behind a single interface | `LLMProvider` Protocol; stub for Phase 1 |
| PROV-02 | Embedding provider configured independently from LLM | `EmbeddingProvider` Protocol with `dim` property; verified |
| PROV-06 | Embeddings normalized at adapter; `embedding_dim` asserted at startup | normalize-at-adapter pattern; startup assert |
| SCHED-01 | Consolidation trigger behind a scheduler port | `Scheduler` Protocol; APScheduler 3.x implementation |
| SCHED-02 | In-process scheduler ships with `trigger_now()` | `job.modify(next_run_time=datetime.now())` pattern verified |
| IFACE-01 | Importable SDK exposes typed `remember`/`recall`/`forget`/`consolidate`/`expand` | `MemoryEngine` class; `ScopedHandle` front door |
| EVAL-01 | Custom test harness covers five capability scenarios | pytest-asyncio 1.4.0; 5-test structure documented |
</phase_requirements>

---

## Summary

Phase 1 is the schema-and-ports first cut: everything downstream depends on getting the T1 record columns right (the un-retrofittable ones), the six adapter Protocols right (avoiding the ISP-retrofit trap), and the local stack proved end-to-end before any cloud dependency lands. The research below answers every concrete implementation question that was flagged as needing verification.

**Most important finding:** sqlite-vec 0.1.9 works correctly on Windows 11 with Python 3.13 — both with `sqlite3` directly and with `aiosqlite`. The pre-2026 GitHub issues (Issues #13, #45) about Windows DLL load failures were caused by trying to load the raw `.dll` file manually rather than using the Python wheel's `sqlite_vec.loadable_path()` function, which the 0.1.9 wheel resolves correctly. The `enable_load_extension` call works without restriction on the target machine. **For aiosqlite, the required pattern is `await db.load_extension(sqlite_vec.loadable_path())` — the sync `sqlite_vec.load(conn)` is sqlite3-only.**

**Key planning inputs:**
1. Use `aiosqlite` (not `sqlite3 + asyncio.to_thread`) — it has a native async extension-loading API, is production-stable (0.22.1), and avoids the threading complexity of D-13's "wrap in `asyncio.to_thread`" approach.
2. Use APScheduler 3.11.2 (not 4.x, which is still alpha). The `AsyncIOScheduler` with `job.modify(next_run_time=datetime.now())` delivers the `trigger_now()` pattern with zero risk.
3. The `looks_like_durable_claim` heuristic is a simple regex classifier — verified working in under 30 lines with all target test cases passing.
4. The vec0 `k=` parameter fetches globally (before JOIN filter) — for Phase 1's single-user scope this is fine; document for Phase 4 multi-user.
5. Pydantic `model_validate(row_dict)` with `sqlite3.row_factory` is the clean single-source-of-truth pattern between the Python schema and the SQL schema.

**Primary recommendation:** Build the record schema (`schema.py`) and the six Protocols (`ports/`) in a single Wave 0, verify pyright accepts them strictly, then write the local adapters one port at a time, each immediately tested by the harness fixture.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Record schema definition | Core (`schema.py`) | — | Pydantic model is the single source of truth; SQL DDL is derived from it |
| Scope enforcement (user_id isolation) | Core query builder | Adapter (WHERE clause) | Core states the invariant; adapter implements it |
| Fast write path (T0 + buffer + provisional T1) | Core (`write_path.py`) | Adapter (I/O only) | Zero logic in adapters; all classification/routing in core |
| Dense recall (vec0 KNN) | Adapter (`SqliteT1.vector_search`) | Core (`recall.py` orchestrates) | KNN is adapter-specific; core does the buffer union and result shaping |
| Buffer-union freshness | Core (`buffer.py` + `recall.py`) | — | In-memory; no I/O |
| looks_like_durable_claim classification | Core (`write_path.py`) | — | Pure logic; no I/O; deterministic regex |
| Embedding normalization | Adapter (`EmbeddingProvider.embed`) | — | Normalize-at-adapter so core never sees unnormalized vectors |
| T0 cold append / expand(id) | Adapter (`LocalFS`) | — | Pure I/O |
| Scheduler trigger | Adapter (`InProcessScheduler`) | — | APScheduler is an adapter detail; Scheduler Protocol is the contract |
| Test hermetic environment | Tests (`StubEmbedder` + `SqliteT1` in-memory) | — | No real API calls in the 5-test harness |

---

## Standard Stack

### Core (Phase 1 local path)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **Python** | 3.12+ (dev: 3.13) | Implementation language | Both mandatory provider SDKs + FastMCP are Python-first; 3.12+ for fast startup + improved typing |
| **pydantic** | 2.12.5 | T1 record schema + config validation | `model_validate(dict)` is the single-source mapping between Python and SQL; FastMCP already uses it |
| **aiosqlite** | 0.22.1 | Async SQLite (T1 + T0 local path) | Native async extension loading API; single-thread-per-connection model; production-stable |
| **sqlite-vec** | 0.1.9 | Vector index via vec0 virtual table | Zero-dependency, runs anywhere SQLite runs; Windows 11 wheel verified working; brute-force KNN at MNEMA's scale |
| **numpy** | 2.4.4 | Float32 vector serialization + math | vec0 accepts `numpy.ndarray.tobytes()` directly; needed for normalization at adapter |
| **apscheduler** | 3.11.2 | In-process scheduler (SCHED-01/02) | `AsyncIOScheduler` integrates cleanly with asyncio; `trigger_now()` via `job.modify`; v4.x is still alpha — use v3 |
| **uv** | 0.9.24 | Dependency management | Fast, lockfile-based; src-layout library support; recommended for embeddable libraries |

### Development Tools

| Tool | Version | Purpose |
|------|---------|---------|
| **pytest** | 8.x | Test runner |
| **pytest-asyncio** | 1.4.0 | Async test support | 
| **ruff** | latest | Lint + format (replaces black+isort+flake8) |
| **pyright** | latest | Static typing (strict mode) |

### Supporting (deferred to later phases but listed for awareness)

| Library | Phase | Purpose |
|---------|-------|---------|
| **sentence-transformers** | Phase 1 optional / Phase 4 | Local embedder for `bge-m3` (1024d); not needed in Phase 1 if using StubEmbedder |
| **fastmcp** | Phase 3 | MCP server surface |
| **psycopg** | Phase 4 | Postgres driver for cloud path |
| **boto3** | Phase 4 | S3/OSS object store |

### Installation (Phase 1 minimal)

```bash
uv init --lib mnema
uv add pydantic numpy aiosqlite sqlite-vec apscheduler
uv add --dev pytest "pytest-asyncio>=1.4" ruff pyright
```

**Version verification** — confirmed against PyPI on 2026-06-10:

```
pydantic     2.12.5   (2026-05-xx)
aiosqlite    0.22.1   (2025-12-23)
sqlite-vec   0.1.9    (2026-03-31)
numpy        2.4.4    (2026-xx-xx)
apscheduler  3.11.2   (2025-12-22)
pytest-asyncio 1.4.0  (2026-05-26)
```

---

## Architecture Patterns

### System Architecture Diagram (Phase 1 scope)

```
SDK caller / test
       |
       | remember(content, *, user_id, session_id) / recall(query, *, user_id)
       v
  MemoryEngine                       (core/engine.py — async def)
   |     |     |
   |     |     +-- ScopedHandle.scope(user_id, agent_id)  [thin ergonomic wrapper]
   |     |
   |     v
  WritePath                          (core/write_path.py)
   |   |   |
   |   |   +---> RecentSessionBuffer.push(turn)          [in-memory deque]
   |   |
   |   +-------> ObjectStorePort.append(session_id, turn)  --> LocalFS (T0)
   |
   +-- if looks_like_durable_claim(turn):
   |       EmbeddingProvider.embed(content) --> StubEmbedder (Phase 1)
   |       RecordStore.upsert(provisional=True)   --> SqliteT1
   |       VectorIndex.upsert_vector(id, embedding) --> SqliteT1 (same connection)
   |
   +-- staging_queue.append({turn, t0_id})       [in-memory deque]
   |
   v
  RecallPath                         (core/recall.py)
   |   |
   |   +-- EmbeddingProvider.embed(query)
   |   +-- VectorIndex.vector_search(q_vec, k=30, user_id=user_id)  --> SqliteT1
   |   +-- RecentSessionBuffer.as_candidates(user_id)
   |   +-- dedupe(vector_results + buffer_candidates)
   |   +-- RecordStore.update_access(ids)        --> SqliteT1
   |
   v
  SchedulerPort.trigger_now()        --> InProcessScheduler (APScheduler 3.x)
  (consolidate stub in Phase 1; real logic in Phase 2)
```

### Recommended Project Structure

```
src/mnema/
├── core/                      # NO vendor imports — depends only on ports/
│   ├── engine.py              # MemoryEngine public API (5 verbs, async def)
│   ├── schema.py              # MemoryRecord (Pydantic), RecordType, Turn enums
│   ├── write_path.py          # WritePath: T0 append + buffer + provisional T1
│   ├── recall.py              # RecallPath: dense recall + buffer union + access-count
│   ├── buffer.py              # RecentSessionBuffer: in-memory deque, K turns
│   └── classifier.py          # looks_like_durable_claim heuristic (no I/O)
│
├── ports/                     # Pure Protocol contracts — Phase 1 set
│   ├── llm.py                 # LLMProvider (stub in Phase 1)
│   ├── embedding.py           # EmbeddingProvider (StubEmbedder + protocol)
│   ├── object_store.py        # ObjectStorePort (append/get/archive)
│   ├── record_store.py        # RecordStore (CRUD for typed records)
│   ├── vector_index.py        # VectorIndex (dense search — Phase 1 only)
│   └── scheduler.py           # Scheduler (schedule + trigger_now)
│
├── adapters/
│   ├── embedding/
│   │   └── stub.py            # StubEmbedder: deterministic hash-based, dim=N
│   ├── object_store/
│   │   └── local_fs.py        # LocalFS: file-per-session in a base dir
│   ├── vector_store/
│   │   └── sqlite_t1.py       # SqliteT1: implements RecordStore + VectorIndex
│   └── scheduler/
│       └── in_process.py      # InProcessScheduler: APScheduler AsyncIOScheduler
│
└── surfaces/
    └── __init__.py            # SDK re-export: from mnema import MemoryEngine, ScopedHandle

tests/
├── conftest.py                # shared fixtures: in-memory SqliteT1, StubEmbedder, engine
├── test_remember_recall.py    # 5-test harness (EVAL-01)
└── test_scope_isolation.py    # CORE-01 enforcement
```

### Pattern 1: The T1 Record Schema (Pydantic as single source of truth)

**What:** Pydantic model defines the record shape. The SQL DDL is derived from it (no ORM — explicit DDL mirrors the model fields). The row-factory converts SELECT results back to Pydantic models via `model_validate(dict(row))`.

**The un-retrofittable columns — must exist before any data is written:**

```python
# Source: mnema-build-plan.md §2 + PITFALLS.md Pitfall 1 + 6
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from enum import StrEnum
import uuid
from datetime import datetime

class RecordType(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    PROCEDURE = "procedure"

class MemoryRecord(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    # Identity + scope (CORE-01) — ALL mandatory
    id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:12]}")
    user_id: str                          # hard isolation boundary
    session_id: str                       # write-time provenance only
    agent_id: Optional[str] = None       # optional narrowing

    # Content (CORE-02)
    record_type: RecordType
    content: str
    summary: str = ""                    # <= ~12 tokens; packer injects this
    keywords: list[str] = Field(default_factory=list)  # Phase 2 BM25, ignored now

    # Embedding provenance (CORE-03) — un-retrofittable
    embedding_model: Optional[str] = None
    embedding_dim: Optional[int] = None
    embedding_version: Optional[str] = None

    # Safety (CORE-04) — structural, not a score threshold
    protected: bool = False              # decay pass skips this BEFORE any score math

    # Lifecycle + supersession
    salience: float = 0.5
    confidence: float = 0.9
    provisional: bool = True            # cleared by consolidation (Phase 2)
    valid_from: datetime = Field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = None   # CORE-05: hot path filters IS NULL
    superseded_by: Optional[str] = None

    # Provenance
    t0_ref: Optional[str] = None        # "t0://session_id/offset" — backs expand(id)
    source_refs: list[str] = Field(default_factory=list)

    # Reinforcement (RECALL-07)
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Graph edges (Phase 2, store empty for now)
    graph_edges: list[dict] = Field(default_factory=list)
```

**SQL DDL derived from the model (split into two tables for sqlite-vec):**

```sql
-- Source: verified sqlite-vec pattern + CORE-01..05 requirements
CREATE TABLE IF NOT EXISTS t1_records (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,       -- CORE-01 scope
    session_id      TEXT NOT NULL,
    agent_id        TEXT,
    record_type     TEXT NOT NULL,
    content         TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    keywords        TEXT NOT NULL DEFAULT '[]',   -- JSON array
    embedding_model TEXT,                -- CORE-03 provenance
    embedding_dim   INTEGER,
    embedding_version TEXT,
    protected       INTEGER NOT NULL DEFAULT 0,  -- CORE-04 structural flag
    salience        REAL NOT NULL DEFAULT 0.5,
    confidence      REAL NOT NULL DEFAULT 0.9,
    provisional     INTEGER NOT NULL DEFAULT 1,
    valid_from      TEXT NOT NULL,
    valid_until     TEXT,                -- NULL = live; CORE-05 hot path filter
    superseded_by   TEXT,
    t0_ref          TEXT,
    source_refs     TEXT NOT NULL DEFAULT '[]',  -- JSON array
    access_count    INTEGER NOT NULL DEFAULT 0,
    last_accessed   TEXT,
    created_at      TEXT NOT NULL,
    graph_edges     TEXT NOT NULL DEFAULT '[]'   -- JSON array, Phase 2
);

-- Partial index for the hot retrieval path (CORE-05)
CREATE INDEX IF NOT EXISTS idx_t1_live_user
    ON t1_records(user_id, agent_id)
    WHERE valid_until IS NULL;

-- vec0 virtual table: stores vectors with a TEXT foreign key
CREATE VIRTUAL TABLE IF NOT EXISTS vec_t1 USING vec0(
    record_id TEXT PRIMARY KEY,
    embedding float[{dim}]              -- dim comes from EmbeddingProvider.dim
);
```

**Row mapping (Pydantic model_validate from sqlite3.Row):**

```python
# Source: verified on Python 3.13 + pydantic 2.12.5
import sqlite3, json
from mnema.core.schema import MemoryRecord

def make_row_factory(model_class):
    def factory(cursor: sqlite3.Cursor, row: tuple) -> model_class:
        cols = [d[0] for d in cursor.description]
        row_dict = dict(zip(cols, row))
        # Deserialize JSON columns
        for col in ('keywords', 'source_refs', 'graph_edges'):
            if col in row_dict and isinstance(row_dict[col], str):
                row_dict[col] = json.loads(row_dict[col])
        # SQLite stores bool as int
        row_dict['protected'] = bool(row_dict.get('protected', 0))
        row_dict['provisional'] = bool(row_dict.get('provisional', 1))
        return model_class.model_validate(row_dict)
    return factory
```

### Pattern 2: The Six Ports as async typing.Protocol

**What:** Six narrow Protocols; concrete adapters satisfy them structurally. No inheritance required. Static checking via pyright/mypy strict.

```python
# Source: CONTEXT.md D-07/D-08 + typing docs + verified pyright-compatible pattern
from typing import Protocol, AsyncIterator
from mnema.core.schema import MemoryRecord, Turn

# ---- EmbeddingProvider (PROV-02) ----
class EmbeddingProvider(Protocol):
    @property
    def dim(self) -> int: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    # Normalization contract: ALWAYS returns L2-normalized (unit) vectors

# ---- RecordStore (D-07 segregated role) ----
class RecordStore(Protocol):
    async def upsert(self, record: MemoryRecord) -> None: ...
    async def get(self, record_id: str) -> MemoryRecord | None: ...
    async def update(self, record_id: str, **fields: object) -> None: ...
    async def live_records(self, user_id: str) -> AsyncIterator[MemoryRecord]: ...

# ---- VectorIndex (D-07 segregated role) ----
class VectorIndex(Protocol):
    async def upsert_vector(self, record_id: str, embedding: list[float]) -> None: ...
    async def vector_search(
        self, query_vec: list[float], k: int, *, user_id: str, agent_id: str | None = None
    ) -> list[tuple[str, float]]: ...   # [(record_id, distance), ...]
    async def delete_vector(self, record_id: str) -> None: ...

# ---- ObjectStorePort (TIER-01) ----
class ObjectStorePort(Protocol):
    async def append(self, session_id: str, turn: Turn) -> str: ...   # returns t0://ref
    async def get(self, ref: str) -> Turn: ...                         # backs expand(id)
    async def archive(self, record: MemoryRecord) -> str: ...          # eviction

# ---- LLMProvider (PROV-01) — stub in Phase 1 ----
class LLMProvider(Protocol):
    async def complete(self, prompt: str, *, model: str | None = None) -> str: ...

# ---- Scheduler (SCHED-01/02) ----
class Scheduler(Protocol):
    def schedule(self, fn: object, *, every_seconds: int) -> None: ...
    def trigger_now(self) -> None: ...
    def start(self) -> None: ...
    def shutdown(self) -> None: ...
```

**One physical adapter satisfying two roles (D-08):**

```python
# SqliteT1 satisfies BOTH RecordStore AND VectorIndex
# No multiple inheritance from abstract classes — pure structural typing
class SqliteT1:  # satisfies RecordStore + VectorIndex by structure
    def __init__(self, db_path: str, dim: int) -> None: ...

    async def upsert(self, record: MemoryRecord) -> None: ...     # RecordStore
    async def get(self, record_id: str) -> MemoryRecord | None: ...
    async def update(self, record_id: str, **fields: object) -> None: ...
    async def live_records(self, user_id: str) -> AsyncIterator[MemoryRecord]: ...

    async def upsert_vector(self, record_id: str, embedding: list[float]) -> None: ...  # VectorIndex
    async def vector_search(self, query_vec: list[float], k: int, *, user_id: str, agent_id: str | None = None) -> list[tuple[str, float]]: ...
    async def delete_vector(self, record_id: str) -> None: ...
```

### Pattern 3: sqlite-vec / aiosqlite Loading (VERIFIED on Windows 11)

**What:** Load sqlite-vec once per connection at connection-open time. All subsequent queries on that connection can use vec0 virtual tables.

```python
# Source: VERIFIED — sqlite-vec 0.1.9 + aiosqlite 0.22.1 on Windows 11 / Python 3.13
import aiosqlite
import sqlite_vec
import numpy as np
import struct

# --- Connection factory (load extension once per connection) ---
async def open_t1_connection(db_path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    await db.enable_load_extension(True)
    await db.load_extension(sqlite_vec.loadable_path())  # <-- the correct pattern
    await db.enable_load_extension(False)
    # sqlite_vec.load(db) is sqlite3-only — does NOT work with aiosqlite
    return db

# --- Float32 vector serialization ---
def serialize_f32(vec: list[float]) -> bytes:
    """Convert to the compact BLOB format sqlite-vec expects."""
    return np.array(vec, dtype=np.float32).tobytes()
    # Alternative (no numpy dep): struct.pack(f'{len(vec)}f', *vec)

# --- vec0 virtual table DDL ---
async def create_vec_table(db: aiosqlite.Connection, dim: int) -> None:
    await db.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_t1 USING vec0(
            record_id TEXT PRIMARY KEY,
            embedding float[{dim}]
        )
    """)
    await db.commit()

# --- KNN query with scope isolation ---
# CRITICAL: k= is the global pre-filter fetch count.
# In a multi-user index, k must be >> desired results because the
# JOIN filter (user_id) is applied AFTER vec0 returns k global candidates.
# Phase 1 is single-user so k=30 is fine; Phase 4 multi-user needs k_fetch >> k_desired.
async def vector_search(
    db: aiosqlite.Connection,
    query_vec: list[float],
    k: int,
    user_id: str,
    agent_id: str | None = None,
) -> list[tuple[str, float]]:
    q_bytes = serialize_f32(query_vec)
    agent_clause = "AND r.agent_id = :agent_id" if agent_id else ""
    sql = f"""
        SELECT v.record_id, v.distance
        FROM vec_t1 v
        JOIN t1_records r ON r.id = v.record_id
        WHERE v.embedding MATCH :q
          AND v.k = :k
          AND r.user_id = :user_id
          AND r.valid_until IS NULL
          {agent_clause}
        ORDER BY v.distance
    """
    params: dict = {"q": q_bytes, "k": k, "user_id": user_id}
    if agent_id:
        params["agent_id"] = agent_id
    rows = await db.execute_fetchall(sql, params)
    return [(row[0], row[1]) for row in rows]
```

### Pattern 4: APScheduler 3.11.2 — Scheduler Port Implementation

**Note on versioning:** CLAUDE.md lists "apscheduler 4.x" but APScheduler 4.x is still alpha (4.0.0a6, Apr 2025) with a stability warning from the author ("do NOT use in production"). APScheduler 3.11.2 is stable (Dec 2025) and provides everything MNEMA needs. **Recommend: use APScheduler 3.11.2; document and revisit when 4.x reaches stable.** [ASSUMED: 4.x will eventually stabilize with compatible AsyncScheduler API]

```python
# Source: VERIFIED — APScheduler 3.11.2 on Python 3.13 (tested)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from typing import Callable, Any

class InProcessScheduler:
    """Implements the Scheduler Protocol backed by APScheduler AsyncIOScheduler."""

    JOB_ID = "consolidate"

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._job: Any = None

    def schedule(self, fn: Callable[[], None], *, every_seconds: int) -> None:
        self._job = self._scheduler.add_job(
            fn,
            "interval",
            seconds=every_seconds,
            id=self.JOB_ID,
            next_run_time=None,   # don't fire immediately on schedule()
        )

    def trigger_now(self) -> None:
        """Force an immediate firing — used by tests and consolidate(force=True)."""
        job = self._scheduler.get_job(self.JOB_ID)
        if job:
            job.modify(next_run_time=datetime.now())  # VERIFIED: fires within ~100ms

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
```

### Pattern 5: looks_like_durable_claim Heuristic (D-04/D-05)

**What:** A regex-based classifier that runs in microseconds on the hot write path. Error-cost bias is toward recall on safety/fact claims (D-05): false positive = cheap provisional record; false negative = read-after-write hole for the session.

```python
# Source: designed from D-04 decisions + verified against test cases
import re
from typing import Literal

RecordTypeHint = Literal["fact", "preference", "event", "procedure"] | None

# Stative verbs in first-person: describe states/properties, not actions
_FIRST_PERSON_STATIVE = re.compile(
    r"(?i)\bi\s+(?:am|was|have|hate|love|like|prefer|enjoy|need|want|"
    r"eat|drink|avoid|dislike|am\s+allergic|am\s+intolerant|follow|practice|"
    r"believe|think|know|own|always|never|usually|often|batch[-\s]cook)\b"
)
_QUESTION = re.compile(r"\?")
_MODAL_HYPOTHETICAL = re.compile(
    r"(?i)\b(?:would|could|might|may|should\s+i|can\s+i|do\s+you|what\s+if|if\s+i)\b"
)

def looks_like_durable_claim(
    text: str,
    type_hint: RecordTypeHint = None,
    durable: bool = False,
) -> bool:
    """Return True if this turn looks like a durable personal fact/preference.

    Caller override (type_hint or durable=True) is always authoritative (D-04).
    Bias toward recall on safety claims — false positives cost one embedding call,
    false negatives cost a freshness hole (D-05).
    """
    # Caller-supplied override always wins
    if durable or type_hint in ("fact", "preference", "procedure"):
        return True
    # Question suppression — rhetorical or clarifying questions are not facts
    if _QUESTION.search(text):
        return False
    # Hypothetical / modal suppression
    if _MODAL_HYPOTHETICAL.search(text):
        return False
    # First-person stative verb match
    return bool(_FIRST_PERSON_STATIVE.search(text))
```

**Lexicon extension guidance (Claude's Discretion):** The planner should tune this lexicon against the 5-test harness cases. Adding verbs to the stative list only increases recall (safer for D-05 bias). Removing verbs decreases false positives. The regex is the classifier seam — when a trained head is added in a later phase, it replaces this function, not the caller.

### Pattern 6: StubEmbedder — hermetic test embedder

**What:** Deterministic hash-based embedder that produces consistent unit vectors without any API call. Keeps the 5-test harness CI-fast and hermetic.

```python
# Source: designed for EVAL-01 hermetic tests
import hashlib, math

class StubEmbedder:
    """Deterministic embedder for tests. Same text always same vector. No API."""

    def __init__(self, dim: int = 128) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            # Build dim-length vector from repeated digest bytes
            raw = [(digest[i % 32] / 255.0) for i in range(self._dim)]
            # L2-normalize (normalize-at-adapter contract)
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            results.append([x / norm for x in raw])
        return results
```

**Choosing StubEmbedder dim:** Use `dim=128` for the walking skeleton (small, fast). The vec0 table is created with this dim. If a future test switches to a real embedder (1024d), the `embedding_dim` startup assertion catches the mismatch before anything is written.

### Pattern 7: pytest-asyncio 1.4.0 Configuration

```toml
# pyproject.toml — Source: pytest-asyncio 1.4.0 docs (verified version)
[tool.pytest.ini_options]
asyncio_mode = "auto"                        # all async def tests run automatically
asyncio_default_fixture_loop_scope = "function"  # one event loop per test
testpaths = ["tests"]
```

**asyncio_mode = "auto"** is the right choice for MNEMA: eliminates `@pytest.mark.asyncio` boilerplate on every test, and every async fixture is automatically treated as an asyncio fixture.

### Anti-Patterns to Avoid

- **`sqlite_vec.load(db)` with aiosqlite:** Works only on `sqlite3.Connection`. With `aiosqlite`, use `await db.load_extension(sqlite_vec.loadable_path())` instead. [VERIFIED]
- **Loading sqlite-vec on a new connection without the extension:** vec0 virtual table queries fail with `no such module: vec0` on any connection that has not had the extension loaded (extension registration is per-connection, not global). Load extension in the connection factory, not once at startup. [VERIFIED — per basic-memory issue #735]
- **Passing Python lists to vec0 INSERT:** sqlite3 / aiosqlite cannot bind Python `list` objects. Always serialize via `numpy.ndarray.tobytes()` or `struct.pack`. [VERIFIED]
- **Using vec0 `LIMIT` without `k=` in the JOIN pattern:** vec0 requires either `LIMIT N` or `k = N` in the KNN query. Without it: `OperationalError: A LIMIT or 'k = ?' constraint is required`. [VERIFIED]
- **Assuming `k=` filters within user scope:** vec0's `k=N` fetches `N` candidates globally, before the JOIN filter. In a mixed-user index, use `k_fetch = desired_k * safety_multiplier`. Phase 1 is single-user — k=30 is fine. [VERIFIED]
- **APScheduler 4.x alpha:** Do not use in production code. The author's README includes: "provided as a pre-release; may change in a backwards incompatible fashion without any migration pathway." [VERIFIED]
- **Coupling LLM and embedding in one Protocol:** Fatal for Claude (no embedder). Keep `LLMProvider` and `EmbeddingProvider` as completely separate Protocols with separate config axes. [Design constraint from PROJECT.md]
- **Non-defaulted `user_id` at SDK level, defaulted at adapter level:** The `user_id` must be non-defaulted all the way down to the SQL WHERE clause. Any gap (even a keyword-with-default in a helper function) silently allows unscoped reads. [D-03 locked decision]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async SQLite + loadable extensions | Custom thread pool + queue | `aiosqlite` 0.22.1 | It handles the single-thread-per-connection safety correctly; async extension API verified |
| Float32 vector serialization | Custom struct packing utility | `numpy.ndarray.tobytes()` or `struct.pack` | Zero-overhead, buffer-protocol compatible with sqlite-vec |
| In-process scheduling | Custom `asyncio.create_task` loop | `APScheduler` 3.x `AsyncIOScheduler` | Handles trigger deferral, immediate fire, shutdown cleanly |
| Pydantic coercion of SQLite booleans | Manual int→bool cast everywhere | `pydantic.model_validate` with `ConfigDict` | Handles `int → bool`, `str → datetime`, None validation automatically |
| Async Protocol methods | Custom ABC with abstract async methods | `typing.Protocol` with `async def ...` stubs | Structural typing, no inheritance burden, pyright/mypy strict compatible |
| Deterministic unit vectors for tests | Real embedding API call in CI | `StubEmbedder` (hash-based, 128d) | Sub-millisecond, hermetic, no network, CI-safe |

---

## Common Pitfalls

### Pitfall 1: sqlite-vec extension not loaded on every new connection

**What goes wrong:** `OperationalError: no such module: vec0` on any connection that didn't run `load_extension`. Extension registration is per-connection in SQLite.

**Why it happens:** Loading the extension once at startup and assuming it's globally available. SQLAlchemy connection pools, aiosqlite reconnects, and test fixtures that open new connections all miss the extension.

**How to avoid:** Call `enable_load_extension` + `load_extension(sqlite_vec.loadable_path())` in the connection factory, before returning the connection to any consumer. For the `SqliteT1` adapter, do this in `__init__` or a `classmethod open(...)`.

**Warning signs:** Tests pass with a warm connection, fail intermittently with a fresh connection; `no such module: vec0` only in CI.

### Pitfall 2: vec0 k= is a global fetch count, not a user-scoped count

**What goes wrong:** `vector_search(..., k=5, user_id="user_A")` returns 0 results even though user_A has 3 matching records, because there are 5 closer records from other users that fill vec0's global k-buffer before the JOIN filter can see user_A's records.

**Why it happens:** vec0's `k=N` (or `LIMIT N`) controls how many candidates the vector index returns globally, before any JOIN condition is applied.

**How to avoid:** For Phase 1 (single-user), this is not a problem. Document in the adapter for Phase 4: `k_fetch = max(k_desired * 4, 50)` as a minimum safety multiplier, or route user-specific queries to a per-user partition. [VERIFIED by code experiment]

**Warning signs:** Recall returns empty for user with known records when total database size grows; adding users makes recall quality degrade.

### Pitfall 3: aiosqlite vs sqlite3 + asyncio.to_thread for extension loading

**What goes wrong:** Using `asyncio.to_thread(sqlite3.connect, ...)` and then trying to load extensions — the thread that opens the connection is not guaranteed to be the same thread that executes queries, and sqlite3 connections are not thread-safe.

**Why it happens:** D-13 says "wrap sync adapters in `asyncio.to_thread` at the leaf." This is correct for e.g. a DashScope call, but for SQLite with extension loading, aiosqlite is a better fit: it guarantees single-thread-per-connection semantics with a native async API.

**How to avoid:** Use `aiosqlite` for the local T1 adapter. The `asyncio.to_thread` pattern is reserved for adapters with no native async option (e.g., some embedding libraries). [VERIFIED: aiosqlite 0.22.1 has native `enable_load_extension` + `load_extension`]

### Pitfall 4: APScheduler 4.x mistaken for stable

**What goes wrong:** Installing `apscheduler` and getting 3.11.2 but expecting 4.x API (e.g., `AsyncScheduler` class, different `add_job` signatures). Or installing `apscheduler==4.0.0a6` and hitting breaking changes in future alpha iterations.

**Why it happens:** CLAUDE.md says "4.x" but PyPI latest stable is 3.x. APScheduler 4.x is in alpha with an explicit "no migration pathway" warning.

**How to avoid:** Pin `apscheduler>=3.11,<4` until 4.x reaches stable. Implement the Scheduler Protocol against APScheduler 3.x's `AsyncIOScheduler`. The `trigger_now()` method uses `job.modify(next_run_time=datetime.now())`. [VERIFIED]

### Pitfall 5: `protected` implemented as a high salience threshold, not a column

**What goes wrong:** The only thing standing between the peanut allergy and eviction is the LLM-assigned salience score. If the LLM scores it 0.92 instead of 1.0, or a merge averages salience, the record can be evicted — and nothing alerts you.

**Why it happens:** Misreading the build plan's "pin allergies to salience 1.0" as the protection mechanism, rather than reading `protected: bool` as the structural guard that runs *before* any score math.

**How to avoid:** `protected` must be a non-nullable boolean column in `t1_records`, set by deterministic rules (allergy keywords, caller-supplied `type="fact"` + safety content), not by the LLM salience judge. In Phase 1, the decay pass is not yet implemented — but the column must exist so Phase 2/3 can implement "if record.protected: continue" as the first line of the decay loop. [CORE-04 requirement]

### Pitfall 6: Missing `valid_until IS NULL` filter in any recall path

**What goes wrong:** A superseded record (vegetarian preference after switching to pescatarian) appears in recall results because the BM25 or buffer path doesn't apply the live-records filter.

**Why it happens:** The filter is only applied to the dense vector_search path, and the buffer union and eventual BM25 paths skip it.

**How to avoid:** In Phase 1, the buffer contains only the current session's turns (all "live" by definition). The dense path enforces `valid_until IS NULL` via the JOIN filter. Document: every future retrieval path added in Phase 2 MUST enforce this filter at the adapter boundary.

---

## Code Examples

### Complete aiosqlite + sqlite-vec connection setup

```python
# Source: VERIFIED — all commands executed on Windows 11 / Python 3.13 / sqlite-vec 0.1.9 / aiosqlite 0.22.1

import aiosqlite
import sqlite_vec
import numpy as np
import json
from typing import AsyncIterator

def _v32(vec: list[float]) -> bytes:
    """Serialize a float list to float32 bytes for sqlite-vec."""
    return np.array(vec, dtype=np.float32).tobytes()

async def open_t1(db_path: str, dim: int) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    await db.enable_load_extension(True)
    await db.load_extension(sqlite_vec.loadable_path())
    await db.enable_load_extension(False)
    await db.execute("PRAGMA journal_mode=WAL")  # better concurrent read performance
    await db.execute("""
        CREATE TABLE IF NOT EXISTS t1_records (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, session_id TEXT NOT NULL,
            agent_id TEXT, record_type TEXT NOT NULL, content TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '', keywords TEXT NOT NULL DEFAULT '[]',
            embedding_model TEXT, embedding_dim INTEGER, embedding_version TEXT,
            protected INTEGER NOT NULL DEFAULT 0,
            salience REAL NOT NULL DEFAULT 0.5, confidence REAL NOT NULL DEFAULT 0.9,
            provisional INTEGER NOT NULL DEFAULT 1,
            valid_from TEXT NOT NULL, valid_until TEXT, superseded_by TEXT,
            t0_ref TEXT, source_refs TEXT NOT NULL DEFAULT '[]',
            access_count INTEGER NOT NULL DEFAULT 0,
            last_accessed TEXT, created_at TEXT NOT NULL,
            graph_edges TEXT NOT NULL DEFAULT '[]'
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_t1_live_user
        ON t1_records(user_id, agent_id)
        WHERE valid_until IS NULL
    """)
    await db.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_t1 USING vec0(
            record_id TEXT PRIMARY KEY,
            embedding float[{dim}]
        )
    """)
    await db.commit()
    return db
```

### Scope-isolated dense recall

```python
# Source: VERIFIED — returns only user1 records even when user2 records exist
async def dense_recall(
    db: aiosqlite.Connection,
    query_vec: list[float],
    k: int,
    user_id: str,
    agent_id: str | None = None,
) -> list[tuple[str, float]]:
    q_bytes = _v32(query_vec)
    agent_clause = "AND r.agent_id = :agent_id" if agent_id else ""
    sql = f"""
        SELECT v.record_id, v.distance
        FROM vec_t1 v
        JOIN t1_records r ON r.id = v.record_id
        WHERE v.embedding MATCH :q
          AND v.k = :k
          AND r.user_id = :user_id
          AND r.valid_until IS NULL
          {agent_clause}
        ORDER BY v.distance
    """
    params: dict = {"q": q_bytes, "k": k, "user_id": user_id}
    if agent_id:
        params["agent_id"] = agent_id
    rows = await db.execute_fetchall(sql, params)
    return [(r[0], r[1]) for r in rows]
```

### APScheduler trigger_now pattern

```python
# Source: VERIFIED — APScheduler 3.11.2 + asyncio, fires within 100ms
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

class InProcessScheduler:
    JOB_ID = "consolidate"

    def __init__(self) -> None:
        self._s = AsyncIOScheduler()

    def schedule(self, fn: object, *, every_seconds: int) -> None:
        self._s.add_job(fn, "interval", seconds=every_seconds,
                        id=self.JOB_ID, next_run_time=None)

    def trigger_now(self) -> None:
        job = self._s.get_job(self.JOB_ID)
        if job:
            job.modify(next_run_time=datetime.now())

    def start(self) -> None:
        self._s.start()

    def shutdown(self) -> None:
        self._s.shutdown(wait=False)
```

### 5-test harness structure (EVAL-01)

```python
# Source: tests/test_remember_recall.py — maps to ROADMAP Phase 1 success criteria
import pytest
from mnema import MemoryEngine
from mnema.adapters.embedding.stub import StubEmbedder
from mnema.adapters.vector_store.sqlite_t1 import SqliteT1
from mnema.adapters.object_store.local_fs import LocalFS
from mnema.adapters.scheduler.in_process import InProcessScheduler

@pytest.fixture
async def engine(tmp_path):
    embedder = StubEmbedder(dim=128)
    t1 = await SqliteT1.open(":memory:", dim=embedder.dim)
    t0 = LocalFS(base_dir=str(tmp_path / "t0"))
    scheduler = InProcessScheduler()
    scheduler.start()
    eng = MemoryEngine(embedder=embedder, t1=t1, t0=t0, scheduler=scheduler)
    yield eng
    scheduler.shutdown()

# SC-1: remember then recall returns the stored fact, scoped by user_id
async def test_remember_and_recall(engine):
    await engine.remember("I am allergic to peanuts", user_id="u1", session_id="s1")
    results = await engine.recall("food allergies", user_id="u1")
    assert any("peanut" in r.summary.lower() or "peanut" in r.content.lower() for r in results)

# SC-1 scope isolation: user2 cannot see user1's memories
async def test_scope_isolation(engine):
    await engine.remember("I am allergic to peanuts", user_id="u1", session_id="s1")
    results = await engine.recall("peanut", user_id="u2")
    assert len(results) == 0

# SC-2: same-session statement recallable immediately via buffer
async def test_within_session_freshness(engine):
    scope = engine.scope(user_id="u1")
    await scope.remember("I love spicy food", session_id="s1")
    # Recall before any consolidation — buffer must surface it
    results = await scope.recall("spicy")
    assert any("spicy" in r.content.lower() for r in results)

# SC-3: fast write path never blocks on LLM, records have all required columns
async def test_fast_write_schema_columns(engine):
    await engine.remember("I prefer vegan meals", user_id="u1", session_id="s1")
    # Fetch raw record to check columns
    record = await engine._t1.get_latest(user_id="u1")
    assert record is not None
    assert record.embedding_model is not None  # CORE-03
    assert record.embedding_dim is not None
    assert isinstance(record.protected, bool)  # CORE-04
    assert record.valid_until is None           # CORE-05 (new record is live)

# SC-5: expand(id) returns verbatim T0 detail; access_count increments
async def test_expand_and_access_count(engine):
    await engine.remember("I batch-cook on Sundays", user_id="u1", session_id="s1")
    results = await engine.recall("cooking schedule", user_id="u1")
    assert len(results) > 0
    first = results[0]
    assert first.access_count >= 1  # RECALL-07
    if first.t0_ref:
        verbatim = await engine.expand(first.id, user_id="u1")
        assert verbatim is not None  # RECALL-06
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sqlite-vss (obsolete) | sqlite-vec 0.1.x | 2023–2024 | sqlite-vss deprecated; sqlite-vec is the maintained replacement |
| APScheduler 3.x `BackgroundScheduler` | `AsyncIOScheduler` for asyncio apps | v3.6+ | Required for async-first code to avoid thread-event-loop conflicts |
| `typing.Protocol` without `@runtime_checkable` | Standard for static-only contracts | Python 3.8+ | `@runtime_checkable` needed only for `isinstance` checks; D-10 defers it |
| `pydantic v1` model + `orm_mode=True` | Pydantic v2 `from_attributes=True` or `model_validate(dict)` | Pydantic 2.0 (2023) | v1 is end-of-life; v2 is faster and stricter |
| pytest-asyncio strict mode (manual mark) | `asyncio_mode = "auto"` in config | pytest-asyncio 0.21+ | Eliminates per-test `@pytest.mark.asyncio` decorator boilerplate |

**Deprecated/outdated:**
- **sqlite-vss:** Predecessor to sqlite-vec; archived by the author. Use sqlite-vec only.
- **psycopg2:** Legacy sync-only Postgres driver; use psycopg3 (`psycopg[binary,pool]`) when Phase 4 cloud adapters land.
- **APScheduler 4.0.0 alpha:** Not stable; do not use in production. Pin `<4`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | APScheduler 4.x will eventually stabilize with a compatible `AsyncScheduler` API making migration straightforward | Standard Stack, Pattern 4 | If 4.x API diverges dramatically, the Scheduler adapter must be rewritten in Phase 4; low risk since the Scheduler Protocol hides the adapter |
| A2 | StubEmbedder dim=128 will produce distinguishable vectors for the harness test cases without collision | Pattern 6, EVAL-01 | If hash collisions produce near-zero distance for different texts, some tests may be flaky; fix by increasing dim or switching to random-seeded vectors |
| A3 | sentence-transformers `bge-m3` (dim=1024) will install and run on Windows 11 for the real local embedder (Phase 4) | Standard Stack | May require additional torch/CUDA setup; fallback is Voyage API |

---

## Open Questions (RESOLVED)

> All three resolved during planning; the recommendations below are implemented in the Phase 1 plans (01-02, 01-04).

1. **`summary` generation on the fast write path**
   - What we know: the build plan says `summary` is "the packer injects by default" and should be <= ~12 tokens. WRITE-03 forbids LLM calls on the fast path.
   - What's unclear: for Phase 1, should `summary` default to the first 80 chars of `content`, or be a separate field the caller must supply?
   - RESOLVED: In Phase 1, auto-generate summary as `content[:80].strip()` in `WritePath`; the real summarization (LLM on the slow path) lands in Phase 2 consolidation. (Implemented in Plan 01-04.)

2. **Staging queue persistence on the local path**
   - What we know: D-13 allows sync queues wrapped in `asyncio.to_thread`. The staging queue must survive a process restart to avoid dropped turns.
   - What's unclear: Phase 1 scope says "in-memory staging queue" per CONTEXT.md deferred notes. Is losing staging on restart acceptable for Phase 1?
   - RESOLVED: Use an in-memory `asyncio.Queue` for Phase 1 (matches "walking skeleton" mode). Add SQLite-backed staging in Phase 2 when the consolidation pipeline actually drains it. (Implemented in Plan 01-04.)

3. **LocalFS T0 format: one file per session or one file per turn?**
   - What we know: T0 is append-only; `expand(id)` needs to retrieve a specific turn by `t0://session_id/offset_or_index` ref.
   - What's unclear: JSONL (one line per turn, offset = line number) vs separate files (one per turn, simpler).
   - RESOLVED: JSONL per session — append is O(1), read by line-number offset is deterministic, no filesystem overhead for high-turn sessions. (Implemented in Plan 01-02.)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | ✓ | 3.13.13 (target: >=3.12) | — |
| uv | Dependency mgmt | ✓ | 0.9.24 | pip + venv |
| sqlite3 (built-in) | aiosqlite + sqlite-vec | ✓ | 3.50.4 (>=3.41 required) | — |
| enable_load_extension | sqlite-vec | ✓ | verified working on this machine | — |
| sqlite-vec (pip) | T1 vector index | ✓ installed | 0.1.9 (Windows wheel confirmed) | No alternative for Phase 1 |
| aiosqlite | Async SQLite | ✓ installed | 0.22.1 | sqlite3 + asyncio.to_thread |
| pydantic | Schema | ✓ installed | 2.12.5 | — |
| numpy | Vector math | ✓ installed | 2.4.4 | struct.pack (no numpy) |
| apscheduler | Scheduler | ✓ installed | 3.11.2 (use v3, not v4 alpha) | asyncio.create_task loop |
| pytest-asyncio | Test harness | not installed | 1.4.0 available on PyPI | — |
| sentence-transformers | Real local embedder (optional in Phase 1) | not installed | needs install | StubEmbedder for Phase 1 |

**Missing dependencies blocking Phase 1:** None — all required packages available or installable from PyPI with verified Windows wheels.

**Missing dependencies for optional real-embedder path:** sentence-transformers (not needed for Phase 1 StubEmbedder harness).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio 1.4.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` (Wave 0 gap) |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CORE-01 | scope ids on every record + isolation | unit | `pytest tests/test_scope_isolation.py -x` | Wave 0 |
| CORE-02 | typed record v2 schema | unit | `pytest tests/test_schema.py -x` | Wave 0 |
| CORE-03 | embedding provenance columns present | unit | `pytest tests/test_remember_recall.py::test_fast_write_schema_columns -x` | Wave 0 |
| CORE-04 | structural `protected` boolean | unit | `pytest tests/test_schema.py::test_protected_is_bool -x` | Wave 0 |
| CORE-05 | `valid_until IS NULL` hot-path filter | unit | `pytest tests/test_scope_isolation.py::test_live_filter -x` | Wave 0 |
| TIER-01 | T0 append + expand round-trip | unit | `pytest tests/test_remember_recall.py::test_expand_and_access_count -x` | Wave 0 |
| TIER-02 | vec0 KNN over live records | unit | `pytest tests/test_remember_recall.py::test_remember_and_recall -x` | Wave 0 |
| TIER-04 | buffer freshness within-session | unit | `pytest tests/test_remember_recall.py::test_within_session_freshness -x` | Wave 0 |
| WRITE-01/02/03/04 | fast write: T0+buffer+provisional, no LLM block | unit | `pytest tests/test_write_path.py -x` | Wave 0 |
| RECALL-01/02 | dense recall + buffer union | unit | `pytest tests/test_remember_recall.py -x` | Wave 0 |
| RECALL-06 | expand(id) returns verbatim | unit | `pytest tests/test_remember_recall.py::test_expand_and_access_count -x` | Wave 0 |
| RECALL-07 | access_count increments on recall | unit | `pytest tests/test_remember_recall.py::test_expand_and_access_count -x` | Wave 0 |
| PROV-02/PROV-06 | independent embedding axis + dim assert | unit | `pytest tests/test_providers.py::test_dim_assertion -x` | Wave 0 |
| SCHED-01/02 | scheduler trigger_now fires consolidate | unit | `pytest tests/test_scheduler.py -x` | Wave 0 |
| IFACE-01 | importable SDK surface | unit | `pytest tests/test_sdk_interface.py -x` | Wave 0 |
| EVAL-01 | 5-scenario harness green | integration | `pytest tests/test_remember_recall.py -v` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/conftest.py` — shared fixtures: in-memory SqliteT1, StubEmbedder, tmp_path T0, engine
- [ ] `tests/test_remember_recall.py` — 5 capability scenarios (EVAL-01)
- [ ] `tests/test_scope_isolation.py` — CORE-01 user_id enforcement
- [ ] `tests/test_schema.py` — CORE-02/03/04/05 schema column verification
- [ ] `tests/test_write_path.py` — WRITE-01/02/03/04
- [ ] `tests/test_providers.py` — PROV-02/06 dim assertion at startup
- [ ] `tests/test_scheduler.py` — SCHED-01/02 trigger_now
- [ ] `tests/test_sdk_interface.py` — IFACE-01 importable surface
- [ ] `pyproject.toml` — project scaffold with `asyncio_mode = "auto"` config
- [ ] Framework install: `uv add --dev "pytest>=8" "pytest-asyncio>=1.4" ruff pyright`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a (Phase 1: no auth surface; user_id is a client-supplied identity token) |
| V3 Session Management | partial | session_id is write-time provenance only, not a security session token |
| V4 Access Control | yes | user_id non-defaulted kwarg at Protocol level enforces scope isolation |
| V5 Input Validation | yes | Pydantic 2.x validates all record fields on write; no raw string injection |
| V6 Cryptography | no | No cryptographic operations in Phase 1 |

### Known Threat Patterns for sqlite-vec + aiosqlite

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unscoped read (missing user_id predicate) | Info Disclosure | Non-defaulted `user_id` kwarg; centralized WHERE clause builder |
| SQLite injection via record content | Tampering | Parameterized queries everywhere (never f-string SQL with user data) |
| Protected fact evicted via score path | Tampering | `protected` boolean column; Phase 3 decay-loop skips before score math |
| T0 raw turn data exposed via expand(id) | Info Disclosure | Document as sensitive; access-control `expand` in Phase 3 MCP surface |

---

## Sources

### Primary (HIGH confidence — verified by code execution)

- sqlite-vec 0.1.9 on Windows 11 — `pip install sqlite-vec` + full loading test executed locally: `enable_load_extension` works, `sqlite_vec.loadable_path()` works with aiosqlite, `vec0` DDL + KNN + JOIN filter all verified [VERIFIED]
- aiosqlite 0.22.1 — `await db.enable_load_extension(True); await db.load_extension(path)` pattern verified working [VERIFIED]
- APScheduler 3.11.2 — `AsyncIOScheduler` + `job.modify(next_run_time=datetime.now())` pattern for `trigger_now()` verified [VERIFIED]
- Pydantic 2.12.5 — `model_validate(row_dict)` with `ConfigDict(from_attributes=False)`, int→bool coercion verified [VERIFIED]
- numpy 2.4.4 — `np.array(vec, dtype=np.float32).tobytes()` as vec0 parameter verified [VERIFIED]
- pytest-asyncio 1.4.0 — https://pypi.org/project/pytest-asyncio/ — version + Python >=3.10 requirement confirmed
- vec0 `k=` global-not-filtered behavior — experimentally verified: k=3 with 5 user2 records + 1 user1 record returns 0 user1 results [VERIFIED]
- `sqlite_vec.load()` sync-only — confirmed: does not work on aiosqlite connection; `load_extension(loadable_path())` is the async pattern [VERIFIED]

### Secondary (MEDIUM confidence — official docs, confirmed)

- APScheduler 4.x alpha status — https://pypi.org/project/APScheduler/ + README.rst: "do NOT use in production" [CITED: pypi.org/project/APScheduler/]
- sqlite-vec Windows wheel availability — https://pypi.org/project/sqlite-vec/ — "Windows x86-64 wheel available (292.8 kB)" [CITED: pypi.org/project/sqlite-vec/]
- sqlite-vec Python loading docs — https://alexgarcia.xyz/sqlite-vec/python.html [CITED: alexgarcia.xyz/sqlite-vec/python.html]
- pytest-asyncio `asyncio_mode = "auto"` config — https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html [CITED]
- vec0 "no such module" per-connection pitfall — https://github.com/basicmachines-co/basic-memory/issues/735 [CITED]
- Python typing.Protocol with async methods — https://typing.python.org/en/latest/reference/protocols.html [CITED]

### Tertiary (LOW confidence — not independently verified)

- sentence-transformers bge-m3 1024d local inference on Windows — described in CLAUDE.md; not tested locally [ASSUMED]
- APScheduler 4.x future stability timeline — [ASSUMED]

---

## Metadata

**Confidence breakdown:**
- sqlite-vec Windows loading: HIGH — tested on target machine
- aiosqlite extension loading pattern: HIGH — tested on target machine
- APScheduler 3.x trigger_now: HIGH — tested on target machine
- Pydantic row_factory pattern: HIGH — tested on target machine
- vec0 k= global behavior: HIGH — tested on target machine, critical finding
- APScheduler v4 recommendation (use v3): HIGH — author's own warning on PyPI
- looks_like_durable_claim lexicon: MEDIUM — regex patterns correct, final tuning is Claude's Discretion per D-04
- Phase 1 summary generation (first 80 chars): LOW — design decision, no canonical reference

**Research date:** 2026-06-10
**Valid until:** 2026-09-10 (stable stack; re-verify sqlite-vec and pytest-asyncio if >3 months pass)
