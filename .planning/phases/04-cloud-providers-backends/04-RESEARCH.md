# Phase 4: Cloud Providers & Backends - Research

**Researched:** 2026-06-14
**Domain:** Cloud adapter implementations behind existing ports; parametrized conformance suite; Pydantic config factory
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Area 1 — Conformance suite + CI strategy (STORE-06)**
- D4-01: Parametrized pytest conformance suite — one contract per port — runs across available backends.
- D4-02: CI hermeticity: local backends run ALWAYS and are the phase gate. Cloud/Postgres backends are credential/Docker-gated with `pytest.skip`.
- D4-03: "≥2 backends per axis" satisfied in CI where two local-capable backends exist; for axes with one local backend the 2nd is gated.
- D4-04: Real-API tests opt-in via env vars (`MNEMA_TEST_DASHSCOPE=1`, `MNEMA_TEST_ANTHROPIC=1`, `MNEMA_TEST_VOYAGE=1`, `MNEMA_TEST_OSS=1`, `MNEMA_TEST_PG=1`).

**Area 2 — Cloud LLM/embedding adapters (PROV-03/04/05/06)**
- D4-05: Direct official SDKs — `anthropic`, `dashscope`, `voyageai` — behind existing Protocols. LiteLLM NOT used.
- D4-06: Claude-compatible embedder = Voyage `voyage-3.5`. Independent embedding axis confirmed.
- D4-07 (PROV-06): Embeddings L2-normalized at the adapter.
- D4-08: Sync SDKs wrapped in `asyncio.to_thread`. Retry/timeout in adapters; conformance uses mock transport.

**Area 3 — Postgres+pgvector backend (STORE-02)**
- D4-09: Postgres+pgvector via psycopg3 async; HNSW + partial index `WHERE valid_until IS NULL`; pin pgvector ≥0.8.2.
- D4-10: testcontainers-pgvector when Docker available; skip cleanly otherwise.
- D4-11: Ship adapter + conformance; gate live run.

**Area 4 — Config factory + reindex + cron (STORE-04/05, PROV-07, SCHED-03)**
- D4-12: Pydantic config model + `build_engine(config)` factory wiring all 6 axes.
- D4-13: Two documented configs: fully-local (always-on) and Qwen+Alibaba (credential-gated).
- D4-14 (PROV-07): Embedder/dim switch triggers explicit reindex/migration path.
- D4-15 (SCHED-03): Generic cron-string adapter behind `Scheduler` Protocol alongside InProcessScheduler.

**Carried-forward locked decisions:** D-07/D-08/D-10 segregated Protocols; D-11 async; D-13 sync-SDK containment via `asyncio.to_thread`; independent LLM/embedding axes; never hard-delete; protected/CONS-08 guarantees intact.

### Claude's Discretion
- Retry/timeout strategy inside cloud adapters (3 retries, exponential backoff is standard).
- Exact cron adapter implementation: APScheduler CronTrigger vs croniter parsing + asyncio.
- Error type hierarchy for adapter failures (custom `MnemaAdapterError` vs passthrough).
- Mock transport design for conformance suite hermetic runs.
- PostgresT1 DDL details (column types, index parameters).

### Deferred Ideas (OUT OF SCOPE)
- Hybrid retrieval (BM25 + graph + RRF) — HYBRID-01/02/03.
- Extra providers OpenAI / Ollama (PROV-08).
- Nutrition-coach demo + before/after eval baseline (Phase 5).
- HTTP/SSE MCP transport.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROV-03 | Qwen (DashScope) LLM and embedding adapters ship and pass the conformance suite | dashscope 1.25.21 verified; API shapes documented below |
| PROV-04 | Anthropic (Claude) LLM adapter ships and passes the conformance suite | anthropic 0.109.1 verified; AsyncAnthropic messages.create pattern documented |
| PROV-05 | A Claude-compatible embedder ships (Voyage and/or local) | voyageai 0.4.0 verified; Client.embed() shape documented; AsyncClient available |
| PROV-07 | Switching embedders triggers a reindex/migration path | Migration pattern: re-embed live records loop + schema recreation |
| STORE-01 | Object store (T0) is swappable — Alibaba OSS and local-FS adapters ship | boto3 1.43.x S3-compat client; endpoint_url for OSS; LocalFS already exists |
| STORE-02 | Vector store (T1) is swappable — Postgres+pgvector and sqlite-vec adapters ship | psycopg3 async + pgvector-python 0.4.2; DDL and query patterns documented |
| STORE-03 | Canonical vault (T2) is a git-versioned markdown adapter | LocalFSVault already satisfies STORE-03 — no git-commit step needed |
| STORE-04 | Config-keyed factory wires provider/backend for each axis from configuration | Pydantic v2 discriminated union pattern; `build_engine(config)` factory |
| STORE-05 | Documented default config (Qwen + Alibaba) and a fully-local config both run end-to-end | Two MnemaConfig instances documented; gating pattern researched |
| STORE-06 | Every adapter passes a shared conformance suite on ≥2 backends per axis | Parametrized pytest fixture pattern documented; skip-if-unavailable markers |
| SCHED-03 | A generic cron adapter ships | APScheduler CronTrigger (3.x) behind Scheduler Protocol; cron-string parsing |
</phase_requirements>

---

## Summary

Phase 4 wires six real cloud/storage adapters behind the six ports established in Phases 1-3. The existing `SqliteT1`, `LocalFS`, `LocalFSVault`, `InProcessScheduler`, `StubLLM`, and `StubEmbedder` are complete and stay untouched — they become the hermetic CI anchors for the conformance suite. The cloud adapters are new leaf-level implementations that must match the Protocol contracts exactly.

The linchpin is the parametrized conformance suite (`tests/conformance/`): it runs the same contract tests against every backend registered for each axis, with local backends always-on and cloud/Postgres backends gated by env vars and Docker. The safety invariants (protected record survives every decay pass, eviction is recoverable, scope isolation) are asserted per-backend rather than per-adapter.

The config factory (`src/mnema/config.py`) is a Pydantic v2 model with a `build_engine(config)` function. Two preset configs exercise the two complete stacks: fully-local (sqlite-vec + LocalFS + LocalFSVault + InProcessScheduler + StubLLM + StubEmbedder) and Qwen+Alibaba (Postgres + OSS + DashScope + Voyage/StubEmbedder + CronScheduler). The dim assertion in `MemoryEngine.__init__` is the runtime backstop for PROV-07; the reindex path is a migration entrypoint that re-embeds all live records when the embedder changes.

