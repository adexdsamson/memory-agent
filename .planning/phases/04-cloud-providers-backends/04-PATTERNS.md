# Phase 4: Cloud Providers & Backends - Pattern Map

**Mapped:** 2026-06-14
**Files analyzed:** 14 new/modified files
**Analogs found:** 11 / 14 (3 no-analog — config factory, migrate, conformance harness)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/mnema/adapters/llm/anthropic.py` | adapter | request-response | `src/mnema/adapters/llm/stub.py` | role-match (same Protocol contract, different I/O) |
| `src/mnema/adapters/llm/qwen.py` | adapter | request-response | `src/mnema/adapters/llm/stub.py` | role-match |
| `src/mnema/adapters/embedding/voyage.py` | adapter | request-response | `src/mnema/adapters/embedding/stub.py` | role-match (same Protocol: dim + embed + L2-norm) |
| `src/mnema/adapters/embedding/qwen.py` | adapter | request-response | `src/mnema/adapters/embedding/stub.py` | role-match |
| `src/mnema/adapters/vector_store/postgres_t1.py` | adapter | CRUD | `src/mnema/adapters/vector_store/sqlite_t1.py` | exact (same dual-Protocol: RecordStore+VectorIndex) |
| `src/mnema/adapters/object_store/oss_s3.py` | adapter | file-I/O | `src/mnema/adapters/object_store/local_fs.py` | exact (same ObjectStorePort contract) |
| `src/mnema/adapters/scheduler/cron.py` | adapter | event-driven | `src/mnema/adapters/scheduler/in_process.py` | exact (same Scheduler Protocol, same APScheduler library) |
| `src/mnema/config.py` | config + factory | request-response | `src/mnema/core/engine.py` (wiring target) | partial (wiring pattern; no config module exists yet) |
| `src/mnema/migrate.py` | utility | batch | `src/mnema/adapters/vector_store/sqlite_t1.py` (live_records + upsert_vector) | partial (method shape; no migration module exists yet) |
| `tests/conformance/conftest.py` | test config | — | `tests/conftest.py` | role-match (fixture style; conformance needs separate backend params) |
| `tests/conformance/test_llm_contract.py` | test | — | `tests/test_providers.py` | role-match |
| `tests/conformance/test_embedding_contract.py` | test | — | `tests/test_providers.py` | role-match |
| `tests/conformance/test_record_store_contract.py` | test | — | `tests/test_remember_recall.py` | role-match |
| `tests/conformance/test_scheduler_contract.py` | test | — | `tests/test_scheduler.py` | exact |

---

## Pattern Assignments

### `src/mnema/adapters/llm/anthropic.py` (adapter, request-response)

**Analog:** `src/mnema/adapters/llm/stub.py`

**Imports pattern** (stub.py lines 1-12):
```python
"""AnthropicLLM — Anthropic Claude LLM adapter.

Satisfies LLMProvider Protocol by structural typing. Direct anthropic SDK — no
LiteLLM (D4-05). Sync client wrapped in asyncio.to_thread (D-13).
"""
from __future__ import annotations

import asyncio
from anthropic import Anthropic
```

**Class + constructor pattern** (stub.py lines 43-58 — copy shape, swap implementation):
```python
class AnthropicLLM:
    """Anthropic Claude LLM adapter.

    Satisfies LLMProvider Protocol via structural subtyping:
      - async complete(prompt: str, *, model: str | None = None) -> str
    """

    def __init__(self, api_key: str, default_model: str = "claude-haiku-4-5") -> None:
        self._client = Anthropic(api_key=api_key)
        self._default_model = default_model
```

**Core Protocol method pattern** (stub.py lines 59-74 — same signature, real I/O body):
```python
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

**Sentinel dispatch** — real adapters do NOT need `EXTRACT_RECORDS:`/`JUDGE_CONTRADICTION:` dispatch. The stub's `_extract`/`_judge` methods (lines 76-132) are replaced by a plain `_call()` closure. The sentinel protocol is ConsolidationPipeline's concern; adapters are transparent pass-throughs.

