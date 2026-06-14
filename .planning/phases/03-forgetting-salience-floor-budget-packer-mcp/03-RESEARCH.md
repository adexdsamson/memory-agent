# Phase 3: Forgetting, Salience Floor, Budget Packer & MCP - Research

**Researched:** 2026-06-14
**Domain:** Eviction/forgetting pipeline, token-budget packing, T2 vault adapter, FastMCP server surface
**Confidence:** HIGH (all four capability areas verified against current sources)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- D3-01: Eviction compares `keep_score` against tunable `KEEP_THRESHOLD` (~0.3). Evict iff `keep_score < KEEP_THRESHOLD AND not protected`.
- D3-02: Eviction target is the T0/LocalFS cold store — set `valid_until`, remove vector, write cold-store record. No hard-delete anywhere.
- D3-03 (FORG-03, load-bearing): Protected records skipped before any score math — proven by a **Hypothesis property test** (`hypothesis` added as dev dep).
- D3-04: Append-only JSONL eviction audit: `{record_id, user_id, keep_score, evicted_at, reason}`.
- D3-05: Re-rank score = `rank_score * salience * recency_decay` (pure sync, reuses decay recency term from D-12).
- D3-06: Token counting via pluggable counter with portable default approximation (tiktoken-style).
- D3-07 (RECALL-05, load-bearing): Two-pass packer — Pass 1 reserves critical set; Pass 2 fills remainder by re-rank score. Adversarial test required.
- D3-08: Reserved "active-constraint" set = `protected UNION (record_type == FACT, live)`.
- D3-09: New `VaultStore` Protocol — the 6th adapter axis (LLM / Embedding / Object-T0 / T1 / Vault-T2 / Scheduler).
- D3-10: LocalFS vault writes human-readable, git-versioned per-user markdown user-model file, sectioned by `record_type`.
- D3-11: Promotion during consolidation: confirmed (non-provisional), above salience threshold.
- D3-12: Vault dedup/merge by entity (subject+predicate); MVP: dedup by summary/content.
- D3-13: **fastmcp 3.x** — thin wrapper exposing 5 verbs as MCP tools delegating to `MemoryEngine`.
- D3-14: `user_id` is an explicit, required MCP tool argument.
- D3-15: stdio transport for MVP; server constructed over injected `MemoryEngine`.
- D3-16: Tests use FastMCP in-process client — hermetic assertions.

### Carried-Forward Locked Decisions
D-11 async verbs/ports; D-12 sans-I/O pure logic; D-02/D-03 user_id hard isolation; D-07/D-08/D-10 segregated Protocols, static-checked; content-driven `protected` rule; CONS-08 supersession guard.

### Claude's Discretion
- Tunable constants: `KEEP_THRESHOLD` value (around 0.3), salience threshold for vault promotion.
- MVP depth tradeoffs within the requirement guarantees.
- Exact vault stability rule for D3-11.

### Deferred Ideas (OUT OF SCOPE)
- Real cloud Vault/object backends (OSS, git remote), OpenAI/Voyage/Qwen provider adapters → Phase 4.
- Hybrid retrieval (BM25 + graph + RRF) — HYBRID-01/02/03 → later phase.
- HTTP/SSE MCP transport and auth beyond explicit user_id → post-MVP.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FORG-02 | Records below keep threshold and not protected are evicted to cold storage | `decay_pass` yields (record, keep_score); eviction checks `< KEEP_THRESHOLD` and calls `t0.archive()` + `t1.update(valid_until=...)` + `t1.delete_vector()`. All three methods exist and are verified. |
| FORG-03 | Protected records are skipped before any score math — proven by invariant/property test | `decay_pass` never yields protected records (structural guarantee). Hypothesis `@given` + `@composite` strategy over generated MemoryRecord sets. Sync `@given` wrapper calls `asyncio.run()` internally. |
| FORG-04 | Eviction is recoverable and auditable — append-only JSONL audit | `LocalFS.archive()` stub exists; JSONL audit log separate from the main cold store. Path: `{base_dir}/eviction_audit.jsonl`. |
| RECALL-03 | Results re-ranked by relevance × salience × recency | Pure-sync re-rank function over `list[MemoryRecord]` with similarity scores. Reuses `recency_decay(record, now)` from `decay.py`. |
| RECALL-04 | Packs record summaries under a caller-supplied token budget | `TokenCounter` Protocol + default tiktoken-backed adapter + byte-length fallback. Packs `record.summary` fields. |
| RECALL-05 | Two-pass budget packer reserves protected/active-constraint slots first | Pass 1 collects critical set (protected OR FACT-type), fits under budget; Pass 2 fills remaining budget by re-rank score. Adversarial test: large off-topic history cannot displace a critical fact. |
| CONS-09 | Stable records promoted into T2 canonical vault | Promotion hook at end of `ConsolidationPipeline.run()`: confirmed (non-provisional), salience >= threshold → `vault.promote(record)`. |
| TIER-03 | T2 canonical vault holds merged, deduped, human-readable, git-versioned user model | `VaultStore` Protocol + `LocalFSVault` adapter writing `{base_dir}/{user_id}.md` — markdown, sectioned by record_type, deduped by content. |
| IFACE-02 | MCP server exposes the same operations as MCP tools (thin wrapper over SDK) | FastMCP 3.4.2 `Client(server)` in-process test; lifespan injects `MemoryEngine`; 5 `@mcp.tool` async functions. |
</phase_requirements>

---

## Summary

Phase 3 layers four capabilities over the existing local core. Eviction is the most straightforward — `decay_pass` already yields (record, keep_score) pairs filtered of protected records; the eviction pass simply checks the score threshold and calls the three already-implemented methods (`update(valid_until=...)`, `delete_vector()`, `archive()`). The vector DELETE path for sqlite-vec vec0 tables is **confirmed working** at the `DELETE FROM vec_t1 WHERE record_id = ?` syntax.

Budget packing is pure-sync algorithmic work with no new I/O. tiktoken 0.13.0 ships a **pre-built binary wheel for Python 3.12 on Windows** (confirmed via `pip download`), so there is no Rust toolchain requirement for this machine. The fallback estimator (byte count / 4) is adequate for the MVP and is accurate enough for short `summary` fields.

The Hypothesis property test for FORG-03 is the most nuanced piece. Hypothesis does NOT natively run `async def` test functions via `@given`. The established MNEMA pattern (already present in `test_decay.py`) is to write the Hypothesis-decorated function as a **sync test that calls `asyncio.run()`** on its inner async helper — this is clean, compatible with `asyncio_mode=auto`, and already proven in the existing codebase.