**Primary recommendation:** Implement in this order — (1) `cloud` optional extra in pyproject.toml, (2) conformance suite skeleton with local fixtures passing, (3) cloud adapters one-by-one (Anthropic LLM, DashScope LLM+Embedder, Voyage Embedder, PostgresT1, OSSL S3), (4) CronScheduler adapter, (5) config factory + reindex path.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| LLM text completion (extraction/judging) | API / Backend (adapter layer) | — | LLM calls are I/O-bound; all logic stays in ConsolidationPipeline; adapter is a pure I/O leaf |
| Text embedding | API / Backend (adapter layer) | — | EmbeddingProvider is an independent axis; normalization happens inside the adapter |
| T1 vector store + record store | Database / Storage | — | Postgres+pgvector owns both roles (RecordStore + VectorIndex) behind one connection |
| T0 object store (turns + cold archive) | Database / Storage | — | OSS/S3 via boto3; LocalFS already exists |
| T2 vault (git-versioned markdown) | Database / Storage | — | LocalFSVault already satisfies; no git-commit step required for STORE-03 |
| Scheduler (cron/interval) | API / Backend (adapter layer) | — | APScheduler 3.x CronTrigger behind existing Scheduler Protocol |
| Config factory + reindex | API / Backend (config layer) | — | `build_engine(config)` lives in `src/mnema/config.py`; touches no Protocol definitions |
| Conformance suite | Testing infrastructure | — | `tests/conformance/` parametrized fixtures; not shipped as part of the engine |

---

## Standard Stack

### Core (cloud extra)

| Library | Version (PyPI-verified) | Purpose | Why Standard |
|---------|------------------------|---------|--------------|
| `anthropic` | 0.109.1 | Anthropic Claude LLM adapter | Official SDK; `AsyncAnthropic` is the async client; `messages.create()` is the sole entrypoint |
| `dashscope` | 1.25.21 | Qwen LLM + Qwen embedder | Official Alibaba Model Studio SDK; covers both default axes with one import |
| `voyageai` | 0.4.0 | Voyage embedder (Claude-compatible) | Anthropic's officially recommended embedding partner; `Client.embed()` + `AsyncClient` |
| `psycopg[binary,pool]` | 3.3.4 | Async Postgres driver | psycopg3 async, binary protocol, connection pool — the correct modern driver |
| `pgvector` (Python) | 0.4.2 | Postgres ↔ Python vector adapter | `pgvector.psycopg.register_vector` / `register_vector_async`; handles `numpy` ↔ PG vector |
| `boto3` | 1.43.29 | S3-compatible object store | One client covers Alibaba OSS / AWS S3 / MinIO via `endpoint_url`; no OSS-specific SDK |

### Dev/Test (dev extra)

| Library | Version (PyPI-verified) | Purpose | When to Use |
|---------|------------------------|---------|-------------|
| `testcontainers[postgres]` | 4.14.2 | Ephemeral Postgres+pgvector in tests | `PostgresContainer("ankane/pgvector")` spun per test session; skip when Docker absent |

### Already in pyproject.toml (no change needed)

| Library | Current Pin | Note |
|---------|-------------|------|
| `apscheduler` | `>=3.11,<4` | CronScheduler uses `CronTrigger` from APScheduler 3.x |
| `pydantic` | `>=2.12` | Config model + factory |
| `numpy` | `>=2.4` | L2 normalization in adapters |

**Version verification:** All versions above confirmed against PyPI on 2026-06-14 via `pip index versions`.

**Installation (pyproject.toml additions):**

```toml
[project.optional-dependencies]
cloud = [
    "anthropic>=0.109.1,<0.110",
    "dashscope>=1.25.21,<2",
    "voyageai>=0.4.0,<0.5",
    "psycopg[binary,pool]>=3.3,<4",
    "pgvector>=0.4.2,<0.5",
    "boto3>=1.43,<2",
]
dev = [
    "pytest>=8",
    "pytest-asyncio>=1.4",
    "ruff",
    "pyright",
    "hypothesis>=6.155",
    "testcontainers[postgres]>=4.14,<5",
]
```

> **Python 3.14 cap risk:** The project currently resolves to Python 3.13.14 (uv venv confirmed). `pyproject.toml` has no upper cap on Python. All cloud packages above have verified wheels for 3.13.x. `sqlite-vec` 0.1.9 is the risk library on Windows (loadable extension); the cloud packages are pure Python or have broad wheel support. No action required for Phase 4 but keep the memory note about the 3.14 cap deviation.

---

## Architecture Patterns

### System Architecture Diagram

```
                         build_engine(MnemaConfig)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              LLMProvider    EmbeddingProvider   (4 more axes)
                    │               │
          ┌─────────┴─────────┐     ├── QwenEmbedder (dashscope)
          ▼                   ▼     └── VoyageEmbedder (voyageai)
  AnthropicLLM          QwenLLM
  (AsyncAnthropic)       (dashscope.TextEmbedding)
          │                   │          via asyncio.to_thread
          │  asyncio.to_thread│
          └─────────┬─────────┘
                    ▼
            LLMProvider Protocol
            (complete() → str)

  EmbeddingProvider → embed() → L2-normalize → list[list[float]]

  RecordStore+VectorIndex:
  ┌───────────────────────┐     ┌──────────────────────────────┐
  │      SqliteT1         │     │       PostgresT1             │
  │  (aiosqlite+sqlite-vec│     │  (psycopg3 async +           │
  │   already shipping)   │     │   pgvector HNSW partial idx) │
  └───────────────────────┘     └──────────────────────────────┘
         ↑ always-on CI                ↑ gated: MNEMA_TEST_PG=1
                                         or testcontainers Docker

  ObjectStorePort:
  ┌──────────────┐     ┌────────────────────────────────────┐
  │   LocalFS    │     │          OSSS3Store                 │
  │  (exists)    │     │  (boto3 s3 client, endpoint_url)   │
  └──────────────┘     └────────────────────────────────────┘
         ↑ always-on CI          ↑ gated: MNEMA_TEST_OSS=1

  Conformance suite (tests/conformance/):
  Backend fixtures yield adapter instances.
  Each port has one contract test module.
  Parametrize over [local_backend, cloud_backend].
  pytest.skip when cloud backend unavailable.
  Safety invariants asserted on every non-skipped backend.
```

### Recommended Project Structure