**No-analog note:** Retry/timeout — RESEARCH.md Pattern 1 note: "anthropic SDK has built-in retry." Accept SDK defaults for Phase 4; add `tenacity` wrapping only if conformance reveals flakiness.

---

### `src/mnema/adapters/llm/qwen.py` (adapter, request-response)

**Analog:** `src/mnema/adapters/llm/stub.py`

**Imports pattern**:
```python
from __future__ import annotations

import asyncio
import dashscope  # lazy import: never at src/mnema/__init__ — Pitfall 4
```

**Global state pitfall (Pitfall 4)** — set `dashscope.api_key` only inside `__init__`, before any calls. With one QwenLLM instance per engine this is safe; document the global-state risk in the class docstring.

**Core Protocol method** (matches stub.py lines 59-74 shape exactly):
```python
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

**Assumption tag:** DashScope `Generation.call()` shape is ASSUMED (A1 in RESEARCH.md) — verify at `uv sync --extra cloud` time.

---

### `src/mnema/adapters/embedding/voyage.py` (adapter, request-response)

**Analog:** `src/mnema/adapters/embedding/stub.py`

**Imports pattern** (stub.py lines 1-12):
```python
"""VoyageEmbedder — Voyage AI embedding adapter (Claude-compatible embedder, PROV-05).

Satisfies EmbeddingProvider Protocol by structural typing. L2-normalized at adapter
(D4-07). Direct voyageai SDK — no LiteLLM (D4-05).
"""
from __future__ import annotations

import asyncio
import math
import voyageai
```

**dim property pattern** (stub.py lines 33-35 — copy exactly):
```python
    @property
    def dim(self) -> int:
        return self._dim
```

**L2-normalize pattern** (stub.py lines 37-52 — extract the norm calculation as a module-level helper):
```python
# From stub.py lines 46-50 — same math, same structure
def _l2_normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]
```

**embed() pattern** (stub.py lines 37-52 shape — same signature, real I/O body):
```python
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
```

**AsyncClient note (Pitfall 3):** `voyageai.AsyncClient` is available in 0.4.0. If the sync `to_thread` approach causes pytest-asyncio event-loop issues, switch to `await self._async_client.embed(...)` directly. The `output_dimension=` parameter parity must be confirmed first (RESEARCH.md open question 1).

---

### `src/mnema/adapters/embedding/qwen.py` (adapter, request-response)

**Analog:** `src/mnema/adapters/embedding/stub.py`

**Imports + L2 helper** — identical to VoyageEmbedder pattern above, swap `voyageai` for `dashscope`.

**embed() pattern**:
```python
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

**Assumption tag:** DashScope `TextEmbedding.call()` return shape is ASSUMED (A7 in RESEARCH.md) — verify at install time. Model constant may be a string `"text-embedding-v4"` rather than `TextEmbedding.Models.text_embedding_v4`.

---

### `src/mnema/adapters/vector_store/postgres_t1.py` (adapter, CRUD)

**Analog:** `src/mnema/adapters/vector_store/sqlite_t1.py` — THE reference implementation. Every method must match exactly.

**Imports pattern** (sqlite_t1.py lines 1-32):
```python
"""PostgresT1 — Postgres+pgvector T1 working-memory adapter.

Satisfies both RecordStore and VectorIndex Protocols by structural typing (D-08).
psycopg3 async connection + pgvector HNSW partial index (D4-09).
register_vector_async() called immediately after connect (Pitfall 1).
HNSW iterative_scan set at session level before KNN queries (Pitfall 2).
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import numpy as np
import psycopg
from pgvector.psycopg import register_vector_async
```

**_ALLOWED_COLUMNS** (sqlite_t1.py lines 36-62 — copy identically):
```python
_ALLOWED_COLUMNS: frozenset[str] = frozenset({
    "user_id", "session_id", "agent_id", "record_type", "content", "summary",
    "keywords", "embedding_model", "embedding_dim", "embedding_version",
    "protected", "salience", "confidence", "provisional",
    "valid_from", "valid_until", "superseded_by", "t0_ref", "source_refs",
    "access_count", "last_accessed", "created_at", "graph_edges",
})
```

**class + dim property** (sqlite_t1.py lines 198-211 — copy shape):
```python
class PostgresT1:
    def __init__(self, conn: psycopg.AsyncConnection, dim: int) -> None:
        self._conn = conn
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim
```

