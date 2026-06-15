# Phase 2: Consolidation & Supersession - Pattern Map

**Mapped:** 2026-06-13
**Files analyzed:** 8 new/modified files
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/mnema/adapters/llm/__init__.py` | config | — | `src/mnema/adapters/embedding/__init__.py` | exact (empty package init) |
| `src/mnema/adapters/llm/stub.py` | adapter/service | request-response | `src/mnema/adapters/embedding/stub.py` | exact (deterministic stub pattern) |
| `src/mnema/core/consolidation.py` | service | batch + event-driven | `src/mnema/core/write_path.py` | role-match (core pipeline orchestrator) |
| `src/mnema/core/decay.py` | utility | transform | `src/mnema/core/classifier.py` | role-match (pure-function sans-I/O module) |
| `src/mnema/adapters/vector_store/sqlite_t1.py` (new methods) | adapter | CRUD + batch | self (existing methods `upsert`, `update`, `live_records`) | exact (same file, same transaction pattern) |
| `src/mnema/core/engine.py` (modify `consolidate()`) | service | event-driven | self (existing `consolidate()` stub + `WritePath` construction pattern) | exact (same file) |
| `tests/test_consolidation.py` | test | batch | `tests/test_write_path.py` | role-match (integration test class pattern) |
| `tests/test_decay.py` | test | transform | `tests/test_write_path.py` | role-match (unit test class pattern) |

---

## Pattern Assignments

### `src/mnema/adapters/llm/__init__.py` (config, empty package init)

**Analog:** `src/mnema/adapters/embedding/__init__.py` (1 line — empty)

**Core pattern** (line 1):
```python
# empty — one blank line only, matching the embedding __init__.py convention
```

No imports, no exports. The package is discovered by structural typing; there is no `__all__` in any adapter `__init__.py` in the project.

---

### `src/mnema/adapters/llm/stub.py` (adapter, request-response)

**Analog:** `src/mnema/adapters/embedding/stub.py`

**Module docstring pattern** (lines 1-7 of stub.py):
```python
"""StubEmbedder — deterministic, hash-based embedding provider for hermetic CI tests.

Produces consistent, distinguishable L2-normalized unit vectors using SHA-256
without any API calls. Satisfies the EmbeddingProvider Protocol structurally.

No numpy dependency — uses only stdlib hashlib and math.
"""
```
Mirror this for StubLLM: no external deps, satisfies `LLMProvider` Protocol structurally.

**Imports pattern** (lines 9-13 of stub.py):
```python
from __future__ import annotations

import hashlib
import math
```
StubLLM replaces `math` with `json` (no `math` needed); `hashlib` stays for deterministic judge verdicts.

**Class declaration + docstring pattern** (lines 15-28 of stub.py):
```python
class StubEmbedder:
    """Deterministic embedding provider for testing.

    Uses SHA-256 to derive a fixed-length vector from text. Identical inputs
    always produce identical vectors. Distinct inputs produce distinct vectors
    at dim=128 for any realistic test inputs.

    Satisfies EmbeddingProvider Protocol via structural subtyping:
      - dim: int property
      - async embed(texts: list[str]) -> list[list[float]]
      - Contract: all returned vectors are L2-normalized (unit vectors)
    """

    version: str = "stub-v1"

    def __init__(self, dim: int = 128) -> None:
        self._dim = dim
```
Copy this shape: `version: str = "stub-v1"` class attribute, `__init__` with no required args.

**Async method + stdlib-only body pattern** (lines 37-52 of stub.py):
```python
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalized unit vector per text, deterministically.

        Algorithm:
          1. SHA-256 digest of UTF-8 encoded text (32 bytes)
          2. Build dim-length raw vector: raw[i] = digest[i % 32] / 255.0
          3. L2-normalize: divide each element by sqrt(sum of squares)
        """
        results: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw = [digest[i % 32] / 255.0 for i in range(self._dim)]
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            normalized = [x / norm for x in raw]
            results.append(normalized)
        return results
```
StubLLM's `complete()` method follows the same shape: `async def complete(self, prompt: str, *, model: str | None = None) -> str`, dispatches on sentinel text in `prompt`, uses `hashlib.sha256` for the judge branch, `json.dumps` for the extract branch.

**LLMProvider Protocol** (ports/llm.py lines 12-15) — the interface to satisfy:
```python
class LLMProvider(Protocol):
    """Contract for a language model backend."""

    async def complete(self, prompt: str, *, model: str | None = None) -> str: ...
```
StubLLM satisfies this by structural typing — no `(LLMProvider)` base class.

---

### `src/mnema/core/consolidation.py` (service, batch + event-driven)

**Primary analog:** `src/mnema/core/write_path.py`

**Module-level docstring + architecture contract pattern** (lines 1-18 of write_path.py):
```python
"""MNEMA fast write path — T0 append + buffer push + optional provisional T1 write.