FastMCP 3.4.2 (current PyPI) supports in-memory `Client(server)` testing with no transport overhead, async tools with Pydantic types, and lifespan-based dependency injection. The cleanest injection pattern for an external `MemoryEngine` object is either (a) **closure capture** (define tool functions inside a factory function that closes over the engine), or (b) **lifespan** (yield the engine in `ctx.lifespan_context`). Both patterns are verified in FastMCP docs.

**Primary recommendation:** Implement the four capabilities in this dependency order: (1) eviction + JSONL audit, (2) re-rank + two-pass packer, (3) VaultStore Protocol + LocalFSVault adapter + promotion hook, (4) MCP server. The MCP server is the integration surface that assembles everything, so it goes last.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Eviction score check (`KEEP_THRESHOLD`) | Core / Engine | — | Pure logic: reads keep_score output, decides eviction. No I/O in the decision itself. |
| Set `valid_until` on evicted record | T1 RecordStore | — | Persistence mutation; uses existing `update()` method. |
| Remove vector from index | T1 VectorIndex | — | Persistence mutation; uses existing `delete_vector()` method. |
| Write cold-store archive record | T0 ObjectStore | — | `LocalFS.archive()` stub already exists; complete it. |
| Write eviction audit JSONL | T0 ObjectStore | — | Co-located with LocalFS; can be a separate `append_audit()` or write inline. |
| Re-rank scoring (relevance × salience × recency) | Core / Recall | — | Pure sync computation over already-fetched records; no new I/O. |
| Token counting | Core / Recall | Pluggable adapter | Default tiktoken-backed; fallback byte/4 estimate. |
| Two-pass budget packing | Core / Recall | — | Pure sync; operates on list[MemoryRecord] already in memory. |
| T2 vault write (markdown) | VaultStore adapter | — | New 6th adapter axis. LocalFSVault writes `{user_id}.md`. |
| T2 vault promotion (during consolidation) | Core / Consolidation | VaultStore adapter | Hook at end of `ConsolidationPipeline.run()`; delegates write to VaultStore. |
| MCP tool surface | MCP server module | Core / Engine | Thin delegation; no business logic in the tool layer. |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastmcp | 3.4.2 | MCP server framework | Stack-mandated. 3.4.2 is current PyPI release. `Client(server)` in-process testing, async tools, lifespan injection. |
| hypothesis | 6.155.2 | Property-based testing (dev dep) | Not yet in pyproject.toml — must add. 6.155.2 is current PyPI release. Required for FORG-03 invariant proof. |
| tiktoken | 0.13.0 | Token counting for budget packer | Already installed on this machine. Binary wheel available for Python 3.12 Windows (cp312-win_amd64). |

[VERIFIED: pip index versions — fastmcp 3.4.2, hypothesis 6.155.2, tiktoken 0.13.0 — all current as of 2026-06-14]

### Supporting (already in pyproject.toml)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| aiosqlite | >=0.22 | Async SQLite (T1 adapter) | Eviction uses `delete_vector()` + `update(valid_until=...)` on existing connection. |
| sqlite-vec | >=0.1.9 | Vector index | `DELETE FROM vec_t1 WHERE record_id = ?` verified working. 0.1.9 fixes the DELETE bug. |
| pydantic | >=2.12 | Schema + FastMCP tool arg validation | FastMCP uses Pydantic for tool schema. Tool args are plain typed Python functions; no extra Pydantic models needed unless complex args. |
| numpy | >=2.4 | Vector math in re-rank | `recency_decay()` reuses `math.exp()` from `decay.py` — numpy not needed for packer. numpy is there if needed. |

### pyproject.toml Changes

```toml
# Add to [project.optional-dependencies] dev:
"hypothesis>=6.155",
# Add to [project.dependencies]:
"fastmcp>=3.4.2,<4",
"tiktoken>=0.13",
```

**Note:** `tiktoken` goes in runtime deps (not dev) because the `TokenCounter` default adapter uses it at engine runtime. `hypothesis` is dev-only.

**Installation:**

```bash
uv add fastmcp tiktoken
uv add --dev hypothesis
```

**Version verification:** [VERIFIED: 2026-06-14]
- fastmcp 3.4.2 — `pip index versions fastmcp` confirmed current
- hypothesis 6.155.2 — `pip index versions hypothesis` confirmed current
- tiktoken 0.13.0 — installed on machine; `pip download` confirmed cp312-win_amd64 wheel available

---

## Architecture Patterns

### System Architecture Diagram

```
    consolidate() call
          |
          v
    ConsolidationPipeline.run()
          |
          +---> (existing: extract, reconcile, entity-resolve, supersede)
          |
          +---> decay_pass(record_store, user_id)
          |           |
          |           v
          |     yields (record, keep_score)  [protected records NEVER yielded]
          |           |
          |           v
          |     EvictionPass
          |           |
          |     keep_score < KEEP_THRESHOLD?
          |           |          |
          |          YES         NO → skip
          |           |
          |     1. update(valid_until=now)          → T1 RecordStore
          |     2. delete_vector(record_id)          → T1 VectorIndex
          |     3. t0.archive(record)                → T0 ObjectStore
          |     4. append_audit(eviction_entry)      → JSONL file
          |
          +---> VaultPromotionPass
                      |
                foreach confirmed record with salience >= VAULT_THRESHOLD
                      |
                      v
                vault.promote(record)                → VaultStore (T2)
                                                          LocalFSVault
                                                          {user_id}.md (markdown)

    recall() call
          |
          v
    RecallPath.execute() [Phase 1: dense KNN + buffer]
          |
          +---> re_rank(records, similarity_scores, now)   [pure sync, D-12]
          |           |
          |     score_i = similarity_i * record.salience * exp(-lambda * age_days_i)
          |     sorted descending
          |
          +---> BudgetPacker.pack(ranked, budget, token_counter)
                      |
                 Pass 1: collect CRITICAL_SET
                         (protected=True OR record_type=FACT, valid_until IS NULL)
                         fit critical records under budget
                         |
                 Pass 2: fill remaining_budget from ranked (skip already-included)
                         |
                         v
                 list[MemoryRecord]  (within token budget, critical facts always present)

    MCP server (stdio transport)
          |
    Client → FastMCP tools: remember / recall / forget / consolidate / expand
          |
          v
    MemoryEngine (injected via lifespan closure)
          |
          v
    Same Python functions as SDK [IFACE-02 thesis]
```

### Recommended Project Structure (additions only)