**open() classmethod** (sqlite_t1.py lines 213-240 — same factory pattern; swap aiosqlite.connect for psycopg.AsyncConnection.connect + register_vector_async):
```python
    @classmethod
    async def open(cls, dsn: str, dim: int) -> "PostgresT1":
        conn = await psycopg.AsyncConnection.connect(dsn, autocommit=False)
        await register_vector_async(conn)   # MUST be called before any vector query — Pitfall 1
        await cls._create_schema(conn, dim)
        return cls(conn, dim)
```

**DDL** — mirrors sqlite_t1.py `_DDL_T1_RECORDS` (lines 67-94) and `_DDL_IDX_LIVE_USER` (lines 96-100) column-for-column. Postgres differences: `BOOLEAN` not `INTEGER`, `TIMESTAMPTZ` not `TEXT`, `JSONB` not `TEXT`, `FLOAT` not `REAL`. See RESEARCH.md Pattern 5 for full Postgres DDL. The `t1_vectors` separate-table design mirrors sqlite_t1's `vec_t1` virtual table.

**supersede() atomicity** (sqlite_t1.py lines 251-291 — copy exactly; swap `BEGIN/COMMIT/ROLLBACK` syntax to psycopg3 async transaction):
```python
    async def supersede(self, old_id: str, new_record: MemoryRecord, embedding: list[float]) -> None:
        try:
            async with self._conn.transaction():
                # Step 1: retire old — must get rowcount=1 (WR-04)
                result = await self._conn.execute(
                    "UPDATE t1_records SET valid_until=NOW(), superseded_by=%s WHERE id=%s AND user_id=%s",
                    (new_record.id, old_id, new_record.user_id),
                )
                if result.rowcount != 1:
                    raise ValueError(
                        f"supersede(): old_id={old_id!r} not found or user_id mismatch"
                    )
                # Step 2: insert new record
                # Step 3: insert new vector
        except Exception:
            raise
```

**vector_search() with HNSW iterative scan** (sqlite_t1.py lines 405-443 — same signature; Postgres uses a JOIN query + SET iterative_scan):
```python
    async def vector_search(self, query_vec: list[float], k: int, *, user_id: str, agent_id: str | None = None) -> list[tuple[str, float]]:
        # CRITICAL: set iterative_scan before KNN query — Pitfall 2
        await self._conn.execute("SET hnsw.iterative_scan = 'strict_order'")
        await self._conn.execute("SET hnsw.ef_search = 100")
        # Then: JOIN t1_vectors + t1_records WHERE user_id=%s AND valid_until IS NULL
        # See RESEARCH.md Pattern 5 for full SQL
```

**upsert_with_vector() atomicity** (sqlite_t1.py lines 375-393 — same try/BEGIN/COMMIT pattern):
```python
    async def upsert_with_vector(self, record: MemoryRecord, embedding: list[float]) -> None:
        try:
            async with self._conn.transaction():
                # INSERT t1_records, then INSERT t1_vectors
                pass
        except Exception:
            raise
```

**Row deserialization** — sqlite_t1.py uses a `_make_record()` row factory (lines 125-143). PostgresT1 uses psycopg3 cursor rows + manual dict assembly. JSONB columns come back as Python dicts/lists automatically (no `json.loads` needed). `BOOLEAN` comes back as Python `bool` natively (no `int()` cast needed — unlike SQLite). Carry the same `protected` and `provisional` field names.

**Security: user_id predicate** — every query in sqlite_t1.py includes `AND user_id = ?`. PostgresT1 must replicate on every SELECT/UPDATE — cross-user reads are the primary security invariant (RESEARCH.md threat table).

---

### `src/mnema/adapters/object_store/oss_s3.py` (adapter, file-I/O)

**Analog:** `src/mnema/adapters/object_store/local_fs.py` — same four-method ObjectStorePort contract.

