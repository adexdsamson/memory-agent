# Phase 3: Forgetting, Salience Floor, Budget Packer & MCP - Pattern Map

**Mapped:** 2026-06-14
**Files analyzed:** 12 (8 new files + 4 modified files)
**Analogs found:** 11 / 12 (MCP server has no internal analog — see No Analog Found section)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/mnema/core/engine.py` (modify) | engine/orchestrator | CRUD + event-driven | `src/mnema/core/engine.py` itself | self |
| `src/mnema/core/recall.py` (modify) | service/pure-logic | request-response | `src/mnema/core/decay.py` | role-match (pure-sync additions) |
| `src/mnema/core/packer.py` (new) | utility/pure-logic | transform | `src/mnema/core/decay.py` | role-match (D-12 sans-I/O module) |
| `src/mnema/ports/vault.py` (new) | port/Protocol | request-response | `src/mnema/ports/scheduler.py` | exact (Protocol-only, async, no `@runtime_checkable`) |
| `src/mnema/adapters/vault/local_fs_vault.py` (new) | adapter/file-I/O | file-I/O | `src/mnema/adapters/object_store/local_fs.py` | exact (LocalFS file-writing pattern) |
| `src/mnema/adapters/object_store/local_fs.py` (modify) | adapter/file-I/O | file-I/O | self | self |
| `src/mnema/core/consolidation.py` (modify) | pipeline/orchestrator | batch | `src/mnema/core/consolidation.py` itself | self |
| `src/mnema/mcp/server.py` (new) | server/facade | request-response | **none** | no-analog (see below) |
| `src/mnema/mcp/__init__.py` (new) | package init | — | `src/mnema/adapters/__init__.py` | trivial |
| `tests/test_forgetting.py` (new) | test | CRUD + property | `tests/test_decay.py` | exact |
| `tests/test_recall_packer.py` (new) | test | transform | `tests/test_decay.py` | role-match (sync pure-logic test style) |
| `tests/test_vault.py` (new) | test | file-I/O | `tests/test_consolidation.py` | role-match (integration + async fixture) |
| `tests/test_mcp_server.py` (new) | test | request-response | `tests/test_sdk_interface.py` | role-match (engine fixture + async roundtrip) |

---

## Pattern Assignments

### `src/mnema/core/engine.py` — forget() stub fill + evict() + recall() budget param

**Analog:** `src/mnema/core/engine.py` (self-modification)

**Imports pattern** (lines 32–44) — keep existing, add:
```python
from typing import Optional  # already present
# Add at method level (deferred import per convention):
# from mnema.core.decay import decay_pass  (inside evict body)
# from mnema.core.packer import pack_records, TiktokenCounter  (inside recall body)
```

**User-id scope check pattern** (lines 228–235) — copy for `forget()` scope guard:
```python
# From engine.expand() — the established scope-check pattern (T-1-10)
record: Optional[MemoryRecord] = await self._t1.get(record_id)
if record is None:
    return None
# T-1-10: scope check — no T0 data crosses user boundaries
if record.user_id != user_id:
    return None
```

**Forget stub signature** (lines 240–250) — fills into:
```python
async def forget(
    self, record_id: str, *, user_id: str, reason: str = ""
) -> None:
    """Mark a record for eviction (stub — Phase 3 will implement decay/eviction).

    Phase 3 will: set valid_until, move to T0 cold storage, clear from vector
    index, add to eviction audit log. For Phase 1 this is a no-op.

    # TODO Phase 3: evict to cold storage — set valid_until, archive to T0/OSS
    """
    pass  # noqa: PIE790