```
src/mnema/
├── core/
│   ├── decay.py           # existing — FORG-01 keep_score + decay_pass
│   ├── recall.py          # existing — Phase 3 adds re_rank() + BudgetPacker
│   ├── packer.py          # NEW: BudgetPacker + TokenCounter Protocol + default adapter
│   └── engine.py          # existing — forget() stub filled; consolidate() gains vault + eviction hooks
├── ports/
│   └── vault.py           # NEW: VaultStore Protocol (6th axis)
├── adapters/
│   ├── object_store/
│   │   └── local_fs.py    # existing — archive() stub completed; add append_audit()
│   └── vault/
│       └── local_fs_vault.py  # NEW: LocalFSVault adapter
└── mcp/
    └── server.py          # NEW: FastMCP server module
tests/
├── test_forgetting.py     # NEW: eviction tests (FORG-02/04 + FORG-03 Hypothesis)
├── test_recall_packer.py  # NEW: re-rank + budget packer tests (RECALL-03/04/05)
├── test_vault.py          # NEW: vault promotion + LocalFSVault tests (CONS-09/TIER-03)
└── test_mcp_server.py     # NEW: MCP surface tests (IFACE-02)
```

---

### Pattern 1: Eviction Pass (FORG-02/03/04)

The `decay_pass` async generator is already fully implemented. The eviction pass consumes it:

```python
# src/mnema/core/engine.py  (inside forget() OR a standalone evict_pass() helper)
# Source: existing decay.py + verified sqlite-vec DELETE syntax
from mnema.core.decay import decay_pass, LAMBDA_DECAY
from datetime import datetime, timezone
import json

KEEP_THRESHOLD: float = 0.3
"""Records with keep_score < KEEP_THRESHOLD are evicted to cold storage.
Tune against Phase 5 demo evaluation. 0.3 is the Claude's-discretion starting point.
"""

async def _run_eviction_pass(
    record_store,      # RecordStore
    vector_index,      # VectorIndex
    t0,                # ObjectStorePort
    audit_path: str,   # path to eviction_audit.jsonl
    user_id: str,
    now: datetime | None = None,
) -> int:
    """Evict records below KEEP_THRESHOLD; return eviction count."""
    if now is None:
        now = datetime.now(timezone.utc)
    evicted = 0
    async for record, score in decay_pass(record_store, user_id, now=now):
        if score >= KEEP_THRESHOLD:
            continue
        # 1. Retire from live index (set valid_until)
        await record_store.update(record.id, valid_until=now)
        # 2. Remove vector from KNN index
        await vector_index.delete_vector(record.id)
        # 3. Write to cold store
        await t0.archive(record)
        # 4. Append to audit JSONL
        entry = {
            "record_id": record.id,
            "user_id": record.user_id,
            "keep_score": score,
            "evicted_at": now.isoformat(),
            "reason": f"keep_score={score:.4f} < KEEP_THRESHOLD={KEEP_THRESHOLD}",
        }
        with open(audit_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        evicted += 1
    return evicted
```

**Critical detail:** The FORG-03 guarantee is structural — `decay_pass` never yields a protected record. The eviction pass does NOT need a `not record.protected` guard because protected records never reach it. The CONS-08 gate (no auto-supersession) and the FORG-03 gate (no eviction) are both handled at the `decay_pass` level.

**sqlite-vec DELETE verified:**

```python
# [VERIFIED: direct Python test on sqlite-vec 0.1.9]
# Standard SQL DELETE from a vec0 virtual table works by primary key:
await db.execute("DELETE FROM vec_t1 WHERE record_id = ?", (record_id,))
# SqliteT1.delete_vector() already implements this correctly.
```

---

### Pattern 2: Hypothesis Property Test for FORG-03

**Key insight:** Hypothesis `@given` does NOT support `async def` test bodies. The clean solution (already established in `test_decay.py`) is a **sync test that wraps async helpers with `asyncio.run()`**.

```python
# tests/test_forgetting.py
# Source: hypothesis docs + existing test_decay.py pattern

import asyncio
from datetime import datetime, timezone
from hypothesis import given, settings
import hypothesis.strategies as st
from mnema.core.schema import MemoryRecord, RecordType

# Strategy for generating arbitrary MemoryRecord sets
@st.composite
def memory_records_strategy(draw):
    """Generate a list of MemoryRecord objects with arbitrary protected flags."""
    n = draw(st.integers(min_value=1, max_value=20))
    records = []
    for _ in range(n):
        protected = draw(st.booleans())
        salience = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
        records.append(
            MemoryRecord(
                user_id="u1",
                session_id="s1",
                record_type=draw(st.sampled_from(list(RecordType))),
                content=draw(st.text(min_size=1, max_size=50)),
                protected=protected,
                salience=salience,
            )
        )
    return records

@given(memory_records_strategy())
@settings(max_examples=100)
def test_protected_records_never_evicted(records):
    """FORG-03: For any set of records, no protected record is ever evicted.

    This is an invariant test, not an example test.
    The eviction pass consumes decay_pass, which structurally never yields
    protected records — so no protected record can ever appear in eviction output.
    """
    from mnema.core.decay import decay_pass
    from mnema.core.engine import KEEP_THRESHOLD

    # Use a static mock store
    class MockStore:
        def __init__(self, recs):
            self._recs = recs
        async def live_records(self, user_id: str):
            for r in self._recs:
                yield r

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    async def _collect_eviction_candidates():
        eviction_candidates = []
        async for record, score in decay_pass(MockStore(records), "u1", now=now):
            if score < KEEP_THRESHOLD:
                eviction_candidates.append(record)
        return eviction_candidates

    eviction_candidates = asyncio.run(_collect_eviction_candidates())

    # INVARIANT: no protected record in eviction_candidates
    protected_evicted = [r for r in eviction_candidates if r.protected]
    assert protected_evicted == [], (
        f"FORG-03 VIOLATION: protected records appeared in eviction candidates: "
        f"{[r.id for r in protected_evicted]}"
    )
```

**Why this works:**
- `@given` decorates a sync function — no async/Hypothesis conflict.
- `asyncio.run()` creates a fresh event loop per Hypothesis example — safe because `asyncio_mode=auto` only affects pytest-collected async tests, not internal `asyncio.run()` calls.
- Hypothesis shrinks failing examples automatically (e.g., finds the minimal protected record set that triggers the violation).

---

### Pattern 3: Re-Rank and Two-Pass Budget Packer (RECALL-03/04/05)

**Re-rank function (pure sync, D-12):**

```python
# src/mnema/core/recall.py  (additions)
# Source: D3-05 decision + decay.py recency term

import math
from datetime import datetime, timezone

def re_rank(
    records: list[MemoryRecord],
    similarity_scores: dict[str, float],  # record_id → raw vector similarity
    now: datetime | None = None,
) -> list[MemoryRecord]:
    """Re-rank records by relevance * salience * recency_decay.

    Pure sync per D-12. similarity_scores for buffer-synthesized records default to 0.5.
    Returns records sorted by descending composite score.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    def composite(r: MemoryRecord) -> float:
        ref = r.last_accessed or r.created_at
        age_days = max(0.0, (now - ref).total_seconds() / 86400.0)
        recency = math.exp(-LAMBDA_DECAY * age_days)  # reuse from decay.py
        sim = similarity_scores.get(r.id, 0.5)
        return sim * r.salience * recency

    return sorted(records, key=composite, reverse=True)
```