WritePath orchestrates the hot online-write path:
  1. Append raw turn verbatim to T0 (object store).
  ...

Architectural note: WritePath imports ONLY from mnema.ports.* and mnema.core.*.
No concrete adapter classes are imported here; this enforces the "core has no
vendor imports" rule from the Architectural Responsibility Map.
"""
```
`consolidation.py` must carry the same "core has no vendor imports" rule in its docstring. All I/O-bearing adapters are injected.

**Imports pattern** (lines 19-33 of write_path.py):
```python
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

from mnema.core.buffer import RecentSessionBuffer
from mnema.core.classifier import looks_like_durable_claim
from mnema.core.schema import MemoryRecord, RecordType, Turn

if TYPE_CHECKING:
    from mnema.ports.embedding import EmbeddingProvider
    from mnema.ports.object_store import ObjectStorePort
    from mnema.ports.record_store import RecordStore
    from mnema.ports.vector_index import VectorIndex
```
Consolidation adds `from mnema.ports.llm import LLMProvider` under `TYPE_CHECKING`; all adapter types stay `TYPE_CHECKING`-only to keep the core vendor-free.

**Constructor dependency injection pattern** (lines 85-99 of write_path.py):
```python
class WritePath:
    def __init__(
        self,
        *,
        embedder: "EmbeddingProvider",
        record_store: "RecordStore",
        vector_index: "VectorIndex",
        t0: "ObjectStorePort",
        staging_queue: asyncio.Queue[Any],
        buffer: RecentSessionBuffer,
    ) -> None:
        self._embedder = embedder
        self._record_store = record_store
        ...
```
`ConsolidationPipeline.__init__` mirrors this keyword-only injection pattern with `llm`, `embedder`, `record_store`, `vector_index`.

**Safety detection reuse** (lines 47-76 of write_path.py):
```python
_SAFETY_KEYWORDS = frozenset(
    {"allerg", "intolerant", "intolerance", "diabeti", "celiac", "coeliac",
     "anaphyl", "medication", "allergy", "epilep", "seizure"}
)

def _is_safety_claim(content: str) -> bool:
    content_lower = content.lower()
    return any(kw in content_lower for kw in _SAFETY_KEYWORDS)
```
Import `_is_safety_claim` from `mnema.core.write_path` in `consolidation.py` — do NOT duplicate it. This is the canonical content-driven safety gate (D2-03).

**Staged write with user_id hard-scoping pattern** (lines 154-176 of write_path.py):
```python
        record = MemoryRecord(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            record_type=resolved_type,
            content=content,
            ...
            protected=protected,
            t0_ref=t0_ref,
            ...
        )

        await self._record_store.upsert(record)
        await self._vector_index.upsert_vector(record.id, embedding)
```
Every write in the consolidation pipeline must carry `user_id` — propagate from the staging-queue item, not from a global. Mirrors the isolation pattern here.

**CONS-08 gate — two-branch early return pattern** (from RESEARCH.md §Pitfall 2, confirmed by write_path structure):
```python
# Copy this two-branch pattern into _maybe_supersede():
if existing.protected or existing.record_type == RecordType.FACT:
    # CONS-08: record contradiction_pending, leave live — NO fall-through
    _record_pending_contradiction(existing, new_record, record_store)
    return
# Only reach here if supersession is permitted
await record_store.supersede(existing.id, new_record, embedding)
```

**Queue drain pattern** — asyncio.QueueEmpty catch (from RESEARCH.md §Code Examples):
```python
items: list[dict] = []
while True:
    try:
        items.append(self._staging.get_nowait())
    except asyncio.QueueEmpty:
        break
```
Note: `self._staging` is on `MemoryEngine`; `ConsolidationPipeline` receives it as a constructor argument (same injection pattern as `staging_queue` in `WritePath`).

---

### `src/mnema/core/decay.py` (utility, transform)

**Primary analog:** `src/mnema/core/classifier.py` (pure-function sans-I/O module)

**Pattern from classifier.py** — read to confirm the sans-I/O, no-class, module-level-function pattern:
```python
# src/mnema/core/classifier.py exports a single pure function
# (no class, no async, no I/O — identical shape required for decay.py)
```

**Module docstring shape** — mirror write_path.py's opening contract comment, adapted for pure sync:
```python
"""MNEMA keep_score decay — pure synchronous, no I/O.