```

**Recall signature to extend** (lines 186–214) — add `budget: int | None = None` parameter:
```python
async def recall(
    self,
    query: str,
    *,
    user_id: str,
    agent_id: Optional[str] = None,
    k: int = 30,
    budget: int | None = None,    # Phase 3: None = return all ranked; set = apply packer
) -> list[MemoryRecord]:
```

**Constructor wiring pattern** (lines 60–133) — new `vault` kwarg follows the established optional-adapter pattern (mirrors `llm: LLMProvider | None = None`):
```python
def __init__(
    self,
    *,
    embedder: "EmbeddingProvider",
    t1: Any,
    t0: "ObjectStorePort",
    scheduler: Any,
    llm: "LLMProvider | None" = None,
    vault: Any = None,   # VaultStore | None — new Phase 3 axis
) -> None:
```

---

### `src/mnema/core/recall.py` — add re_rank() + route budget to packer

**Analog:** `src/mnema/core/decay.py` (same D-12 pure-sync module pattern)

**Module-level constant pattern** (decay.py lines 35–64) — copy for `LAMBDA_DECAY` import and re-rank constants:
```python
# From decay.py lines 35–64 — module-level tunable with inline rationale comment
LAMBDA_DECAY: float = 0.05
"""Recency half-life constant.
Half-life = ln(2) / LAMBDA_DECAY ≈ 13.9 days.
"""
```

**Pure-sync function pattern** (decay.py lines 72–115) — the `keep_score` function is the template for `re_rank()`:
```python
# Pure sync per D-12 — no I/O, no async, no imports at runtime beyond math and datetime.
def keep_score(record: "MemoryRecord", now: datetime | None = None) -> float:
    """Return the retention score for *record* in [0.0, 1.0]."""
    if now is None:
        now = datetime.now(timezone.utc)
    ref_time = record.last_accessed if record.last_accessed is not None else record.created_at
    age_days = max(0.0, (now - ref_time).total_seconds() / 86400.0)
    recency = math.exp(-LAMBDA_DECAY * age_days)
    # ...
    return min(1.0, max(0.0, score))
```

**Import block pattern** (recall.py lines 27–39) — TYPE_CHECKING guard for port imports:
```python
from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from mnema.core.schema import MemoryRecord, RecordType
if TYPE_CHECKING:
    from mnema.ports.embedding import EmbeddingProvider
    from mnema.ports.record_store import RecordStore
    from mnema.ports.vector_index import VectorIndex
```

**RecallPath.execute() return pattern** (recall.py lines 91–161) — Phase 3 adds re-rank + packer call after line 161 (before `return`):
```python
# Phase 1 returns at line 161:
return t1_records + buffer_records
# Phase 3 inserts re-rank + pack between combining and returning:
# combined = t1_records + buffer_records
# ranked = re_rank(combined, similarity_scores, now)
# if budget is not None:
#     return pack_records(ranked, budget, TiktokenCounter())
# return ranked
```

---

### `src/mnema/core/packer.py` (new) — BudgetPacker + TokenCounter Protocol

**Analog:** `src/mnema/core/decay.py` (D-12 pure-sync, sans-I/O module)

**Module docstring pattern** (decay.py lines 1–19):
```python
"""MNEMA keep_score decay — pure synchronous, no I/O.

D-12 compliance: this module contains ZERO I/O operations and ZERO async calls.
It may be imported and called from any context including synchronous test code.
"""
```

**Protocol definition pattern** (ports/scheduler.py lines 1–35) — no `@runtime_checkable`, async methods, minimal interface:
```python
from typing import Protocol

class Scheduler(Protocol):
    """Contract for a background consolidation scheduler."""

    async def schedule(self, fn: object, *, every_seconds: int) -> None:
        """Register a recurring consolidation function."""
        ...

    async def trigger_now(self) -> None:
        ...
```
Apply same structure for `TokenCounter` Protocol (sync, not async — D-12).

**Deferred import inside class pattern** (engine.py lines 94–96) — use for tiktoken import inside `TiktokenCounter.__init__`:
```python
# Deferred import avoids import-time failure if tiktoken not installed
if llm is None:
    from mnema.adapters.llm.stub import StubLLM  # noqa: PLC0415
    llm = StubLLM()