**Token counter protocol + adapters (pure sync, D-12):**

```python
# src/mnema/core/packer.py
from typing import Protocol, runtime_checkable

class TokenCounter(Protocol):
    """Pluggable token counter for the budget packer (D3-06).
    Must be synchronous (D-12 — pure logic, no I/O).
    """
    def count(self, text: str) -> int:
        """Return the token count for text."""
        ...

class TiktokenCounter:
    """Default token counter backed by tiktoken cl100k_base.
    Pre-built binary wheel available for Python 3.12 Windows (verified 2026-06-14).
    """
    def __init__(self) -> None:
        import tiktoken  # noqa: PLC0415
        self._enc = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        return len(self._enc.encode(text))

class ByteLengthCounter:
    """Portable fallback: estimate tokens as len(text.encode()) // 4.
    Accurate for English short summaries (verified: 9-token sentence gives
    approx=9 via this heuristic). No binary dependencies.
    """
    def count(self, text: str) -> int:
        return max(1, len(text.encode("utf-8")) // 4)
```

**Two-pass packer (D3-07):**

```python
# src/mnema/core/packer.py  (continued)
from mnema.core.schema import MemoryRecord, RecordType

def pack_records(
    ranked: list[MemoryRecord],
    budget: int,
    counter: TokenCounter,
) -> list[MemoryRecord]:
    """Two-pass budget packer (D3-07, RECALL-05).

    Pass 1: Reserve slots for CRITICAL_SET = protected OR (FACT-type AND live).
            These records are always included (up to budget). If the critical set
            alone exceeds budget, truncate it at the budget limit (critical set
            is already sorted by importance: protected first, then FACT).
    Pass 2: Fill remaining budget by re-rank score (descending).

    Returns list of records whose summaries fit under `budget` tokens.
    """
    # Partition into critical and non-critical
    critical = [r for r in ranked
                if r.protected or (r.record_type == RecordType.FACT and r.valid_until is None)]
    non_critical = [r for r in ranked if r not in set(critical)]

    packed: list[MemoryRecord] = []
    used = 0

    # Pass 1: reserved slots
    for rec in critical:
        cost = counter.count(rec.summary or rec.content[:80])
        if used + cost <= budget:
            packed.append(rec)
            used += cost

    critical_ids = {r.id for r in packed}

    # Pass 2: fill remaining by score
    for rec in non_critical:
        if rec.id in critical_ids:
            continue
        cost = counter.count(rec.summary or rec.content[:80])
        if used + cost > budget:
            continue  # skip, don't stop — a later shorter record might fit
        packed.append(rec)
        used += cost

    return packed
```

**Adversarial test (D3-07):**

```python
# tests/test_recall_packer.py
def test_critical_fact_survives_large_off_topic_history():
    """RECALL-05: A protected/critical fact always appears in packed output
    even when the bulk of the history is large off-topic records."""
    from mnema.core.packer import pack_records, ByteLengthCounter
    from mnema.core.schema import MemoryRecord, RecordType

    # One critical record: protected allergy fact
    allergy = MemoryRecord(
        user_id="u1", session_id="s1",
        record_type=RecordType.FACT,
        content="allergy: peanuts", summary="allergy: peanuts",
        protected=True, salience=1.0,
    )
    # 100 large off-topic records that would push allergy out in a naive packer
    filler = [
        MemoryRecord(
            user_id="u1", session_id="s1",
            record_type=RecordType.PREFERENCE,
            content=f"filler record {i}", summary=f"filler record {i}" * 10,
            salience=0.9,  # high salience but NOT protected
        )
        for i in range(100)
    ]
    # ranked: filler first (they have higher raw similarity in this test)
    ranked = filler + [allergy]

    packed = pack_records(ranked, budget=200, counter=ByteLengthCounter())
    packed_ids = {r.id for r in packed}
    assert allergy.id in packed_ids, (
        "RECALL-05 VIOLATION: protected allergy fact was pushed out of budget by off-topic history"
    )
```

---

### Pattern 4: VaultStore Protocol and LocalFSVault (CONS-09/TIER-03)

**VaultStore Protocol (6th axis):**

```python
# src/mnema/ports/vault.py
from typing import Protocol
from mnema.core.schema import MemoryRecord

class VaultStore(Protocol):
    """Contract for T2 canonical vault — the 6th adapter axis (D3-09).

    No @runtime_checkable — static checking only (D-10).
    T2 holds the merged, deduped, human-readable, git-versioned user model.
    """

    async def promote(self, record: MemoryRecord) -> None:
        """Promote a confirmed, stable record into the T2 canonical vault.

        Implementations must:
        - Dedup by content/summary before writing (D3-12).
        - Write in a human-readable, git-versioned format (TIER-03).
        - Be idempotent — re-promoting the same record is safe.
        """
        ...

    async def get_user_model(self, user_id: str) -> str:
        """Return the current T2 user model as a string (for recall/expand)."""
        ...
```

**LocalFSVault adapter:**

```python
# src/mnema/adapters/vault/local_fs_vault.py
from pathlib import Path
from mnema.core.schema import MemoryRecord, RecordType

VAULT_SECTION_ORDER = [
    RecordType.FACT,
    RecordType.PREFERENCE,
    RecordType.PROCEDURE,
    RecordType.EVENT,
]

class LocalFSVault:
    """T2 canonical vault — human-readable per-user markdown file.

    Writes {base_dir}/{user_id}.md — one file per user, sectioned by record_type.
    Each fact/preference/etc. is a markdown bullet point.
    Dedup: same summary → skip (D3-12 MVP dedup).
    Git-versioned: the files are committed to the repo; no git commands issued here.
    """

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def _vault_path(self, user_id: str) -> Path:
        return self._base / f"{user_id}.md"

    async def promote(self, record: MemoryRecord) -> None:
        """Promote record into the user model markdown file."""
        path = self._vault_path(record.user_id)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""

        # Dedup: if summary already appears in file, skip (D3-12)
        summary = (record.summary or record.content[:80]).strip()
        if summary in existing:
            return

        # Build updated content by parsing existing sections
        # For MVP: append to appropriate section header
        section_header = f"## {record.record_type.value.capitalize()}s"
        bullet = f"- {summary}\n"

        if section_header in existing:
            # Insert after section header
            updated = existing.replace(
                section_header + "\n",
                section_header + "\n" + bullet,
            )
        else:
            # Append new section
            updated = existing + f"\n{section_header}\n{bullet}"

        path.write_text(updated.lstrip(), encoding="utf-8")

    async def get_user_model(self, user_id: str) -> str:
        path = self._vault_path(user_id)
        return path.read_text(encoding="utf-8") if path.exists() else ""
```