**Imports pattern** (local_fs.py lines 1-28):
```python
"""OSSS3Store — S3-compatible T0 object store (Alibaba OSS / AWS S3 / MinIO).

Satisfies ObjectStorePort Protocol by structural typing.
endpoint_url must be set for non-AWS providers (OSS: https://oss-<region>.aliyuncs.com).
Path-style addressing required for OSS (Pitfall 6).
boto3 sync client wrapped in asyncio.to_thread (D-13).
"""
from __future__ import annotations

import asyncio
import json
import re

import boto3
from botocore.config import Config

from mnema.core.schema import MemoryRecord, Turn
```

**session_id validation** (local_fs.py lines 32-44 — copy exactly; same regex, same exception):
```python
_VALID_SESSION_ID = re.compile(r"^[A-Za-z0-9_\-]+$")

def _validate_session_id(session_id: str) -> None:
    if not _VALID_SESSION_ID.match(session_id):
        raise ValueError(
            f"Invalid session_id {session_id!r}: only alphanumeric characters, "
            "hyphens, and underscores are permitted."
        )
```

**constructor pattern** (local_fs.py lines 50-58 shape — swap Path for boto3 client):
```python
class OSSS3Store:
    def __init__(self, bucket: str, *, aws_access_key_id: str,
                 aws_secret_access_key: str, endpoint_url: str | None = None,
                 region_name: str = "us-east-1") -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            endpoint_url=endpoint_url,
            region_name=region_name,
            config=Config(s3={"addressing_style": "path"}),  # OSS requires path-style — Pitfall 6
        )
```

**append() pattern** (local_fs.py lines 60-79 — same return value contract `t0://session_id/N`; S3 uses one object per turn at key `{session_id}/{offset}.json`):
```python
    async def append(self, session_id: str, turn: Turn) -> str:
        _validate_session_id(session_id)
        # Count existing objects under prefix session_id/ to determine offset
        # Then put_object at key={session_id}/{offset}.json
        # Return f"t0://{session_id}/{offset}"
        def _call() -> str:
            resp = self._client.list_objects_v2(Bucket=self._bucket, Prefix=f"{session_id}/")
            offset = resp.get("KeyCount", 0)
            key = f"{session_id}/{offset}.json"
            self._client.put_object(Bucket=self._bucket, Key=key, Body=turn.model_dump_json().encode())
            return f"t0://{session_id}/{offset}"
        return await asyncio.to_thread(_call)
```

**get() pattern** (local_fs.py lines 81-117 — same ref parsing logic `t0://session_id/N`; S3 uses get_object instead of file read):
```python
    async def get(self, ref: str) -> Turn:
        # Ref parsing: identical to local_fs.py lines 88-104
        if not ref.startswith("t0://"):
            raise ValueError(f"Invalid t0 ref format: {ref!r}")
        # ... parse session_id and offset ...
        _validate_session_id(session_id)
        def _call() -> Turn:
            key = f"{session_id}/{offset}.json"
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
            return Turn.model_validate(json.loads(obj["Body"].read()))
        return await asyncio.to_thread(_call)
```

**archive() and append_audit()** (local_fs.py lines 119-139 — same method signatures; S3 uses put_object to `archived/{record.id}.json` and `eviction_audit/{timestamp}.json` respectively):
```python
    async def archive(self, record: MemoryRecord) -> str:
        # put_object to key=f"archived/{record.id}.json"
        # return f"archived://{record.id}"

    async def append_audit(self, entry: dict) -> None:
        # put_object to key=f"eviction_audit/{entry['evicted_at']}/{entry['record_id']}.json"
```

---

### `src/mnema/adapters/scheduler/cron.py` (adapter, event-driven)

**Analog:** `src/mnema/adapters/scheduler/in_process.py` — exact Protocol match; same APScheduler library.

**Imports pattern** (in_process.py lines 1-21 — copy imports, add CronTrigger):
```python
"""CronScheduler — APScheduler 3.x CronTrigger behind the Scheduler Protocol.

Satisfies Scheduler Protocol via structural subtyping (SCHED-03).
APScheduler 3.x only (pinned <4 in pyproject.toml — 4.x has a different API).
CronTrigger.from_crontab() parses standard 5-field cron expressions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger          # type: ignore[import-untyped]

JOB_ID = "consolidate"
```