```
src/mnema/
├── adapters/
│   ├── llm/
│   │   ├── stub.py          # exists
│   │   ├── anthropic.py     # NEW: AnthropicLLM
│   │   └── qwen.py          # NEW: QwenLLM
│   ├── embedding/
│   │   ├── stub.py          # exists
│   │   ├── voyage.py        # NEW: VoyageEmbedder
│   │   └── qwen.py          # NEW: QwenEmbedder
│   ├── vector_store/
│   │   ├── sqlite_t1.py     # exists
│   │   └── postgres_t1.py   # NEW: PostgresT1
│   ├── object_store/
│   │   ├── local_fs.py      # exists
│   │   └── oss_s3.py        # NEW: OSSS3Store
│   ├── vault/
│   │   └── local_fs_vault.py  # exists — satisfies STORE-03
│   └── scheduler/
│       ├── in_process.py    # exists
│       └── cron.py          # NEW: CronScheduler
├── config.py                # NEW: MnemaConfig + build_engine()
└── migrate.py               # NEW: reindex_all() for PROV-07

tests/
├── conformance/
│   ├── conftest.py          # NEW: backend fixture registry
│   ├── test_llm_contract.py          # NEW
│   ├── test_embedding_contract.py    # NEW
│   ├── test_record_store_contract.py # NEW
│   ├── test_vector_index_contract.py # NEW
│   ├── test_object_store_contract.py # NEW
│   ├── test_vault_contract.py        # NEW
│   └── test_scheduler_contract.py   # NEW
└── ... (existing tests untouched)
```

---

## SDK API Shapes

### Pattern 1: Anthropic LLM Adapter

**What:** `AsyncAnthropic.messages.create()` wrapped in `asyncio.to_thread` (sync SDK) or called natively with `AsyncAnthropic`.
**When to use:** `LLMProvider.complete(prompt, *, model=None)` calls from ConsolidationPipeline.

```python
# Source: Context7 /anthropics/anthropic-sdk-python
# AnthropicLLM — src/mnema/adapters/llm/anthropic.py

import asyncio
from anthropic import Anthropic  # sync client (D-13 pattern)

class AnthropicLLM:
    def __init__(self, api_key: str, default_model: str = "claude-haiku-4-5") -> None:
        self._client = Anthropic(api_key=api_key)
        self._default_model = default_model

    @property
    def model(self) -> str:
        return self._default_model

    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        m = model or self._default_model
        def _call() -> str:
            resp = self._client.messages.create(
                model=m,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        return await asyncio.to_thread(_call)
```

> **Note:** `AsyncAnthropic` is also available in the SDK and avoids the `to_thread` overhead. Either works; `asyncio.to_thread` is the locked D-13 pattern for sync SDKs. Use `AsyncAnthropic` if the sync-client approach causes test-event-loop issues under pytest-asyncio.

### Pattern 2: DashScope Qwen LLM Adapter

**What:** `dashscope.Generation.call()` (sync) wrapped in `asyncio.to_thread`.
**When to use:** `LLMProvider.complete()` with `qwen-flash` (consolidation) or `qwen-plus` (reasoning).

```python
# Source: [ASSUMED] dashscope Python SDK — verify call shape at install time
# dashscope.Generation.call() is the standard text completion entry
import asyncio
import dashscope

class QwenLLM:
    def __init__(self, api_key: str, default_model: str = "qwen-flash") -> None:
        dashscope.api_key = api_key
        self._default_model = default_model

    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        m = model or self._default_model
        def _call() -> str:
            resp = dashscope.Generation.call(
                model=m,
                messages=[{"role": "user", "content": prompt}],
                result_format="message",
            )
            return resp.output.choices[0].message.content
        return await asyncio.to_thread(_call)
```

> **Pitfall:** DashScope SDK is a sync library. Always use `asyncio.to_thread`. Import `dashscope` lazily inside the adapter module (not at `src/mnema/__init__`). [VERIFIED: PyPI dashscope 1.25.21]

### Pattern 3: Voyage Embedder

**What:** `voyageai.Client.embed(texts, model=..., output_dimension=...).embeddings` + L2-normalize.
**When to use:** `EmbeddingProvider.embed(texts) -> list[list[float]]`.

```python
# Source: Context7 /websites/voyageai + PyPI voyageai 0.4.0
import asyncio
import math
import voyageai

class VoyageEmbedder:
    def __init__(
        self,
        api_key: str,
        model: str = "voyage-3.5",
        output_dimension: int = 1024,
    ) -> None:
        self._client = voyageai.Client(api_key=api_key)
        self._model = model
        self._output_dimension = output_dimension

    @property
    def dim(self) -> int:
        return self._output_dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        def _call() -> list[list[float]]:
            result = self._client.embed(
                texts,
                model=self._model,
                output_dimension=self._output_dimension,
            )
            return result.embeddings
        raw = await asyncio.to_thread(_call)
        return [_l2_normalize(v) for v in raw]

def _l2_normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]
```

> **Note:** `voyageai.AsyncClient` exists in 0.4.0 and avoids `to_thread`. Use it if sync threading causes issues. The normalization step is always required per the EmbeddingProvider Protocol contract.

> **output_dimension:** Voyage `voyage-3.5` supports 256, 512, 1024, 2048. Fix at 1024 for the default config. The value must match `PostgresT1` column width at creation time — the startup dim assertion in `MemoryEngine.__init__` is the backstop.

### Pattern 4: DashScope Qwen Embedder

**What:** `dashscope.TextEmbedding.call()` (sync) wrapped in `asyncio.to_thread`.

```python
# Source: [ASSUMED] dashscope Python SDK — text-embedding-v4 model
import asyncio
import math
import dashscope
from dashscope import TextEmbedding

class QwenEmbedder:
    def __init__(self, api_key: str, output_dimension: int = 1024) -> None:
        dashscope.api_key = api_key
        self._dim = output_dimension

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        def _call() -> list[list[float]]:
            resp = TextEmbedding.call(
                model=TextEmbedding.Models.text_embedding_v4,
                input=texts,
                dimension=self._dim,
            )
            return [item["embedding"] for item in resp.output["embeddings"]]
        raw = await asyncio.to_thread(_call)
        return [_l2_normalize(v) for v in raw]
```

> **DashScope embedding model name:** `text-embedding-v4` (Qwen3-Embedding). Supports Matryoshka dimensions 64–2048; 1024 is the default. [ASSUMED: exact call shape — verify against dashscope docs at install time. The model constant may be `TextEmbedding.Models.text_embedding_v4` or a string literal `"text-embedding-v4"`.]

### Pattern 5: PostgresT1 (RecordStore + VectorIndex)

**What:** `psycopg3 AsyncConnection` + `pgvector.psycopg.register_vector_async` + HNSW partial index.