```

---

### `src/mnema/ports/vault.py` (new) — VaultStore Protocol (6th axis)

**Analog:** `src/mnema/ports/scheduler.py` (exact match: Protocol-only file, async, no `@runtime_checkable`)

**Full file pattern** (scheduler.py lines 1–35):
```python
"""Scheduler port — SCHED-01/02.

Async methods (D-11 async-first). ...
No @runtime_checkable — static checking only (D-10).
"""

from __future__ import annotations
from typing import Protocol


class Scheduler(Protocol):
    """Contract for a background consolidation scheduler."""

    async def schedule(self, fn: object, *, every_seconds: int) -> None:
        """Register a recurring consolidation function."""
        ...

    async def trigger_now(self) -> None:
        """Force an immediate fire of the scheduled function (SCHED-02)."""
        ...

    async def start(self) -> None:
        """Start the scheduler background thread/loop."""
        ...

    async def shutdown(self) -> None:
        """Shutdown the scheduler, releasing resources."""
        ...
```

**ObjectStorePort pattern** (ports/object_store.py lines 1–33) — imports `MemoryRecord` from schema (same pattern `vault.py` needs):
```python
from mnema.core.schema import MemoryRecord, Turn

class ObjectStorePort(Protocol):
    async def archive(self, record: MemoryRecord) -> str:
        """Archive a T1 record to cold storage; returns an archive ref."""
        ...
```

`VaultStore` follows the same shape: two async methods (`promote`, `get_user_model`), import `MemoryRecord`, no `@runtime_checkable`.

---

### `src/mnema/adapters/vault/local_fs_vault.py` (new) — LocalFSVault adapter

**Analog:** `src/mnema/adapters/object_store/local_fs.py` (exact match: LocalFS file-writing adapter)

**Constructor + base dir pattern** (local_fs.py lines 50–58):
```python
class LocalFS:
    """Local filesystem T0 object store — JSONL per session, append-only."""

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
```

**Path construction pattern** (local_fs.py lines 64–67):
```python
path = self._base / f"{session_id}.jsonl"
```
Apply as: `path = self._base / f"{user_id}.md"`

**Path traversal validation pattern** (local_fs.py lines 32–44) — copy `_VALID_SESSION_ID` regex and `_validate_session_id()` for `user_id` validation in `_vault_path()`:
```python
_VALID_SESSION_ID = re.compile(r"^[A-Za-z0-9_\-]+$")

def _validate_session_id(session_id: str) -> None:
    """Raise ValueError if session_id contains characters that could be used for path traversal."""
    if not _VALID_SESSION_ID.match(session_id):
        raise ValueError(
            f"Invalid session_id {session_id!r}: only alphanumeric characters, "
            "hyphens, and underscores are permitted."
        )
```

**File write pattern** (local_fs.py lines 75–79) — append-mode write, UTF-8:
```python
with path.open("a", encoding="utf-8") as fh:
    fh.write(turn.model_dump_json() + "\n")
```

**File read pattern** (local_fs.py lines 119–127) — read-if-exists + write:
```python
async def archive(self, record: MemoryRecord) -> str:
    path = self._base / "archived.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(record.model_dump_json() + "\n")
    return f"archived://{record.id}"
```

**Structural-typing note:** `LocalFSVault` does NOT inherit from `VaultStore`. It satisfies the Protocol by structural typing (D-08) — same as `LocalFS` satisfies `ObjectStorePort`.

---

### `src/mnema/adapters/object_store/local_fs.py` (modify) — complete archive() + add append_audit()

**Analog:** self (existing `archive()` stub at lines 119–127)

**Existing stub to fill** (local_fs.py lines 119–127):
```python
async def archive(self, record: MemoryRecord) -> str:
    """Archive a T1 record to cold storage; returns an archive ref.

    Phase 3 eviction path — stub implementation sufficient for Phase 1.
    """
    path = self._base / "archived.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(record.model_dump_json() + "\n")
    return f"archived://{record.id}"