**Vault promotion hook in ConsolidationPipeline:**

```python
# src/mnema/core/consolidation.py  (addition to run())
# After decay_pass, call vault promotion for records above threshold

VAULT_SALIENCE_THRESHOLD: float = 0.7
"""Records confirmed + salience >= this value are promoted to T2 vault (D3-11)."""

# In ConsolidationPipeline.run(), after decay_pass loop:
if self._vault is not None:
    async for record in self._record_store.live_records(uid):
        if (
            not record.provisional
            and record.salience >= VAULT_SALIENCE_THRESHOLD
            and record.valid_until is None
        ):
            await self._vault.promote(record)
```

---

### Pattern 5: FastMCP MCP Server (IFACE-02)

**Server construction over an injected MemoryEngine:**

FastMCP 3.x supports two clean patterns for injecting an external object:
1. **Closure capture** (recommended for MNEMA — engine already exists before server creation)
2. **Lifespan** (useful when the engine must be created during server startup)

Since `MemoryEngine` is constructed outside the MCP server and passed in, closure capture is the cleaner pattern:

```python
# src/mnema/mcp/server.py
# Source: gofastmcp.com docs verified 2026-06-14

from fastmcp import FastMCP

def create_mcp_server(engine) -> FastMCP:  # engine: MemoryEngine
    """Create a FastMCP server wrapping the provided MemoryEngine.

    The server is a thin layer — all business logic lives in engine.
    user_id is an explicit required arg on every tool (D3-14).
    """
    mcp = FastMCP("mnema")

    @mcp.tool
    async def remember(
        content: str,
        user_id: str,
        session_id: str,
        type_hint: str | None = None,
        durable: bool = False,
    ) -> str:
        """Store an utterance in memory."""
        return await engine.remember(
            content, user_id=user_id, session_id=session_id,
            type_hint=type_hint, durable=durable,
        )

    @mcp.tool
    async def recall(
        query: str,
        user_id: str,
        k: int = 10,
        budget: int = 2000,
    ) -> list[dict]:
        """Retrieve relevant memories within a token budget."""
        records = await engine.recall(query, user_id=user_id, k=k, budget=budget)
        return [{"id": r.id, "summary": r.summary, "record_type": r.record_type.value,
                 "salience": r.salience, "protected": r.protected}
                for r in records]

    @mcp.tool
    async def forget(record_id: str, user_id: str, reason: str = "") -> None:
        """Evict a record (mark for forgetting)."""
        await engine.forget(record_id, user_id=user_id, reason=reason)

    @mcp.tool
    async def consolidate(user_id: str) -> str:
        """Run offline consolidation for a user."""
        await engine.consolidate()
        return "consolidated"

    @mcp.tool
    async def expand(record_id: str, user_id: str) -> dict | None:
        """Return the verbatim T0 turn behind a record."""
        turn = await engine.expand(record_id, user_id=user_id)
        if turn is None:
            return None
        return {"content": turn.content, "role": turn.role,
                "created_at": turn.created_at.isoformat()}

    return mcp


if __name__ == "__main__":
    # Stdio entry point — construct engine from config, then serve
    from mnema import MemoryEngine
    # ... adapter construction from config omitted for clarity ...
    # engine = MemoryEngine(...)
    # mcp_server = create_mcp_server(engine)
    # mcp_server.run()  # Uses stdio transport by default
    pass
```

**In-process hermetic tests (D3-16):**

```python
# tests/test_mcp_server.py
# Source: gofastmcp.com in-memory client pattern verified 2026-06-14

import pytest
from fastmcp import Client

@pytest.fixture
def mcp_server(engine):  # engine is the existing conftest fixture
    from mnema.mcp.server import create_mcp_server
    return create_mcp_server(engine)

async def test_mcp_tools_list(mcp_server):
    """IFACE-02: MCP server exposes the five verbs as tools."""
    async with Client(mcp_server) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert {"remember", "recall", "forget", "consolidate", "expand"} <= tool_names

async def test_mcp_remember_recall_roundtrip(mcp_server):
    """IFACE-02: remember/recall roundtrip via MCP tool surface."""
    async with Client(mcp_server) as client:
        await client.call_tool("remember", {
            "content": "I am allergic to peanuts",
            "user_id": "u1",
            "session_id": "s1",
            "type_hint": "fact",
        })
        result = await client.call_tool("recall", {
            "query": "food allergies",
            "user_id": "u1",
        })
        assert result.data is not None
        # At least one record should mention peanuts
        summaries = [r.get("summary", "") for r in result.data]
        assert any("peanut" in s.lower() for s in summaries), (
            f"Peanut allergy not found in recall results: {summaries}"
        )
```

**Stdio run entry point:**