```python
# Source: Context7 /websites/psycopg_psycopg3 + /pgvector/pgvector-python + /pgvector/pgvector
import psycopg
from pgvector.psycopg import register_vector_async
import numpy as np

class PostgresT1:
    """T1 working-memory adapter over Postgres + pgvector.

    Satisfies RecordStore + VectorIndex Protocols by structural typing.
    """

    def __init__(self, conn: psycopg.AsyncConnection, dim: int) -> None:
        self._conn = conn
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @classmethod
    async def open(cls, dsn: str, dim: int) -> "PostgresT1":
        conn = await psycopg.AsyncConnection.connect(dsn, autocommit=False)
        await register_vector_async(conn)          # pgvector-python ≥0.4.x
        await cls._create_schema(conn, dim)
        return cls(conn, dim)

    @staticmethod
    async def _create_schema(conn: psycopg.AsyncConnection, dim: int) -> None:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS t1_records (
                id              TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                session_id      TEXT NOT NULL,
                agent_id        TEXT,
                record_type     TEXT NOT NULL,
                content         TEXT NOT NULL,
                summary         TEXT NOT NULL DEFAULT '',
                keywords        JSONB NOT NULL DEFAULT '[]',
                embedding_model TEXT,
                embedding_dim   INTEGER,
                embedding_version TEXT,
                protected       BOOLEAN NOT NULL DEFAULT FALSE,
                salience        FLOAT NOT NULL DEFAULT 0.5,
                confidence      FLOAT NOT NULL DEFAULT 0.9,
                provisional     BOOLEAN NOT NULL DEFAULT TRUE,
                valid_from      TIMESTAMPTZ NOT NULL,
                valid_until     TIMESTAMPTZ,
                superseded_by   TEXT,
                t0_ref          TEXT,
                source_refs     JSONB NOT NULL DEFAULT '[]',
                access_count    INTEGER NOT NULL DEFAULT 0,
                last_accessed   TIMESTAMPTZ,
                created_at      TIMESTAMPTZ NOT NULL,
                graph_edges     JSONB NOT NULL DEFAULT '[]'
            )
        """)
        # Partial index — only live records on the hot path (CORE-05)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_t1_live_user
                ON t1_records(user_id, agent_id)
                WHERE valid_until IS NULL
        """)
        # Vector column — must match dim at creation time
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS t1_vectors (
                record_id TEXT PRIMARY KEY REFERENCES t1_records(id) ON DELETE CASCADE,
                embedding vector({dim})
            )
        """)
        # HNSW index + partial-index simulation via WHERE join
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_t1_vectors_hnsw
                ON t1_vectors USING hnsw (embedding vector_l2_ops)
        """)
        await conn.commit()
```

**Vector search with partial-index filter:**

```sql
-- Source: Context7 /pgvector/pgvector (HNSW iterative scan docs)
-- Enable iterative scan to handle valid_until IS NULL post-filter
SET hnsw.iterative_scan = 'strict_order';
SET hnsw.ef_search = 100;

SELECT v.record_id, v.embedding <-> %s AS distance
FROM t1_vectors v
JOIN t1_records r ON r.id = v.record_id
WHERE r.user_id = %s
  AND r.valid_until IS NULL
  AND (%s IS NULL OR r.agent_id = %s)
ORDER BY distance
LIMIT %s;
```

> **Critical:** Use `SET hnsw.iterative_scan = 'strict_order'` at session level before KNN queries. Without it, the `valid_until IS NULL` post-filter can reduce k results below the requested count — this is the same issue as sqlite-vec's k= global pre-filter pitfall, but solved differently in pgvector (iterative scan rather than k overfetch). [VERIFIED: Context7 /pgvector/pgvector configuration docs]

> **Separate vectors table vs embedding column:** Two approaches exist — (a) `vector` column in `t1_records` or (b) separate `t1_vectors` table with FK. The separate-table approach mirrors the SqliteT1 design (vec_t1 virtual table) and makes the `delete_vector` / `upsert_vector` Protocol methods map cleanly to `DELETE/INSERT on t1_vectors`. It also avoids a NULL embedding column for non-vector records. [ASSUMED: planner may choose embedded column if simpler; either satisfies the Protocol]

### Pattern 6: OSSS3Store (ObjectStorePort)

**What:** boto3 S3 client with `endpoint_url` for Alibaba OSS compatibility.

```python
# Source: Context7 /boto/boto3 (S3 client endpoint_url pattern)
import asyncio
import json
import boto3

class OSSS3Store:
    """T0 object store backed by S3-compatible storage (OSS/S3/MinIO).

    Satisfies ObjectStorePort Protocol by structural typing.
    endpoint_url must be set for non-AWS providers (OSS: https://oss-<region>.aliyuncs.com).
    """

    def __init__(
        self,
        bucket: str,
        *,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        endpoint_url: str | None = None,
        region_name: str = "us-east-1",
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            service_name="s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            endpoint_url=endpoint_url,
            region_name=region_name,
        )

    async def append(self, session_id: str, turn: "Turn") -> str:
        # ... list existing objects, compute offset, put_object ...
        def _put(key: str, body: bytes) -> None:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=body)
        ...
```

> **OSS endpoint URL format:** `https://oss-<region>.aliyuncs.com` (path-style) or `https://<bucket>.oss-<region>.aliyuncs.com` (virtual-hosted). Use path-style with `s3={'addressing_style': 'path'}` in boto3 Config for OSS compatibility. Region must be an OSS region code (e.g. `oss-cn-hangzhou`).

> **Append semantics over S3:** S3/OSS is not append-native. Implement append by (a) reading the current object, appending, re-uploading (simple but racey), or (b) using object key = `{session_id}/{offset}.json` (each turn is one object, no read-modify-write). Option (b) maps cleanly to the `t0://session_id/offset` ref format and is idempotent. [ASSUMED: planner picks the strategy; option (b) is recommended]

### Pattern 7: CronScheduler Adapter

**What:** APScheduler 3.x `CronTrigger` behind the `Scheduler` Protocol.

```python
# Source: APScheduler 3.x docs (already a project dependency)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

class CronScheduler:
    """Cron-string scheduler backed by APScheduler 3.x CronTrigger.

    Satisfies Scheduler Protocol by structural typing (SCHED-03).
    Accepts a standard cron expression: "*/30 * * * *"
    """

    def __init__(self, cron_expression: str) -> None:
        self._cron = cron_expression
        self._scheduler = AsyncIOScheduler()
        self._fn: object = None

    async def schedule(self, fn: object, *, every_seconds: int = 0) -> None:
        # every_seconds ignored in CronScheduler; cron_expression governs timing
        self._fn = fn
        trigger = CronTrigger.from_crontab(self._cron)
        self._scheduler.add_job(fn, trigger, id="consolidate", next_run_time=None)

    async def trigger_now(self) -> None:
        from datetime import datetime
        job = self._scheduler.get_job("consolidate")
        if job is not None:
            job.modify(next_run_time=datetime.now())

    async def start(self) -> None:
        self._scheduler.start()

    async def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
```

> `CronTrigger.from_crontab("*/30 * * * *")` parses standard 5-field cron expressions. APScheduler 3.x is pinned `<4` in pyproject.toml so this is safe. [VERIFIED: APScheduler 3.11.2 in venv, CronTrigger.from_crontab available in 3.x]

### Pattern 8: Config Factory

**What:** Pydantic v2 discriminated union config + `build_engine(config) -> MemoryEngine`.