**class shape** (in_process.py lines 24-70 — copy all four async methods verbatim; only `schedule()` changes):
```python
class CronScheduler:
    JOB_ID: str = JOB_ID

    def __init__(self, cron_expression: str) -> None:
        self._cron = cron_expression
        self._scheduler: AsyncIOScheduler = AsyncIOScheduler()

    async def start(self) -> None:
        self._scheduler.start()  # identical to InProcessScheduler.start()

    async def schedule(self, fn: Any, *, every_seconds: int = 0) -> None:
        # every_seconds ignored — cron_expression governs timing
        trigger = CronTrigger.from_crontab(self._cron)
        self._scheduler.add_job(fn, trigger, id=self.JOB_ID, next_run_time=None)

    async def trigger_now(self) -> None:
        # Copy verbatim from in_process.py lines 58-66
        job = self._scheduler.get_job(self.JOB_ID)
        if job is not None:
            job.modify(next_run_time=datetime.now())

    async def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)  # identical to InProcessScheduler.shutdown()
```

---

### `src/mnema/config.py` (config + factory)

**No direct analog** — no config module exists yet. Pattern derives from two sources:

1. **Wiring target** (`src/mnema/core/engine.py` lines 59-153): The `MemoryEngine.__init__` signature is what `build_engine()` must satisfy. All six adapter parameters (`embedder`, `t1`, `t0`, `scheduler`, `llm`, `vault`) must be wired.

2. **RESEARCH.md Pattern 8** (Pydantic v2 discriminated union config — lines 591-632): Concrete `LocalConfig` and `QwenAlibabaConfig` model shapes with literal type discriminators.

**Key wiring pattern** (engine.py lines 75-153):
```python
# build_engine() must produce:
engine = MemoryEngine(
    embedder=embedder,   # EmbeddingProvider
    t1=t1,              # RecordStore + VectorIndex (structural)
    t0=t0,              # ObjectStorePort
    scheduler=scheduler, # Scheduler
    llm=llm,            # LLMProvider | None
    vault=vault,        # VaultStore | None
)
```

**Startup dim assertion wiring** (engine.py lines 97-103) — `build_engine()` does NOT add a separate dim check; engine.__init__ already raises `ValueError` if `embedder.dim != t1._dim`. The factory just ensures it passes the same `embedder_dim` to both axes.

**Pydantic SecretStr** — RESEARCH.md security table: API keys must be `SecretStr` fields in config models to prevent accidental logging. This is a discretion detail the planner should enforce.

**Lazy import pattern** (engine.py lines 108-110 — same deferred import to keep core vendor-free):
```python
# Adapters imported lazily inside build_engine(), not at module top
# (mirrors engine.py's deferred import of StubLLM)
def build_engine(config: MnemaConfig) -> MemoryEngine:
    if isinstance(config, LocalConfig):
        from mnema.adapters.embedding.stub import StubEmbedder  # noqa: PLC0415
        ...
```

---

### `src/mnema/migrate.py` (utility, batch)

**No direct analog** — no migration module exists yet. Pattern derives from:

**live_records() iterator** (sqlite_t1.py lines 362-369 — this is the loop source):
```python
    async def live_records(self, user_id: str) -> AsyncIterator[MemoryRecord]:
        cursor = await self._db.execute(
            "SELECT * FROM t1_records WHERE user_id = ? AND valid_until IS NULL",
            (user_id,),
        )
        async for row in cursor:
            yield row
```

**upsert_vector() method** (sqlite_t1.py lines 394-403 — this is the loop sink):
```python
    async def upsert_vector(self, record_id: str, embedding: list[float]) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO vec_t1(record_id, embedding) VALUES (?, ?)",
            (record_id, _v32(embedding)),
        )
        await self._db.commit()
```

**reindex_all() shape** — RESEARCH.md Pattern 9 (lines 640-658) is the direct code to copy. Key requirement: caller must delete all existing vectors for the user and (for PostgresT1) recreate the vector column at the new dim before calling `reindex_all()`. The function itself is a pure `async for record in t1.live_records(user_id)` loop.

---

## Conformance Suite Patterns

### `tests/conformance/conftest.py` (test config)

**Analog:** `tests/conftest.py`