```python
# mcp_server.run()  — FastMCP 3.x uses stdio by default
# Equivalent to: await mcp_server.run_async("stdio")
# For tests: Client(server) uses in-memory transport — no subprocess
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token counting | Custom tokenizer / regex word-count | `tiktoken.get_encoding("cl100k_base")` + `ByteLengthCounter` fallback | BPE tokenization has many edge cases (Unicode, special tokens, whitespace). tiktoken ships pre-built wheels; byte/4 fallback is accurate for short summaries. |
| MCP protocol framing (JSON-RPC + schema gen) | Custom MCP transport | FastMCP 3.4.2 | FastMCP handles protocol framing, Pydantic schema generation, stdio transport loop, and test Client. Implementing MCP JSON-RPC manually is hundreds of lines with no upside. |
| Property-based test case generation | Manual parametrize exhaustion | `hypothesis` `@given` + `@composite` | Hypothesis finds adversarial shrunk counterexamples automatically. Manual parametrize misses corner cases (empty set, all-protected, salience=0.0). |
| Markdown parsing to update vault sections | Custom regex section parser | Simple string `replace()` + `in` check for MVP | The D3-12 MVP only needs dedup-by-content and section append. Full markdown parsing is unnecessary until Phase 5 refines the vault format. |
| Vector DELETE from custom B-tree | Custom eviction index | `DELETE FROM vec_t1 WHERE record_id = ?` | sqlite-vec 0.1.9 DELETE is standard SQL; verified working in direct test. |

**Key insight:** The eviction, packing, and vault operations are all thin wrappers over already-implemented building blocks (decay_pass, delete_vector, archive, update). The main risk is building complexity where simplicity suffices.

---

## Common Pitfalls

### Pitfall 1: `@given` Applied to `async def` Test Function

**What goes wrong:** Hypothesis raises a `HealthCheck` failure or `InvalidArgument` error because `@given` wraps the function, which returns a coroutine instead of None.

**Why it happens:** Hypothesis does not natively know how to execute coroutines. The `asyncio_mode=auto` setting in pytest affects pytest-collected tests but not Hypothesis's internal executor.

**How to avoid:** Write the property test as a **sync function** (`def test_...`, not `async def test_...`). Call `asyncio.run(inner_async_helper())` inside the sync test body. This is already the established pattern in `test_decay.py` line 129 (`yielded = asyncio.run(_collect())`).

**Warning signs:** `hypothesis.errors.InvalidArgument: test_protected_records_never_evicted is an async function.`

---

### Pitfall 2: Protected Flag Not Checked in Eviction — Defense-in-Depth

**What goes wrong:** A developer adds a `not record.protected` guard inside the eviction pass, then `decay_pass` changes to yield protected records by mistake in a future refactor — the guard is the only defense.

**Why it happens:** The FORG-03 guarantee is structural: `decay_pass` is the only gate. If a reviewer adds `and not record.protected` in the eviction pass as "defense in depth," future refactors may remove it as "redundant."

**How to avoid:** The eviction pass has NO `not record.protected` guard. The property test is the proof. The code comment explicitly states: "protected records cannot reach this point — decay_pass structural guarantee, proven by Hypothesis test."

---

### Pitfall 3: Budget Packer Stops on First Oversized Record

**What goes wrong:** A greedy packer exits the loop when `used + cost > budget` instead of continuing to look for shorter records that fit.

**Why it happens:** Intuitive "first fit decreasing" assumes records are sorted descending by size, which they are NOT (they are sorted by relevance score).

**How to avoid:** Use `continue` (skip the current oversized record) not `break` (stop the loop) in Pass 2. Short summaries that fit in the remaining budget may appear after large ones in the relevance-sorted list. The adversarial test (large filler + protected allergy) catches this.

---

### Pitfall 4: Vault Write Race Condition with Concurrent Consolidations

**What goes wrong:** Two concurrent consolidation runs both read the vault file, both check "summary not in existing", both decide to write, and one overwrites the other's write.

**Why it happens:** `LocalFSVault` does read-then-write without a file lock.

**How to avoid:** The MVP spec says "runs identically on a laptop" with a single-process scheduler. Concurrent consolidation runs are not possible with `InProcessScheduler`. The `asyncio` event loop is single-threaded. The `asyncio.Queue` drain is synchronous and non-concurrent. Flag this as a Phase 4 concern when moving to cloud (Function Compute / multi-process).

---

### Pitfall 5: Vault Promotion Runs on Every Record on Every Consolidation

**What goes wrong:** `live_records()` iterates all live records every consolidation run, and `promote()` is called on every qualifying record even if it was already promoted.

**Why it happens:** There is no "promoted" flag on `MemoryRecord`.

**How to avoid:** `LocalFSVault.promote()` is idempotent by design — it checks `summary in existing` before writing. The dedup check is cheap (in-memory string search on the markdown file). For large user models this could become slow, but at MNEMA's working-set scale (hundreds to low thousands of live records) it is acceptable. Flag for Phase 4 if profiling shows contention.

---

### Pitfall 6: FastMCP `Client(server)` and `asyncio_mode=auto` Double-Loop

**What goes wrong:** `async with Client(server)` inside an `async def test_...` function raises `RuntimeError: This event loop is already running` when `asyncio_mode=auto` is active.

**Why it happens:** FastMCP's in-memory transport runs in the current event loop — which is fine. The error does NOT occur with `Client(server)` because FastMCP uses the caller's event loop, not a new one. The error only occurs if you call `asyncio.run()` inside an `async def` test.

**How to avoid:** In async pytest tests, use `async with Client(server) as client:` directly. Only use `asyncio.run()` inside **sync** test functions (the Hypothesis property tests). The existing conftest pattern (`asyncio_mode=auto`) works correctly with FastMCP's in-process client.

---

### Pitfall 7: sqlite-vec `delete_vector` Must Be Committed

**What goes wrong:** `DELETE FROM vec_t1 WHERE record_id = ?` succeeds but the change is not visible to subsequent queries because `aiosqlite` is in autocommit mode by default and the connection's WAL checkpoint hasn't propagated.

**Why it happens:** The existing `SqliteT1.delete_vector()` already calls `await self._db.commit()` after the DELETE — see the implementation. This pitfall is already avoided, but it is easy to miss when writing new eviction code that directly accesses `self._db`.

**How to avoid:** Always call `await self._db.commit()` after mutations. The existing `SqliteT1.delete_vector()` implementation is correct — use it; don't write raw `DELETE` statements in engine code.

---

### Pitfall 8: Eviction Before Vault Promotion

**What goes wrong:** The eviction pass runs first during consolidation and evicts a record that the vault promotion pass would have promoted. The vault never receives the record.

**Why it happens:** If `_run_eviction_pass()` and the vault promotion pass are both called from `ConsolidationPipeline.run()`, their order matters.

**How to avoid:** Run vault promotion **before** eviction in `ConsolidationPipeline.run()`. The order should be: (1) decay_pass scoring, (2) vault promotion of stable records, (3) eviction of low-score records. This ensures a record destined for T2 is safely in the vault before being retired from T1.

---

## Code Examples

### Composite Hypothesis Strategy for MemoryRecord Sets

```python
# Source: hypothesis.readthedocs.io + confirmed pattern from test_decay.py
# [VERIFIED: hypothesis docs via Context7 /hypothesisworks/hypothesis]

import hypothesis.strategies as st
from hypothesis import given, settings
from mnema.core.schema import MemoryRecord, RecordType

@st.composite
def record_set_strategy(draw):
    n = draw(st.integers(min_value=0, max_value=30))
    records = []
    for _ in range(n):
        records.append(MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=draw(st.sampled_from(list(RecordType))),
            content=draw(st.text(min_size=1, max_size=100, alphabet=st.characters(
                blacklist_categories=("Cs",)  # exclude surrogates
            ))),
            protected=draw(st.booleans()),
            salience=draw(st.floats(min_value=0.0, max_value=1.0,
                                    allow_nan=False, allow_infinity=False)),
        ))
    return records
```

### FastMCP In-Process Client Testing

```python
# Source: gofastmcp.com — "In-Memory Testing of FastMCP Server and Client"
# [VERIFIED: Context7 /websites/gofastmcp 2026-06-14]