```python
# Source: Pydantic v2 discriminated union pattern
from pydantic import BaseModel
from typing import Literal

class LocalConfig(BaseModel):
    llm: Literal["stub"] = "stub"
    embedder: Literal["stub"] = "stub"
    vector_store: Literal["sqlite"] = "sqlite"
    object_store: Literal["local_fs"] = "local_fs"
    vault: Literal["local_fs"] = "local_fs"
    scheduler: Literal["in_process"] = "in_process"
    sqlite_path: str = ":memory:"
    local_fs_path: str = "/tmp/mnema_t0"
    vault_path: str = "/tmp/mnema_vault"
    embedder_dim: int = 128

class QwenAlibabaConfig(BaseModel):
    llm: Literal["qwen"] = "qwen"
    embedder: Literal["voyage"] = "voyage"
    vector_store: Literal["postgres"] = "postgres"
    object_store: Literal["oss_s3"] = "oss_s3"
    vault: Literal["local_fs"] = "local_fs"
    scheduler: Literal["cron"] = "cron"
    qwen_api_key: str
    voyage_api_key: str
    postgres_dsn: str
    oss_bucket: str
    oss_access_key_id: str
    oss_secret_access_key: str
    oss_endpoint_url: str
    oss_region: str = "oss-cn-hangzhou"
    cron_expression: str = "*/30 * * * *"
    embedder_dim: int = 1024
    vault_path: str = "/tmp/mnema_vault"

MnemaConfig = LocalConfig | QwenAlibabaConfig

def build_engine(config: MnemaConfig) -> "MemoryEngine":
    """Wire all 6 adapter axes from configuration and return MemoryEngine."""
    ...  # dispatch on config type to instantiate adapters
```

### Pattern 9: Reindex Path (PROV-07)

**What:** When `embedder_dim` changes, re-embed all live records and recreate the vector column.

```python
# Source: [ASSUMED] — standard re-embedding pattern
async def reindex_all(
    t1: "RecordStore & VectorIndex",
    embedder: "EmbeddingProvider",
    user_id: str,
) -> int:
    """Re-embed all live records for user_id with the current embedder.

    Called when switching embedder/dim. The caller must have already:
    1. Recreated the vector column/table at the new dim.
    2. Deleted all existing vectors for the user.
    """
    count = 0
    async for record in t1.live_records(user_id):
        text = record.summary or record.content
        [vec] = await embedder.embed([text])
        await t1.upsert_vector(record.id, vec)
        count += 1
    return count
```