```

Phase 3 adds `append_audit()` as a new method following the same append pattern. The JSONL audit path is `{base_dir}/eviction_audit.jsonl`. Method signature:
```python
async def append_audit(self, entry: dict) -> None:
    """Append one eviction audit entry to the JSONL audit log (FORG-04)."""
    import json  # noqa: PLC0415
    path = self._base / "eviction_audit.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
```

Also add `append_audit` to `ObjectStorePort` Protocol (`src/mnema/ports/object_store.py`).

---

### `src/mnema/core/consolidation.py` (modify) — add vault promotion + eviction hooks after decay_pass

**Analog:** self (existing `run()` method, lines 112–147)

**Existing decay_pass consumption pattern** (consolidation.py lines 135–147) — Phase 3 replaces the bare loop body:
```python
# Step 7: decay_pass over all live records, per unique user_id processed.
from mnema.core.decay import decay_pass  # noqa: PLC0415

processed_user_ids: set[str] = {
    item.get("user_id", "")
    for item in items
    if item.get("user_id")
}
for uid in processed_user_ids:
    async for _record, _score in decay_pass(self._record_store, uid):
        pass  # Phase 3 will act on scores; Phase 2 exercises the code path
```

Phase 3 replaces `pass` with the eviction check. **Ordering is load-bearing** (RESEARCH.md Pitfall 8): vault promotion runs BEFORE eviction.

**Module-level constant pattern** (decay.py lines 35–64) — for `VAULT_SALIENCE_THRESHOLD` and `KEEP_THRESHOLD`:
```python
VAULT_SALIENCE_THRESHOLD: float = 0.7
"""Records confirmed + salience >= this value are promoted to T2 vault (D3-11).
Tune in Phase 5 demo eval.
"""

KEEP_THRESHOLD: float = 0.3
"""Records with keep_score < KEEP_THRESHOLD are evicted to cold storage.
Tune against Phase 5 demo evaluation. 0.3 is the Claude's-discretion starting point.
"""
```

**Constructor injection pattern** (consolidation.py lines 80–106) — add `vault: Any = None` kwarg following same optional-adapter pattern as `llm`:
```python
def __init__(
    self,
    *,
    llm: "LLMProvider",
    embedder: "EmbeddingProvider",
    record_store: "RecordStore",
    vector_index: "VectorIndex",
    staging_queue: asyncio.Queue[Any],
    vault: Any = None,   # VaultStore | None (6th axis, Phase 3)
) -> None:
    # ...
    self._vault = vault
```

---

### `src/mnema/mcp/server.py` (new) — FastMCP server

**NO INTERNAL ANALOG.** See "No Analog Found" section below. Use RESEARCH.md Pattern 5 (lines 657–738) directly.

Key shape to copy:
- Factory function `create_mcp_server(engine) -> FastMCP`
- Closure-capture injection (engine passed into factory, captured by nested `@mcp.tool` functions)
- All 5 tools are `async def` — they `await engine.<verb>(...)`
- `user_id` is explicit, required, non-defaulted on every tool (D3-14)
- `mcp = FastMCP("mnema")` — the name string
- `if __name__ == "__main__":` block with `mcp_server.run()` for stdio entry point

---

### `tests/test_forgetting.py` (new) — FORG-02/03/04

**Analog:** `tests/test_decay.py` (exact match: same asyncio.run() in sync test pattern, same MockStore inline class, same FORG-03 subject)

**Test class + deferred import pattern** (test_decay.py lines 23–27):
```python
class TestDecay:
    def test_keep_score_values(self) -> None:
        """FORG-01: keep_score returns float in [0,1]; correct formula for known inputs."""
        from mnema.core.decay import keep_score  # noqa: PLC0415
        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415
```

**MockStore inline class pattern** (test_decay.py lines 116–122) — exact template for Hypothesis test's mock store:
```python
class _MockStore:
    @staticmethod
    async def live_records(user_id: str):  # type: ignore[return]
        yield protected_record