import pytest
from fastmcp import Client

@pytest.fixture
def mcp_server(engine):
    from mnema.mcp.server import create_mcp_server
    return create_mcp_server(engine)

async def test_tool_exists(mcp_server):
    async with Client(mcp_server) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert "remember" in names

async def test_call_tool(mcp_server):
    async with Client(mcp_server) as client:
        result = await client.call_tool("remember", {
            "content": "test content",
            "user_id": "u1",
            "session_id": "s1",
        })
        assert result.data is not None
```

### TokenCounter Usage

```python
# [VERIFIED: tiktoken 0.13.0 installed, binary wheel available Python 3.12 Windows]

from mnema.core.packer import TiktokenCounter, ByteLengthCounter

counter = TiktokenCounter()  # runtime dep — tiktoken must be in pyproject.toml
print(counter.count("I am allergic to peanuts and shellfish."))  # → 9

fallback = ByteLengthCounter()
print(fallback.count("I am allergic to peanuts and shellfish."))  # → 9 (accurate for this input)
```

### sqlite-vec vec0 DELETE by Primary Key

```python
# [VERIFIED: direct test on sqlite-vec 0.1.9, Python 3.12]
# Standard SQL DELETE works on vec0 virtual tables.
# SqliteT1.delete_vector() already implements this correctly:

await self._db.execute(
    "DELETE FROM vec_t1 WHERE record_id = ?", (record_id,)
)
await self._db.commit()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| MCP servers hand-roll JSON-RPC | FastMCP decorator `@mcp.tool` | 2024 | Zero boilerplate; auto schema gen from type hints |
| Hypothesis `@given` wraps async def | Sync test wraps async with `asyncio.run()` | Always the pattern | Required — Hypothesis does not support async def natively |
| Hard DELETE of expired vectors | `valid_until` + cold-store archive + vector DELETE | MNEMA design | Recoverable eviction; audit trail; portability |
| Tiktoken required Rust build | Pre-built binary wheels for all major platforms | tiktoken 0.4.0+ | Zero Rust toolchain requirement on Python 3.12 |

**Deprecated/outdated:**
- `hypothesis-trio`: A separate package for Trio async; not needed for asyncio/MNEMA.
- FastMCP `<3.0` API: The `3.x` API changed significantly from `2.x`. MNEMA uses `3.4.2` exclusively.
- psycopg2: Replaced by psycopg3 (not directly relevant here but noted in CLAUDE.md).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `VAULT_SALIENCE_THRESHOLD = 0.7` is an appropriate cutoff for T2 promotion | Pattern 4 / CONS-09 | Too high: vault too sparse; too low: vault cluttered with low-value records. Tune in Phase 5 demo eval. |
| A2 | Vault dedup by summary string equality is sufficient for Phase 3 MVP | Pattern 4 / D3-12 | Paraphrase duplicates slip through. Acceptable for MVP; Phase 5 or post-MVP should use semantic dedup. |
| A3 | `asyncio.run()` inside a sync Hypothesis test does not conflict with `asyncio_mode=auto` | Pattern 2 / Pitfall 1 | If pytest-asyncio `asyncio_mode=auto` somehow intercepts `asyncio.run()` calls inside sync test bodies, the Hypothesis tests may fail with event-loop errors. Mitigation: the existing `test_decay.py` uses the same pattern successfully, confirming compatibility. |

**If this table were empty:** All claims in this research were verified or cited — no user confirmation needed.

---

## Open Questions

1. **`budget` parameter placement on `engine.recall()`**
   - What we know: `RecallPath.execute()` currently returns `list[MemoryRecord]` without budget awareness.
   - What's unclear: Should `budget` be added to `engine.recall()` signature (breaking change for SDK users), or should the packer be called by the MCP tool layer only (non-breaking, but inconsistent with IFACE-01)?
   - Recommendation: Add `budget: int | None = None` to `engine.recall()` signature. If `None`, return all ranked results (SDK behavior). If set, apply packer (MCP tool default). This keeps the SDK usable without a budget while satisfying RECALL-04.

2. **EvictionPass as standalone method vs. inside `ConsolidationPipeline.run()`**
   - What we know: `engine.forget(record_id)` is single-record targeted. Batch eviction (decay_pass-based) belongs in consolidation.
   - What's unclear: Where exactly to hook the eviction pass — in `ConsolidationPipeline.run()` or as a separate `evict()` method on `MemoryEngine`?
   - Recommendation: Add `MemoryEngine.evict(user_id)` as a separate async method that the consolidation pipeline calls (via `_run_eviction_pass()`). This keeps `ConsolidationPipeline` focused and `MemoryEngine.forget()` focused on single-record targeted forget. Both paths share the same underlying eviction mechanics.

3. **`engine.forget()` semantics: single-record targeted forget vs. batch eviction**
   - What we know: The stub says "set valid_until, move to T0 cold storage, clear from vector index, add to eviction audit log."
   - What's unclear: Does `forget(record_id)` bypass the keep_score threshold (user explicitly forgets a record) or does it run keep_score first?
   - Recommendation: `engine.forget(record_id)` is an explicit/forced forget — it does NOT check keep_score. It always evicts the named record (unless protected, in which case raise ValueError). Batch decay-based eviction is a separate path.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All | ✓ | 3.12 (pyproject.toml) | — |
| sqlite-vec | T1 vector delete | ✓ | 0.1.9 | — |
| aiosqlite | T1 async ops | ✓ | installed | — |
| fastmcp | MCP server | must add | 3.4.2 (PyPI) | — |
| hypothesis | FORG-03 property test | must add | 6.155.2 (PyPI) | No fallback — required by D3-03 |
| tiktoken | Budget packer token count | ✓ (system Python), must add to venv | 0.13.0, cp312-win_amd64 wheel | `ByteLengthCounter` (byte/4 estimate) |

**Missing dependencies with no fallback:**
- `fastmcp` — must be added to `[project.dependencies]` before MCP server implementation.
- `hypothesis` — must be added to `[project.optional-dependencies] dev` before writing FORG-03 property test.