> **Migration entrypoint:** Expose `reindex_all` in `src/mnema/migrate.py`. The startup dim assertion in `MemoryEngine.__init__` (`if embedder.dim != t1._dim`) is the backstop that refuses a silent flip. The migration path must be called before constructing `MemoryEngine` with the new config. [ASSUMED: exact CLI/API surface is planner's discretion]

### Pattern 10: Conformance Suite Structure

**What:** Parametrized pytest fixtures yielding backend instances per axis.

```python
# Source: pytest parametrize pattern (well-established)
# tests/conformance/conftest.py

import os
import pytest
from mnema.adapters.embedding.stub import StubEmbedder

def _pg_available() -> bool:
    return bool(os.environ.get("MNEMA_TEST_PG"))

def _docker_available() -> bool:
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        return False

@pytest.fixture(
    params=["stub", pytest.param("postgres", marks=pytest.mark.skipif(
        not (_pg_available() or _docker_available()),
        reason="Postgres not available: set MNEMA_TEST_PG=1 or provide Docker"
    ))]
)
async def t1_backend(request, tmp_path):
    if request.param == "stub":
        from mnema.adapters.vector_store.sqlite_t1 import SqliteT1
        yield await SqliteT1.open(":memory:", dim=128)
    elif request.param == "postgres":
        # testcontainers path or DSN from env
        ...
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vector type registration (PG) | Custom COPY/binary protocol | `pgvector.psycopg.register_vector_async` | Handles `vector` ↔ numpy array codec; brittle otherwise |
| S3-compatible object storage | Direct HTTP to OSS API | boto3 `s3` client with `endpoint_url` | OSS exposes S3-compatible endpoint; one client covers OSS/S3/MinIO |
| Cron parsing | Hand-rolled cron string parser | `APScheduler.CronTrigger.from_crontab()` | APScheduler 3.x already a dependency; CronTrigger handles all edge cases |
| Retry/backoff on API calls | Manual sleep loops | SDK's own retry or `tenacity` | anthropic SDK has built-in retry; dashscope/voyageai need explicit `tenacity` |
| HNSW filtered KNN | Post-filter in Python after large KNN | pgvector `hnsw.iterative_scan = 'strict_order'` | Iterative scan ensures k results even with dense filter; Python post-filter truncates |
| Dim assertion at startup | Per-operation dim checks | Existing `MemoryEngine.__init__` assertion | Already implemented; don't duplicate |
| L2 normalization | Per-call normalization in multiple places | Single `_l2_normalize()` helper in each adapter | Normalization is the adapter's contract; callers assume it |

**Key insight:** The pgvector iterative scan setting is the critical difference from sqlite-vec. With sqlite-vec, you overfetch (`k * 4`) and discard; with pgvector, you enable `hnsw.iterative_scan = 'strict_order'` at session level and get exactly k results regardless of how many the filter removes.

---

## Common Pitfalls

### Pitfall 1: pgvector register_vector must be called AFTER connection, BEFORE queries

**What goes wrong:** `psycopg.AsyncConnection.connect()` does not automatically register the `vector` type codec. Any query returning a `vector` column returns raw bytes without registration.
**Why it happens:** pgvector is a Postgres extension, not a built-in type; psycopg3 doesn't auto-register custom types.
**How to avoid:** Call `await register_vector_async(conn)` (from `pgvector.psycopg`) immediately after `await psycopg.AsyncConnection.connect(...)`.
**Warning signs:** `AttributeError: 'memoryview'` or `TypeError` when fetching vector columns.

[VERIFIED: Context7 /pgvector/pgvector-python — `register_vector_async` for async psycopg3]

### Pitfall 2: HNSW filtered queries return fewer than k results without iterative_scan

**What goes wrong:** `SELECT ... ORDER BY embedding <-> %s LIMIT k` over HNSW with a post-filter (`WHERE valid_until IS NULL`) returns fewer than k rows, silently truncating recall.
**Why it happens:** HNSW single-pass scan fetches `ef_search` candidates then post-filters; if the filter removes many candidates, fewer than k survive.
**How to avoid:** `SET hnsw.iterative_scan = 'strict_order'` at session level (or connection level). Optionally increase `hnsw.ef_search` to 100+ for better recall.
**Warning signs:** KNN tests returning fewer results than requested when live records >> k; non-deterministic result counts.

[VERIFIED: Context7 /pgvector/pgvector configuration docs — `hnsw.iterative_scan`]

### Pitfall 3: voyageai.Client is sync; voyageai.AsyncClient is preferred in async contexts

**What goes wrong:** Using `voyageai.Client.embed()` inside an async adapter without `asyncio.to_thread` blocks the event loop.
**Why it happens:** The sync client makes blocking HTTP calls.
**How to avoid:** Use `voyageai.AsyncClient` (available in 0.4.0) directly with `await`, or wrap `voyageai.Client.embed()` in `asyncio.to_thread` per D-13.
**Warning signs:** Event loop stalls during embedding; pytest-asyncio timeouts.

[VERIFIED: PyPI voyageai 0.4.0 — AsyncClient present in 0.4.x]

### Pitfall 4: DashScope SDK sets api_key globally (module-level state)

**What goes wrong:** `dashscope.api_key = ...` sets a module-level global. In a multi-adapter environment, two DashScope adapters with different API keys interfere.
**Why it happens:** DashScope SDK uses global state rather than client instances.
**How to avoid:** Either use a single DashScope adapter (QwenLLM + QwenEmbedder share the same key), or pass `api_key=` directly in each call if the SDK supports it. For MNEMA v1 (single provider config), this is not a problem.
**Warning signs:** Unexpected auth failures when switching API keys mid-session.

[ASSUMED — verify at dashscope install time: some SDK versions support per-call api_key]

### Pitfall 5: testcontainers PostgresContainer default image lacks pgvector

**What goes wrong:** `PostgresContainer("postgres:16")` starts plain Postgres without the `vector` extension. `CREATE EXTENSION IF NOT EXISTS vector` fails.
**Why it happens:** The official Postgres Docker image does not bundle pgvector.
**How to avoid:** Use `PostgresContainer("ankane/pgvector")` (the standard pgvector Docker image). Alternatively, use `pgvector/pgvector:pg16` (official pgvector image).
**Warning signs:** `ERROR: extension "vector" is not available` during schema creation.

[VERIFIED: pgvector/pgvector GitHub — Docker images available at `ankane/pgvector` and `pgvector/pgvector:pg16`]

### Pitfall 6: boto3 addressing_style for Alibaba OSS

**What goes wrong:** Default virtual-hosted addressing (`bucket.s3.amazonaws.com`) does not work with OSS. Requests fail with DNS resolution errors.
**Why it happens:** OSS path-style endpoint URLs require `s3={'addressing_style': 'path'}` in the boto3 Config.
**How to avoid:** Pass `Config(s3={'addressing_style': 'path'})` when constructing the S3 client for OSS. Use endpoint format `https://oss-<region>.aliyuncs.com`.
**Warning signs:** `EndpointResolutionError` or DNS failures when connecting to OSS with `endpoint_url`.

[ASSUMED — standard boto3/OSS compatibility pattern; verify at integration test time]

### Pitfall 7: pyproject.toml Python 3.14 cap deviation

**What goes wrong:** The project resolves to Python 3.13.14 (confirmed). The `pyproject.toml` has no upper cap (`>=3.12`). If the user upgrades to 3.14, `sqlite-vec` wheel availability becomes uncertain on Windows.
**Why it happens:** Deferred per memory note. Not a Phase 4 blocker (all cloud packages work on 3.13.x).
**How to avoid:** No action needed for Phase 4. Cloud packages (anthropic, dashscope, voyageai, psycopg, pgvector, boto3) all have 3.13 wheels. Flag at the phase gate if 3.14+ adoption occurs.
**Warning signs:** `ModuleNotFoundError: No module named 'sqlite_vec'` on Python 3.14 Windows.

### Pitfall 8: Conformance suite does NOT inherit from existing conftest.py

**What goes wrong:** Tests in `tests/conformance/` can accidentally pick up fixtures from `tests/conftest.py` (e.g. the `engine` fixture uses SqliteT1 + dim=128) and shadow the conformance parametrized fixtures.
**Why it happens:** pytest fixture lookup traverses parent directories.
**How to avoid:** `tests/conformance/conftest.py` defines its own backend fixtures. Don't name them `engine` or `stub_embedder` — use `t1_backend`, `embedder_backend`, etc.
**Warning signs:** Conformance tests silently only run the local backend.

### Pitfall 9: Sync LocalFS I/O in async context (D-13 note)

**What goes wrong:** `LocalFS.append()` and `LocalFSVault.promote()` use synchronous file I/O inside async wrappers. Both files carry a `D-13` marker comment noting this is acceptable for the local-only MVP path but should be wrapped in `asyncio.to_thread` if contention is observed.
**Why it happens:** Design choice from Phase 1; not a Phase 4 blocker.
**How to avoid:** Phase 4 can optionally add `asyncio.to_thread` wrapping to LocalFS and LocalFSVault if the conformance suite reveals event-loop blocking. Not required.
**Warning signs:** Slow test teardown; event-loop warnings under high-concurrency test scenarios.

---

## STORE-03 Finding: LocalFSVault Already Satisfies the Requirement

STORE-03 requires "the canonical vault (T2) is a git-versioned markdown adapter." The existing `LocalFSVault` in `src/mnema/adapters/vault/local_fs_vault.py` writes per-user markdown files to a configurable `base_dir`. The docstring explicitly states: "Git-versioned: files are intended to be committed to the repository; no git commands are issued by this class."

**Conclusion:** STORE-03 is satisfied by LocalFSVault without any git-commit step. The `build_engine(config)` factory wires `LocalFSVault` for both the fully-local and Qwen+Alibaba configs. No new vault adapter is needed in Phase 4.

[VERIFIED: src/mnema/adapters/vault/local_fs_vault.py — reviewed in this session]

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4.x |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]` — `asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/conformance/ -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROV-03 | DashScope LLM complete() returns non-empty string | unit (gated) | `pytest tests/conformance/test_llm_contract.py -k qwen -x` | ❌ Wave 0 |
| PROV-03 | DashScope Embedder embed() returns correct-dim L2-normalized vectors | unit (gated) | `pytest tests/conformance/test_embedding_contract.py -k qwen -x` | ❌ Wave 0 |
| PROV-04 | Anthropic LLM complete() returns non-empty string | unit (gated) | `pytest tests/conformance/test_llm_contract.py -k anthropic -x` | ❌ Wave 0 |
| PROV-05 | Voyage Embedder embed() returns 1024-dim L2-normalized vectors | unit (gated) | `pytest tests/conformance/test_embedding_contract.py -k voyage -x` | ❌ Wave 0 |
| PROV-06 | Startup dim assertion raises on mismatch (already tested) | unit | `pytest tests/test_providers.py -x` | ✅ |
| PROV-07 | reindex_all() re-embeds all live records with new embedder | unit | `pytest tests/test_migrate.py -x` | ❌ Wave 0 |
| STORE-01 | OSSS3Store append/get/archive match LocalFS behavior | unit (gated) | `pytest tests/conformance/test_object_store_contract.py -k oss -x` | ❌ Wave 0 |
| STORE-02 | PostgresT1 satisfies same RecordStore+VectorIndex contract as SqliteT1 | unit (gated) | `pytest tests/conformance/test_record_store_contract.py -k postgres -x` | ❌ Wave 0 |
| STORE-02 | PostgresT1 vector_search returns live-only records (partial-index) | unit (gated) | `pytest tests/conformance/test_vector_index_contract.py -k postgres -x` | ❌ Wave 0 |
| STORE-03 | LocalFSVault promote()+get_user_model() (already tested) | unit | `pytest tests/test_vault.py -x` | ✅ |
| STORE-04 | build_engine(LocalConfig) returns working MemoryEngine | unit | `pytest tests/test_config.py -x` | ❌ Wave 0 |
| STORE-05 | build_engine(LocalConfig) runs end-to-end (remember+recall+consolidate) | integration | `pytest tests/test_config.py::test_local_end_to_end -x` | ❌ Wave 0 |
| STORE-05 | build_engine(QwenAlibabaConfig) runs end-to-end (gated) | integration (gated) | `pytest tests/test_config.py::test_qwen_alibaba_end_to_end -x` | ❌ Wave 0 |
| STORE-06 | Protected record survives every conformance backend's decay pass | property | `pytest tests/conformance/test_record_store_contract.py -k protected -x` | ❌ Wave 0 |
| STORE-06 | Eviction stores record in cold storage (not hard-delete) | unit | `pytest tests/conformance/test_record_store_contract.py -k eviction -x` | ❌ Wave 0 |
| STORE-06 | Scope isolation: user A cannot read user B's records | unit | `pytest tests/conformance/test_record_store_contract.py -k scope -x` | ❌ Wave 0 |
| SCHED-03 | CronScheduler.schedule() accepts cron string; trigger_now() fires | unit | `pytest tests/conformance/test_scheduler_contract.py -k cron -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -x -q --ignore=tests/conformance` (existing suite, ~56 tests, <10s)
- **Per wave merge:** `uv run pytest tests/ -x -q` (includes conformance local backends)
- **Phase gate:** Full suite green (local backends) + conformance local backends green. Cloud backends green when creds/Docker available but not required for gate.