```

**asyncio.run() inside sync test pattern** (test_decay.py lines 123–129) — THE critical pattern for Hypothesis sync wrapper:
```python
async def _collect() -> list:  # type: ignore[return]
    results = []
    async for item in decay_pass(_MockStore(), "u1", now=now):
        results.append(item)
    return results

yielded = asyncio.run(_collect())
```

**Module-level imports pattern** (test_decay.py lines 17–21):
```python
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
```

---

### `tests/test_recall_packer.py` (new) — RECALL-03/04/05

**Analog:** `tests/test_decay.py` (same role: pure-sync logic test, no engine fixture needed)

**Plain sync test (no async fixture)** (test_decay.py lines 23–44) — packer tests are plain `def`, not `async def`, since `re_rank()` and `pack_records()` are D-12 pure-sync:
```python
class TestDecay:
    def test_keep_score_values(self) -> None:
        from mnema.core.decay import keep_score  # noqa: PLC0415
        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415
        now = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
        record_fresh = MemoryRecord(
            user_id="u1", session_id="s1",
            record_type=RecordType.PREFERENCE,
            content="test fresh",
            created_at=now, access_count=0, salience=0.5,
        )
```

---

### `tests/test_vault.py` (new) — CONS-09/TIER-03

**Analog:** `tests/test_consolidation.py` (role-match: integration test using engine fixture + consolidation pipeline)

**Engine fixture usage pattern** (conftest.py lines 28–55) — `engine` fixture provides `SqliteT1 + LocalFS + InProcessScheduler`. Phase 3 vault test needs an engine with an injected `LocalFSVault`. Extend conftest with a new `engine_with_vault` fixture following the same teardown pattern:
```python
@pytest.fixture
async def engine(tmp_path, stub_embedder):  # type: ignore[return]
    from mnema import MemoryEngine  # noqa: PLC0415
    from mnema.adapters.object_store.local_fs import LocalFS  # noqa: PLC0415
    from mnema.adapters.scheduler.in_process import InProcessScheduler  # noqa: PLC0415
    from mnema.adapters.vector_store.sqlite_t1 import SqliteT1  # noqa: PLC0415

    t1 = await SqliteT1.open(":memory:", dim=stub_embedder.dim)
    t0 = LocalFS(str(tmp_path / "t0"))
    scheduler = InProcessScheduler()
    await scheduler.start()
    eng = MemoryEngine(embedder=stub_embedder, t1=t1, t0=t0, scheduler=scheduler)
    yield eng
    await scheduler.shutdown()
```

---

### `tests/test_mcp_server.py` (new) — IFACE-02

**Analog:** `tests/test_sdk_interface.py` + RESEARCH.md FastMCP in-process client pattern (lines 922–950)

**Engine fixture dependency pattern** (conftest.py lines 28–55) — MCP server tests use the shared `engine` fixture; `mcp_server` fixture wraps it:
```python
@pytest.fixture
async def mcp_server(engine):  # engine is the existing conftest fixture
    from mnema.mcp.server import create_mcp_server
    return create_mcp_server(engine)
```

**Async test + async with pattern** (test_sdk_interface.py pattern — async def tests are collected by pytest-asyncio `asyncio_mode=auto`):
```python
async def test_mcp_tools_list(mcp_server):
    async with Client(mcp_server) as client:
        tools = await client.list_tools()
```
Note: `asyncio.run()` must NOT be called inside `async def` test bodies (RESEARCH.md Pitfall 6). Only the Hypothesis sync wrapper in `test_forgetting.py` uses `asyncio.run()`.

---

## Shared Patterns

### User-ID Scope Check (T-1-10)
**Source:** `src/mnema/core/engine.py` lines 228–235
**Apply to:** `engine.forget()` (must verify `record.user_id == user_id` before mutation), vault `promote()` (user_id from record), MCP tools (user_id explicit arg passes through to engine — no additional check in tool layer)
```python
record: Optional[MemoryRecord] = await self._t1.get(record_id)
if record is None:
    return None