**Missing dependencies with fallback:**
- `tiktoken` — `ByteLengthCounter` is an adequate fallback for MVP; tiktoken preferred for production accuracy.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio >=1.4 |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` |
| Quick run command | `uv run --extra dev pytest tests/test_forgetting.py tests/test_recall_packer.py -x -q` |
| Full suite command | `uv run --extra dev pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FORG-02 | Records below threshold evicted (valid_until set, vector deleted, archived) | integration | `pytest tests/test_forgetting.py::TestEviction::test_eviction_sets_valid_until -x` | ❌ Wave 0 |
| FORG-03 | Protected records never evicted — invariant, not example | property (Hypothesis) | `pytest tests/test_forgetting.py::test_protected_records_never_evicted -x` | ❌ Wave 0 |
| FORG-04 | Eviction audit JSONL is written with correct fields | unit/integration | `pytest tests/test_forgetting.py::TestEviction::test_eviction_audit_jsonl -x` | ❌ Wave 0 |
| RECALL-03 | Re-rank returns records sorted by relevance×salience×recency | unit (sync) | `pytest tests/test_recall_packer.py::TestReRank -x` | ❌ Wave 0 |
| RECALL-04 | Budget packer fits summaries under token budget | unit (sync) | `pytest tests/test_recall_packer.py::TestPacker::test_pack_under_budget -x` | ❌ Wave 0 |
| RECALL-05 | Protected fact survives large off-topic history | adversarial unit | `pytest tests/test_recall_packer.py::test_critical_fact_survives_large_off_topic_history -x` | ❌ Wave 0 |
| CONS-09 | Confirmed high-salience records promoted to vault on consolidation | integration | `pytest tests/test_vault.py::test_promotion_on_consolidation -x` | ❌ Wave 0 |
| TIER-03 | Vault writes human-readable markdown per user, sectioned, deduped | unit | `pytest tests/test_vault.py::TestLocalFSVault -x` | ❌ Wave 0 |
| IFACE-02 | MCP server exposes 5 verbs; remember/recall roundtrip works | integration | `pytest tests/test_mcp_server.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run --extra dev pytest tests/ -x -q --tb=short`
- **Per wave merge:** `uv run --extra dev pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_forgetting.py` — covers FORG-02, FORG-03, FORG-04
- [ ] `tests/test_recall_packer.py` — covers RECALL-03, RECALL-04, RECALL-05
- [ ] `tests/test_vault.py` — covers CONS-09, TIER-03
- [ ] `tests/test_mcp_server.py` — covers IFACE-02
- [ ] `src/mnema/core/packer.py` — new module for BudgetPacker + TokenCounter
- [ ] `src/mnema/ports/vault.py` — new VaultStore Protocol
- [ ] `src/mnema/adapters/vault/local_fs_vault.py` — new LocalFSVault adapter
- [ ] `src/mnema/mcp/server.py` — new MCP server module
- [ ] `src/mnema/mcp/__init__.py` — new package init
- [ ] `src/mnema/adapters/vault/__init__.py` — new package init
- [ ] Add to pyproject.toml: `fastmcp>=3.4.2,<4`, `tiktoken>=0.13` (runtime), `hypothesis>=6.155` (dev)

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | MCP server uses explicit user_id arg (not session auth). stdio transport is local-only. |
| V3 Session Management | no | stdio MCP is single-client, local. No HTTP session. |
| V4 Access Control | yes (partial) | `engine.forget(record_id, user_id=...)` must verify record.user_id matches. Same scope check as `engine.expand()`. |
| V5 Input Validation | yes | MCP tool args validated by FastMCP/Pydantic. `user_id`, `record_id` are strings — validated by `MemoryEngine` scope checks (existing pattern). |
| V6 Cryptography | no | Vault markdown files are plaintext local FS. No new crypto surface. |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-user eviction: `forget(record_id, user_id=attacker_id)` targeting victim's record | Tampering | `engine.forget()` must fetch record, verify `record.user_id == user_id` before mutating. Mirrors existing `engine.expand()` scope check. |
| Audit log tampering (JSONL append) | Tampering | MVP: file-system level. Phase 4 can use append-only object store. Flag but do not block Phase 3. |
| Path traversal via `user_id` in vault filename | Tampering | `LocalFSVault._vault_path()` must sanitize `user_id` with same pattern as `LocalFS._validate_session_id()` — alphanumeric + hyphens + underscores only. |
| MCP tool arg injection via `content` field containing JSONL payload | Tampering | `content` is stored as text in T1 — no SQL interpolation (parameterized queries). FastMCP/Pydantic validates types. No new surface. |

---

## Sources

### Primary (HIGH confidence)
- `pip index versions fastmcp` — fastmcp 3.4.2 current 2026-06-14 [VERIFIED]
- `pip index versions hypothesis` — hypothesis 6.155.2 current 2026-06-14 [VERIFIED]
- `pip index versions tiktoken` + `pip download` — tiktoken 0.13.0, cp312-win_amd64 wheel available [VERIFIED]
- Context7 `/websites/gofastmcp` — FastMCP server construction, tools, in-process Client, lifespan [VERIFIED]
- Context7 `/hypothesisworks/hypothesis` — `@composite`, `@given`, strategies [VERIFIED]
- Direct Python test of sqlite-vec 0.1.9 vec0 DELETE — `DELETE FROM vec_t1 WHERE record_id = ?` works [VERIFIED]
- Direct Python test of tiktoken token counting — `cl100k_base` encodes correctly [VERIFIED]
- `src/mnema/adapters/vector_store/sqlite_t1.py` — `delete_vector()` already implemented correctly [VERIFIED via code read]
- `src/mnema/adapters/object_store/local_fs.py` — `archive()` stub exists, pattern clear [VERIFIED via code read]
- `src/mnema/core/decay.py` — `decay_pass` structural FORG-03 guarantee, sync `asyncio.run()` pattern [VERIFIED via code read]
- `tests/test_decay.py` — established `asyncio.run()` inside sync test pattern [VERIFIED via code read]

### Secondary (MEDIUM confidence)
- [github.com/asg017/sqlite-vec releases/tag/v0.1.9](https://github.com/asg017/sqlite-vec/releases/tag/v0.1.9) — confirmed v0.1.9 fixes DELETE bug for long text metadata columns
- [gofastmcp.com FastMCP blog](https://jlowin.dev/blog/fastmcp-3) — FastMCP 3.x architecture overview

### Tertiary (LOW confidence)
- WebSearch results on Hypothesis + asyncio compatibility — confirmed sync-wrapper pattern is the recommended approach; full official docs page returned empty content from WebFetch

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against PyPI; binary wheel confirmed
- Architecture: HIGH — all integration points read directly from existing code; no assumed interfaces
- Pitfalls: HIGH — pitfalls 1/2/7/8 verified against existing code; pitfalls 3/4/5/6 derived from direct implementation analysis
- FastMCP patterns: HIGH — verified via Context7 official docs
- Hypothesis async pattern: MEDIUM — sync wrapper pattern confirmed by `test_decay.py` existing usage and multiple WebSearch sources, but official Hypothesis docs page returned no content (server error); pattern is well-established in the codebase

**Research date:** 2026-06-14
**Valid until:** 2026-07-14 (fastmcp is fast-moving; re-verify if > 30 days)