### Wave 0 Gaps

- [ ] `tests/conformance/__init__.py` — package marker
- [ ] `tests/conformance/conftest.py` — backend fixture registry + skip helpers
- [ ] `tests/conformance/test_llm_contract.py` — covers PROV-03, PROV-04
- [ ] `tests/conformance/test_embedding_contract.py` — covers PROV-03, PROV-05, PROV-06
- [ ] `tests/conformance/test_record_store_contract.py` — covers STORE-02, STORE-06 (protected, scope, eviction)
- [ ] `tests/conformance/test_vector_index_contract.py` — covers STORE-02 (KNN, partial filter)
- [ ] `tests/conformance/test_object_store_contract.py` — covers STORE-01
- [ ] `tests/conformance/test_vault_contract.py` — covers STORE-03 (LocalFSVault only, always-on)
- [ ] `tests/conformance/test_scheduler_contract.py` — covers SCHED-03
- [ ] `tests/test_config.py` — covers STORE-04, STORE-05
- [ ] `tests/test_migrate.py` — covers PROV-07

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| psycopg2 (sync only) | psycopg3 (`psycopg[binary,pool]`) async | psycopg3 GA 2022 | Async Protocol; binary protocol faster; explicit type registration |
| pgvector simple cosine | HNSW with iterative scan | pgvector 0.8.0 | Filtered queries return full k results; iterative_scan is the key setting |
| Fixed embedding dimensions | Matryoshka (Voyage/Qwen) | 2025 | Can choose smaller dims for storage efficiency; fix at config time |
| LangChain/LiteLLM as public seam | Direct official SDKs behind Protocols | Locked decision | Independent embedding axis; no vendor coupling in public API |
| testcontainers 3.x | testcontainers 4.x | 4.0 2024 | `PostgresContainer` API slightly changed; use 4.x |

**Deprecated/outdated:**
- `asyncpg` for pgvector: pgvector-python has `register_vector` for asyncpg too, but MNEMA uses psycopg3.
- `voyageai 0.3.x`: still functional but 0.4.0 adds `AsyncClient`; pin 0.4.0+.
- APScheduler 4.x: NOT used — 4.x has a different API. Pin `<4` (already in pyproject.toml).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DashScope SDK `dashscope.Generation.call()` is the correct text completion entry; `TextEmbedding.call()` is the correct embedding entry | Pattern 2, Pattern 4 | Adapter would fail at runtime; remediation is updating call site |
| A2 | QwenLLM and QwenEmbedder can share a single DashScope API key without global state conflict | Pitfall 4 | Would need per-call api_key passing if SDK is not stateless |
| A3 | Separate `t1_vectors` table (vs embedding column in `t1_records`) is the planner's preferred PostgresT1 design | Pattern 5 | Minor DDL change; Protocol contract is unaffected |
| A4 | Reindex migration `reindex_all()` is exposed as a Python function in `migrate.py` rather than a CLI command | Pattern 9 | Planner may want a CLI wrapper; Python function is still the building block |
| A5 | boto3 path-style addressing (`s3={'addressing_style': 'path'}`) is required for Alibaba OSS | Pitfall 6 | OSS requests would fail; fix at integration test time |
| A6 | OSS T0 append semantics: one S3 object per turn (key = `{session_id}/{offset}.json`) | Pattern 6 | Alternative: JSONL re-upload. One-object-per-turn is simpler and idempotent |
| A7 | DashScope embedding model constant is `TextEmbedding.Models.text_embedding_v4` | Pattern 4 | May be a string literal `"text-embedding-v4"`; verify at install time |

**Claims tagged `[VERIFIED]`:** anthropic 0.109.1, dashscope 1.25.21, voyageai 0.4.0, psycopg 3.3.4, pgvector (Python) 0.4.2, boto3 1.43.29, testcontainers 4.14.2 — all confirmed via `pip index versions` on 2026-06-14.

---

## Open Questions (RESOLVED)

> Resolved in planning: Q1 (voyageai.AsyncClient) → wrap the sync client in `asyncio.to_thread` per D-13 (uniform with the other cloud adapters); confirm `output_dimension` parity at install time. Q2 (PostgresT1 dim check at open()) → enforce via the MemoryEngine startup dim assertion + a `SELECT extversion` guard; not blocking. Q3 (hermetic OSS mock) → use `moto[s3]` as the always-on 2nd object-store backend (Plan 04-00/04-06), no OSS credentials needed for CI.