**Critical difference (Pitfall 8):** Do NOT use fixture names `engine`, `stub_embedder`, `stub_llm` — these conflict with parent conftest. Use `t1_backend`, `embedder_backend`, `llm_backend`, `object_store_backend`, `scheduler_backend`.

**Fixture shape** (tests/conftest.py lines 19-55 — copy yield pattern + scheduler teardown):
```python
# tests/conftest.py lines 19-24 — fixture shape to copy
@pytest.fixture
async def stub_embedder():
    from mnema.adapters.embedding.stub import StubEmbedder
    return StubEmbedder(dim=128)

# Yield + teardown pattern (lines 28-55):
@pytest.fixture
async def engine(tmp_path, stub_embedder):
    ...
    yield eng
    await scheduler.shutdown()  # teardown in yield fixture
```

**Skip helper pattern** (RESEARCH.md Pattern 10 lines 674-698 — the parametrize+skipif shape):
```python
import os
import pytest

def _pg_available() -> bool:
    return bool(os.environ.get("MNEMA_TEST_PG"))

@pytest.fixture(
    params=["sqlite", pytest.param("postgres", marks=pytest.mark.skipif(
        not _pg_available(),
        reason="Postgres not available: set MNEMA_TEST_PG=1 or provide Docker"
    ))]
)
async def t1_backend(request, tmp_path):
    if request.param == "sqlite":
        from mnema.adapters.vector_store.sqlite_t1 import SqliteT1
        yield await SqliteT1.open(":memory:", dim=128)
    elif request.param == "postgres":
        ...
```

**ENV var gates** (CONTEXT.md D4-04): `MNEMA_TEST_DASHSCOPE`, `MNEMA_TEST_ANTHROPIC`, `MNEMA_TEST_VOYAGE`, `MNEMA_TEST_OSS`, `MNEMA_TEST_PG` — one guard per cloud axis.

---

### `tests/conformance/test_llm_contract.py` + `test_embedding_contract.py`

**Analog:** `tests/test_providers.py`

**Test class style** (test_providers.py lines 18-43 — class-based, method per assertion):
```python
class TestLLMContract:
    async def test_complete_returns_nonempty_string(self, llm_backend) -> None:
        result = await llm_backend.complete("EXTRACT_RECORDS: hello")
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_complete_stub_sentinel_dispatch(self, llm_backend) -> None:
        # Only assert on StubLLM behavior; skip sentinel assertion for real adapters
        ...
```

**Dim assertion test** (test_providers.py lines 19-43 — copy the pytest.raises pattern):
```python
    async def test_dim_mismatch_raises_at_startup(self, tmp_path) -> None:
        dim_mismatch = "[Ee]mbedding.*dim|dim.*mismatch"
        with pytest.raises(ValueError, match=dim_mismatch):
            MemoryEngine(embedder=StubEmbedder(dim=128), t1=t1_64, ...)
```

---

### `tests/conformance/test_scheduler_contract.py`

**Analog:** `tests/test_scheduler.py` — exact pattern match.

**Test shape** (test_scheduler.py lines 17-45 — copy entirely; parametrize over `[InProcessScheduler, CronScheduler]`):
```python
class TestSchedulerContract:
    async def test_trigger_now_fires_consolidate(self, scheduler_backend) -> None:
        call_count = 0
        async def sentinel() -> None:
            nonlocal call_count
            call_count += 1
        await scheduler_backend.schedule(sentinel, every_seconds=3600)
        await scheduler_backend.trigger_now()
        await asyncio.sleep(0.2)
        assert call_count >= 1
```

---

### `tests/conformance/test_record_store_contract.py`

**Analog:** `tests/test_remember_recall.py` + `tests/test_forgetting.py`

**Safety invariant pattern** — every conformance backend must assert:
1. Protected record is NOT evicted by `evict()` (from tests/test_forgetting.py — copy the `test_protected_records_never_evicted` Hypothesis test structure)
2. Evicted record is archived, not hard-deleted (from tests/test_forgetting.py — check `archived.jsonl` or equivalent cold store)
3. Scope isolation: user A cannot read user B's records (from tests/test_scope_isolation.py)

---