Computes keep_score(record, now) for use by the consolidation pipeline (Phase 2)
and the forgetting/eviction pass (Phase 3).

D-12 compliance: this module contains ZERO I/O operations and ZERO async calls.
It may be imported and called from any context including synchronous test code.
"""
```

**Imports pattern** (stdlib-only, same as StubEmbedder):
```python
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mnema.core.schema import MemoryRecord
```
`MemoryRecord` under `TYPE_CHECKING` only — the function takes it as a parameter but this keeps the module free of runtime Pydantic imports (D-12 purity).

**keep_score pure function** (from RESEARCH.md §Pattern 5, verified formula):
```python
W_RECENCY    = 0.4   # weight on exponential recency decay
W_REINFORCE  = 0.3   # weight on logarithmic access reinforcement
W_SALIENCE   = 0.3   # weight on LLM-judged long-term salience
LAMBDA_DECAY = 0.05  # recency half-life ≈ 14 days  (ln(2)/0.05 ≈ 13.9)

def keep_score(record: "MemoryRecord", now: datetime | None = None) -> float:
    if now is None:
        now = datetime.now(timezone.utc)
    ref_time = record.last_accessed if record.last_accessed is not None else record.created_at
    age_days = max(0.0, (now - ref_time).total_seconds() / 86400.0)
    recency  = math.exp(-LAMBDA_DECAY * age_days)
    reinforce = math.log(1.0 + float(record.access_count))
    score = W_RECENCY * recency + W_REINFORCE * reinforce + W_SALIENCE * record.salience
    return min(1.0, max(0.0, score))
```

**decay_pass companion** — async generator consuming `live_records` (mirrors `live_records` pattern in sqlite_t1.py lines 283-290):
```python
# sqlite_t1.py lines 283-290 — the async generator this function iterates
async def live_records(self, user_id: str) -> AsyncIterator[MemoryRecord]:
    cursor = await self._db.execute(
        "SELECT * FROM t1_records WHERE user_id = ? AND valid_until IS NULL",
        (user_id,),
    )
    async for row in cursor:
        yield row
```
`decay_pass(record_store, user_id, now)` calls `record_store.live_records(user_id)` and calls `keep_score` for each non-protected record.

---

### `src/mnema/adapters/vector_store/sqlite_t1.py` — new methods (CRUD + batch)

**Analog for `supersede()`:** existing `upsert()` method (lines 190-235) + `upsert_vector()` (lines 296-305)

**Transaction commit/rollback pattern** — the ONLY place in the codebase that multi-statement writes are needed; copy from `upsert()` structure but wrap with explicit rollback (from RESEARCH.md §Pattern 2):
```python
# Existing upsert() ends with a bare commit (lines 234-235 of sqlite_t1.py):
        await self._db.commit()

# supersede() wraps all three statements in try/except rollback:
    async def supersede(self, old_id: str, new_record: MemoryRecord, embedding: list[float]) -> None:
        now_str = _dt_to_str(datetime.now(timezone.utc))
        try:
            await self._db.execute(
                "UPDATE t1_records SET valid_until=?, superseded_by=? WHERE id=?",
                (now_str, new_record.id, old_id),
            )
            await self._db.execute(_INSERT_SQL, _record_params(new_record))
            await self._db.execute(
                "INSERT OR REPLACE INTO vec_t1(record_id, embedding) VALUES (?, ?)",
                (new_record.id, _v32(embedding)),
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise
```
`_INSERT_SQL` + `_record_params()` are extracted from the existing inline `upsert()` SQL (lines 191-234). Extract to module-level constants to share with `supersede()`.

**`find_by_t0_ref()` pattern** — mirrors `get()` (lines 237-246 of sqlite_t1.py):
```python
    async def get(self, record_id: str) -> MemoryRecord | None:
        cursor = await self._db.execute(
            "SELECT * FROM t1_records WHERE id = ?", (record_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return row  # type: ignore[return-value]
```
`find_by_t0_ref(t0_ref, user_id)` is identical shape: one `SELECT ... WHERE ... AND valid_until IS NULL`, `fetchone()`, `None` guard, typed return.

**`_ALLOWED_COLUMNS` whitelist** (lines 36-62 of sqlite_t1.py) — already includes all fields Phase 2 needs (`provisional`, `valid_until`, `superseded_by`, `salience`, `record_type`, `keywords`, `graph_edges`). The existing `update()` method (lines 248-281) is the correct tool for provisional reconcile — no new method needed for that path.

**`_v32()` and `_dt_to_str()` helpers** (lines 127-136) — reuse these in `supersede()`; they are already at module scope.

---

### `src/mnema/core/engine.py` — modify `consolidate()` (service, event-driven)

**Analog:** existing `consolidate()` stub (lines 228-238) + `__init__` constructor injection pattern (lines 59-109)

**Constructor injection pattern to extend** (lines 59-109 of engine.py):
```python
    def __init__(
        self,
        *,
        embedder: "EmbeddingProvider",
        t1: Any,
        t0: "ObjectStorePort",
        scheduler: Any,
    ) -> None:
```
Add `llm: "LLMProvider" | None = None` as a keyword-only parameter with default `None` (engine constructs `StubLLM()` when `None`). This preserves backward compatibility for all existing tests that construct `MemoryEngine` without an `llm` argument.

**Existing stub to replace** (lines 228-238 of engine.py):
```python
    async def consolidate(self, *, force: bool = False) -> None:
        """Trigger offline consolidation (stub — Phase 2 will implement batch extract).
        ...
        # TODO Phase 2: drain staging queue — batch extract, salience, supersession
        """
        await self._scheduler.trigger_now()
```
Replace body: construct `ConsolidationPipeline` (or delegate to stored `self._consolidation_pipeline`) and call it; retain `await self._scheduler.trigger_now()` after for scheduling bookkeeping.

**WritePath construction as the wiring model** (lines 95-102 of engine.py):
```python
        self._write_path: WritePath = WritePath(
            embedder=embedder,
            record_store=t1,
            vector_index=t1,
            t0=t0,
            staging_queue=self._staging,
            buffer=self._buffer,
        )
```
Mirror this for `ConsolidationPipeline` construction in `__init__` (store as `self._consolidation_pipeline`).

---

### `tests/test_consolidation.py` (test, integration)

**Primary analog:** `tests/test_write_path.py` (integration test class) + `tests/conftest.py`

**Test class structure** (lines 14-74 of test_write_path.py):
```python
class TestWritePath:
    async def test_durable_claim_produces_t1_record(self, engine) -> None:
        """docstring explaining the invariant being tested."""
        await engine.remember(...)
        records = await engine.t1.get_live_records(user_id="u1")
        assert len(records) >= 1
        assert any(r.provisional for r in records)
```
All test methods are `async def`, take `engine` fixture, use `engine.t1.get_live_records()` for assertions. No `@pytest.mark.asyncio` needed — `asyncio_mode=auto` in `pyproject.toml` covers all async tests.

**Fixture usage pattern** (conftest.py lines 19-55):
```python
@pytest.fixture
async def stub_embedder():
    from mnema.adapters.embedding.stub import StubEmbedder
    return StubEmbedder(dim=128)

@pytest.fixture
async def engine(tmp_path, stub_embedder):
    from mnema import MemoryEngine
    ...
    yield eng
    await scheduler.shutdown()
```
`test_consolidation.py` needs an additional `stub_llm` fixture (analogous to `stub_embedder`) and an `engine_with_llm` fixture that passes `StubLLM` to `MemoryEngine`. Add these fixtures to `conftest.py` or at the top of `test_consolidation.py` with `pytest.fixture` decorators — match the deferred-import style used in `conftest.py`.

**Safety/protection assertion pattern** (lines 53-60 of test_write_path.py):
```python
        records = await engine.t1.get_live_records(user_id="u1")
        assert len(records) == 1
        assert records[0].protected is True
```
CONS-08 tests follow the same assertion shape: `get_live_records()` → check `protected`, `valid_until`, `superseded_by`, `provisional` fields.

---

### `tests/test_decay.py` (test, unit)

**Primary analog:** `tests/test_write_path.py` (simple unit test class, no network/DB fixtures)

**Unit test class shape** (lines 14+ of test_write_path.py — adapted for synchronous pure-function tests):
```python
class TestDecay:
    def test_keep_score_values(self) -> None:
        """Pure sync — no async, no fixtures, no engine required."""
        from mnema.core.decay import keep_score
        from mnema.core.schema import MemoryRecord
        ...
        score = keep_score(record, now=some_datetime)
        assert 0.0 <= score <= 1.0
```
`keep_score` is a pure sync function — tests are plain `def`, not `async def`. No fixtures needed beyond constructing `MemoryRecord` objects inline. This matches the D-12 (sans-I/O) contract.

**Protected-record guard pattern** (same assertion style):
```python
    def test_protected_skipped_before_score_math(self) -> None:
        """The decay_pass caller must skip protected records before keep_score.
        This test verifies the guard is in the caller, not inside keep_score."""
        # Call keep_score directly on a protected record — it must not raise,
        # but the decay_pass loop must have a `if record.protected: continue` guard.
```

---

## Shared Patterns

### User-ID Hard Isolation
**Source:** `src/mnema/core/write_path.py` lines 108-111, `src/mnema/adapters/vector_store/sqlite_t1.py` lines 283-290, 307-344
**Apply to:** `consolidation.py` (every `record_store` call), new `sqlite_t1.py` methods (`find_by_t0_ref`, `supersede`)
```python
# Every query and write carries user_id as an explicit predicate — NEVER global
"SELECT * FROM t1_records WHERE user_id = ? AND valid_until IS NULL"
# OR in vector_search:
params: dict[str, object] = {"q": q_bytes, "k": k, "user_id": user_id}
```

### Structural Typing (No Protocol Base Classes)
**Source:** `src/mnema/adapters/embedding/stub.py` (no `(EmbeddingProvider)` base), `src/mnema/adapters/vector_store/sqlite_t1.py` (no `(RecordStore)` or `(VectorIndex)` base)
**Apply to:** `src/mnema/adapters/llm/stub.py` — `StubLLM` must NOT inherit from `LLMProvider`; it satisfies the Protocol by structural subtyping only (D-08).

### TYPE_CHECKING-only Adapter Imports in Core
**Source:** `src/mnema/core/write_path.py` lines 28-33
```python
if TYPE_CHECKING:
    from mnema.ports.embedding import EmbeddingProvider
    from mnema.ports.object_store import ObjectStorePort
    from mnema.ports.record_store import RecordStore
    from mnema.ports.vector_index import VectorIndex
```
**Apply to:** `src/mnema/core/consolidation.py` and `src/mnema/core/decay.py` — all port/adapter references are string-quoted and under `TYPE_CHECKING`. This enforces the "core has no vendor imports at runtime" architectural rule.

### from \_\_future\_\_ import annotations
**Source:** Every source file in the project (`src/mnema/**/*.py`)
**Apply to:** All new files — first line after the module docstring, before all other imports.

### Deferred Imports in Test Fixtures
**Source:** `tests/conftest.py` lines 22, 37-42
```python
@pytest.fixture
async def stub_embedder():
    from mnema.adapters.embedding.stub import StubEmbedder  # noqa: PLC0415
    return StubEmbedder(dim=128)
```
**Apply to:** `test_consolidation.py` fixtures for `StubLLM` and the `engine_with_llm` fixture. Deferred imports allow pytest to collect tests even before the implementation exists (walking-skeleton phase).

### JSON Serialization of List Columns
**Source:** `src/mnema/adapters/vector_store/sqlite_t1.py` lines 204-213 (upsert) and lines 114-117 (_make_record)
```python
"keywords": json.dumps(record.keywords),
"source_refs": json.dumps(record.source_refs),
"graph_edges": json.dumps(record.graph_edges),
# and in _make_record:
for col in ("keywords", "source_refs", "graph_edges"):
    val = row_dict.get(col)
    if isinstance(val, str):
        row_dict[col] = json.loads(val)
```
**Apply to:** `supersede()` in `sqlite_t1.py` — when building `_record_params(new_record)`, reuse the same `json.dumps` pattern for list columns and `int(record.protected)` / `int(record.provisional)` for bool columns.

### Explicit bool → int Cast for SQLite
**Source:** `src/mnema/adapters/vector_store/sqlite_t1.py` lines 221-222
```python
"protected": int(record.protected),  # T-1-07: explicit cast
"provisional": int(record.provisional),
```
**Apply to:** `_record_params()` helper extracted for `supersede()` — must include the same explicit casts (T-1-07 mitigation).

### Safety Content Detection Import
**Source:** `src/mnema/core/write_path.py` lines 47-76
```python
_SAFETY_KEYWORDS = frozenset({...})

def _is_safety_claim(content: str) -> bool:
    content_lower = content.lower()
    return any(kw in content_lower for kw in _SAFETY_KEYWORDS)
```
**Apply to:** `src/mnema/core/consolidation.py` — import `_is_safety_claim` from `mnema.core.write_path` directly. Do NOT copy the function body or duplicate `_SAFETY_KEYWORDS`. The single canonical safety gate must live in one place (D2-03; [[mnema-protected-flag-content-driven]]).

---

## No Analog Found

All Phase 2 files have analogs. No files fall into this category.

---

## Metadata

**Analog search scope:** `src/mnema/` (all subdirectories), `tests/`
**Files scanned:** 23 source files + 9 test files
**Pattern extraction date:** 2026-06-13