1. **voyageai.AsyncClient vs asyncio.to_thread**
   - What we know: `voyageai.AsyncClient` is confirmed present in 0.4.0.
   - What's unclear: Whether the async client has API parity with `Client.embed()` including `output_dimension=`.
   - Recommendation: Use `AsyncClient` if parity is confirmed; fall back to `to_thread` if not.

2. **PostgresT1 dim assertion hook**
   - What we know: `MemoryEngine.__init__` checks `if hasattr(t1, "_dim") and embedder.dim != t1._dim`. PostgresT1 will expose `_dim`.
   - What's unclear: Whether to also add a Postgres-specific assertion that the vector column width matches `dim` at open time (via `SELECT attlen FROM pg_attribute WHERE...`).
   - Recommendation: Add the column-width check to `PostgresT1.open()` as a defense-in-depth assertion. Not blocking.

3. **Conformance suite: how to test OSS without live credentials**
   - What we know: D4-04 gates OSS tests behind `MNEMA_TEST_OSS=1`. No local S3-mock is currently in the env.
   - What's unclear: Whether to add moto (AWS mock) as a dev dependency for hermetic OSS contract tests.
   - Recommendation: Add `moto[s3]` to dev dependencies for an always-on S3-mock backend in the object-store conformance suite. This gives ≥2 backends for STORE-01 without requiring credentials. [ASSUMED: moto is the standard boto3 mock; not yet verified]

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | All | ✓ | 3.13.14 (venv) | — |
| uv | Dependency management | ✓ | 0.9.24 | — |
| pytest + pytest-asyncio | Test suite | ✓ | In venv (pytest-asyncio via uv sync --extra dev) | — |
| Docker | PostgresT1 testcontainers | ✗ | — | Skip PostgresT1 conformance; gate behind MNEMA_TEST_PG env var |
| PostgreSQL (live) | PostgresT1 live run | ✗ | — | testcontainers (requires Docker) or MNEMA_TEST_PG DSN |
| anthropic SDK | PROV-04 | ✗ (not installed) | — | Will install via `uv sync --extra cloud` |
| dashscope SDK | PROV-03 | ✗ (not installed) | — | Will install via `uv sync --extra cloud` |
| voyageai SDK | PROV-05 | ✗ (not installed) | — | Will install via `uv sync --extra cloud` |
| psycopg[binary,pool] | STORE-02 | ✗ (not installed) | — | Will install via `uv sync --extra cloud` |
| pgvector (Python) | STORE-02 | ✗ (not installed) | — | Will install via `uv sync --extra cloud` |
| boto3 | STORE-01 | ✗ (not installed) | — | Will install via `uv sync --extra cloud` |
| testcontainers[postgres] | STORE-02 testing | ✗ (not installed) | — | Will install via `uv sync --extra dev` |

**Missing dependencies with no fallback:** None (all cloud deps install via extras; all cloud test paths skip cleanly when Docker/creds absent).

**Missing dependencies with fallback:** Docker (PostgresT1 gated behind env var; conformance suite skips cleanly).

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (API keys) | API keys from environment variables, never hardcoded; Pydantic config reads from env |
| V3 Session Management | no | N/A — MNEMA sessions are memory scoping units, not auth sessions |
| V4 Access Control | yes | `user_id` predicate on every query (already enforced in RecordStore/VectorIndex); PostgresT1 must replicate this |
| V5 Input Validation | yes | Column whitelist for `UPDATE` (already in SqliteT1 `_ALLOWED_COLUMNS`); PostgresT1 must replicate; S3 key validation for session_id |
| V6 Cryptography | no | API keys passed to cloud SDKs; no custom crypto |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-user vector search | Info disclosure | `WHERE user_id = %s` predicate on every PostgresT1 query; never unscoped |
| SQL injection via field names in UPDATE | Tampering | Column whitelist (already in `_ALLOWED_COLUMNS`); replicate in PostgresT1 |
| Path traversal in S3 key construction | Tampering | Validate `session_id` with same regex as LocalFS (`^[A-Za-z0-9_\-]+$`) |
| API key exposure in logs | Info disclosure | Never log API key values; Pydantic SecretStr for key fields in config |
| Hard-delete instead of eviction | Data destruction | Enforced by Protocol contract: `archive()` + `valid_until` never `DELETE` |

---

## Sources

### Primary (HIGH confidence)
- Context7 `/anthropics/anthropic-sdk-python` — messages.create(), AsyncAnthropic pattern
- Context7 `/websites/psycopg_psycopg3` — AsyncConnection.connect(), execute(), cursor pattern
- Context7 `/pgvector/pgvector-python` — register_vector, register_vector_async, HNSW index creation
- Context7 `/pgvector/pgvector` — HNSW partial index, hnsw.iterative_scan, hnsw.ef_search
- Context7 `/websites/voyageai` — Client.embed(), output_dimension, batch patterns
- Context7 `/boto/boto3` — S3 client, endpoint_url pattern
- Context7 `/testcontainers/testcontainers-python` — PostgresContainer, pytest fixture pattern
- PyPI `pip index versions` (2026-06-14) — all package versions verified: anthropic 0.109.1, dashscope 1.25.21, voyageai 0.4.0, psycopg 3.3.4, pgvector 0.4.2, boto3 1.43.29, testcontainers 4.14.2
- Codebase review (2026-06-14) — SqliteT1 DDL/methods, LocalFS, LocalFSVault, InProcessScheduler, engine.py, all port Protocols

### Secondary (MEDIUM confidence)
- APScheduler 3.x CronTrigger.from_crontab() — confirmed from APScheduler docs (already in venv at 3.11.2)
- pgvector/pgvector Docker images (`ankane/pgvector`, `pgvector/pgvector:pg16`) — standard images

### Tertiary (LOW confidence / ASSUMED)
- DashScope Generation.call() and TextEmbedding.call() exact call shapes — SDK not installed; assumed from documentation pattern
- Alibaba OSS boto3 path-style addressing requirement — standard S3-compat pattern, verify at integration time
- OSS T0 append semantics (one object per turn) — design recommendation, not SDK-verified
- moto[s3] for hermetic S3 mock — standard but not verified for this project

---

## Metadata

**Confidence breakdown:**
- Standard stack (package versions): HIGH — all verified via `pip index versions` 2026-06-14
- Anthropic SDK API shape: HIGH — Context7 confirmed
- psycopg3 async + pgvector patterns: HIGH — Context7 confirmed
- voyageai Client.embed() shape: HIGH — Context7 confirmed
- DashScope call shapes: MEDIUM — SDK not installed; API assumed from pattern
- boto3 OSS compatibility: MEDIUM — standard S3-compat pattern; OSS-specific details assumed
- Cron adapter design: HIGH — APScheduler 3.x already in venv
- Conformance suite design: HIGH — standard pytest parametrize pattern

**Research date:** 2026-06-14
**Valid until:** 2026-07-14 (30 days; all packages on fast-moving cadence but breaking changes are minor-version gated)