if record.user_id != user_id:
    return None
```

### D-12 Pure-Sync Module Shape
**Source:** `src/mnema/core/decay.py` lines 1–19, 35–64
**Apply to:** `src/mnema/core/packer.py` (entire module), `re_rank()` function added to `recall.py`
```python
"""Module docstring — pure synchronous, no I/O.

D-12 compliance: this module contains ZERO I/O operations and ZERO async calls.
"""
# Module-level tunable constant with inline rationale:
CONSTANT: type = value
"""Rationale comment.
Half-life / formula derivation / tuning note.
"""
```

### D-10 Protocol Shape (no @runtime_checkable)
**Source:** `src/mnema/ports/scheduler.py` lines 1–35, `src/mnema/ports/record_store.py` lines 1–10
**Apply to:** `src/mnema/ports/vault.py`
```python
"""Port docstring — role description.

No @runtime_checkable — static checking only (D-10).
"""
from __future__ import annotations
from typing import Protocol

class ProtocolName(Protocol):
    """Contract description."""
    async def method(self, ...) -> ...:
        ...
```

### D-08 Structural Typing (no inheritance from Protocol)
**Source:** `src/mnema/adapters/object_store/local_fs.py` line 50, `src/mnema/adapters/vector_store/sqlite_t1.py` lines 1–18
**Apply to:** `LocalFSVault` — must NOT inherit from `VaultStore`; satisfies by structural typing

### Deferred Imports (import inside body)
**Source:** `src/mnema/core/engine.py` lines 94–96, `tests/conftest.py` lines 20–24
**Apply to:** All new files — imports of new modules go inside method/fixture bodies (not at module level) so pytest can collect before implementation exists
```python
from mnema.adapters.llm.stub import StubLLM  # noqa: PLC0415
```

### Path Traversal Validation
**Source:** `src/mnema/adapters/object_store/local_fs.py` lines 32–44
**Apply to:** `LocalFSVault._vault_path(user_id)` — validate `user_id` against `_VALID_SESSION_ID` pattern (same regex: `r"^[A-Za-z0-9_\-]+$"`)

### asyncio.run() Inside Sync Hypothesis Test
**Source:** `tests/test_decay.py` lines 123–129
**Apply to:** `tests/test_forgetting.py::test_protected_records_never_evicted` — the Hypothesis `@given`-decorated function MUST be `def` (sync), not `async def`. Call `asyncio.run(inner())` for async helpers inside it.

### Module-Level Constant Documentation
**Source:** `src/mnema/core/decay.py` lines 35–64
**Apply to:** `KEEP_THRESHOLD` in engine/consolidation, `VAULT_SALIENCE_THRESHOLD` in consolidation, tunable constants in packer.py — each gets a docstring with formula derivation and Phase 5 tuning note

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `src/mnema/mcp/server.py` | server/facade | request-response | No FastMCP server exists in the codebase. Use RESEARCH.md Pattern 5 (lines 657–738) — the `create_mcp_server(engine) -> FastMCP` closure-capture factory. FastMCP 3.4.2 `@mcp.tool` async decorator pattern. |

**What to copy for MCP server:** RESEARCH.md lines 667–738 contain the complete reference implementation including the factory function, all 5 tool definitions, `__main__` stdio entry point, and the `Client(server)` in-process test pattern. The only internal analog for engine-wiring style is `MemoryEngine.__init__()` — the MCP server similarly assembles collaborators, but its "wiring" is FastMCP tool registration rather than `WritePath`/`RecallPath` construction.

---

## Metadata

**Analog search scope:** `src/mnema/core/`, `src/mnema/ports/`, `src/mnema/adapters/`, `tests/`
**Files scanned:** 16 source files read in full
**Pattern extraction date:** 2026-06-14