## Shared Patterns

### Structural Typing (all new adapters)
**Source:** `src/mnema/adapters/llm/stub.py` lines 43-55 docstring convention  
**Apply to:** All 7 new adapter files  
```python
"""<ClassName> — <one-line description>.

Satisfies <ProtocolName> Protocol by structural typing.
"""
```
No `class MyAdapter(LLMProvider):` inheritance — structural typing only (D-08).

### asyncio.to_thread wrapping (all cloud adapters)
**Source:** `src/mnema/adapters/scheduler/in_process.py` — APScheduler sync calls are NOT wrapped in to_thread because AsyncIOScheduler is async-native. For SDK adapters with sync I/O the pattern is:  
**Apply to:** `anthropic.py`, `qwen.py` (LLM), `voyage.py`, `qwen.py` (embedding), `oss_s3.py`
```python
async def complete(self, prompt: str, *, model: str | None = None) -> str:
    def _call() -> str:
        ...  # sync SDK call
    return await asyncio.to_thread(_call)
```

### from __future__ import annotations (all new files)
**Source:** Every existing adapter file (stub.py line 7, sqlite_t1.py line 20, local_fs.py line 22, etc.)  
**Apply to:** All new `.py` files  
```python
from __future__ import annotations
```

### Deferred imports inside factory/engine bodies
**Source:** `src/mnema/core/engine.py` lines 108-110 and 143-144  
**Apply to:** `src/mnema/config.py` `build_engine()`, `tests/conformance/conftest.py` fixture bodies  
```python
# Never at module top for optional-extra adapters
from mnema.adapters.llm.anthropic import AnthropicLLM  # noqa: PLC0415
```

### Path validation (object store adapters)
**Source:** `src/mnema/adapters/object_store/local_fs.py` lines 32-44  
**Apply to:** `src/mnema/adapters/object_store/oss_s3.py` — copy `_VALID_SESSION_ID` regex and `_validate_session_id()` function verbatim. Same validation must gate S3 key construction.

### _ALLOWED_COLUMNS whitelist (vector store adapters)
**Source:** `src/mnema/adapters/vector_store/sqlite_t1.py` lines 36-62  
**Apply to:** `src/mnema/adapters/vector_store/postgres_t1.py` — copy the frozenset verbatim. The `update()` method must perform the same whitelist check before interpolating column names into SQL.

### user_id predicate on every query (vector store adapters)
**Source:** `src/mnema/adapters/vector_store/sqlite_t1.py` — present on `find_by_t0_ref` (line 314), `live_records` (line 364), `vector_search` (line 429), `get_live_records` (line 477)  
**Apply to:** `src/mnema/adapters/vector_store/postgres_t1.py` — every SELECT/UPDATE must include `AND user_id = %s` (psycopg3 uses `%s` not `?`).

---

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns directly):

| File | Role | Data Flow | Reason | RESEARCH.md Reference |
|------|------|-----------|--------|----------------------|
| `src/mnema/config.py` | config + factory | request-response | No config module exists; `MemoryEngine.__init__` is the wiring target but not a factory | Pattern 8 (lines 591-632) |
| `src/mnema/migrate.py` | utility | batch | No migration or reindex module exists | Pattern 9 (lines 635-660) |
| `tests/conformance/conftest.py` + contract test modules | test infrastructure | — | Parametrized multi-backend fixture pattern is new; existing conftest.py is single-backend | Pattern 10 (lines 663-698) + Pitfall 8 |

---

## Metadata

**Analog search scope:** `src/mnema/adapters/`, `src/mnema/core/`, `src/mnema/ports/`, `tests/`  
**Files read:** 14 (stubs, sqlite_t1, local_fs, local_fs_vault, in_process, engine, conftest, all port protocols, test_providers, test_scheduler)  
**Pattern extraction date:** 2026-06-14  
**Key structural observation:** All 7 existing adapters follow the same three-part pattern: (1) `from __future__ import annotations` + stdlib-only imports at top, (2) structural-typing class with no Protocol inheritance, (3) async methods that never block the event loop. New cloud adapters must follow this exactly — the only difference is the I/O leaf (SDK call inside `asyncio.to_thread`).
