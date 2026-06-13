# Phase 2: Consolidation & Supersession - Research

**Researched:** 2026-06-13
**Domain:** Offline consolidation pipeline — deterministic extraction, entity resolution, atomic supersession, idempotency, decay keep_score
**Confidence:** HIGH (all schema/adapter facts verified against live codebase; decay formula verified by Python execution; transaction pattern verified via Context7 aiosqlite docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**LLM Extraction — local + deterministic (D2-01..D2-04)**
- Ship a deterministic `StubLLM` adapter behind the existing `LLMProvider` Protocol (mirrors StubEmbedder hermetic-CI pattern). Real Qwen/Claude adapters land in Phase 4.
- Extraction yields 0..N typed records per turn (a turn may produce multiple facts or none).
- Safety/medical content is pinned `protected` + salience 1.0 by the Phase-1 content-driven `_is_safety_claim()` / `_SAFETY_KEYWORDS` rule — NEVER by trusting the LLM's salience judgment.
- On reconciliation, reuse the provisional record's existing embedding; only embed newly-extracted records that had no provisional ancestor (cost discipline, CONS-06).

**Entity Resolution & Contradiction (D2-05..D2-08)**
- Candidate match by dense cosine similarity over live records, user-scoped and narrowed by `record_type`; candidates above threshold (~cosine 0.85) passed to contradiction judge.
- The (Stub)LLM judge returns verdict `{contradict | refine | distinct}`; deterministic for seeded fixtures.
- Match threshold is a tunable constant (~0.85 cosine), Claude's discretion to tune; documented in code.
- **CONS-08 (load-bearing):** Structural pre-check gates supersession — if matched live record is `protected` OR `record_type == FACT`, pipeline NEVER auto-supersedes on LLM contradiction alone; records `contradiction_pending` graph edge and leaves record live. Only explicit `forget()` supersedes a protected/FACT record.

**Supersession Transaction & Idempotency (D2-09..D2-12)**
- Supersession is atomic in a single SQLite transaction: set `valid_until` + `superseded_by` on old record AND insert `supersedes` graph edge together.
- Idempotency identity key is the existing `t0_ref` (`t0://session/offset`) — no new schema column.
- Drain staging queue + reconcile-by-`t0_ref` yields idempotency regardless of crash timing; re-running consolidation upgrades existing record rather than inserting duplicate.
- Provisional records upgraded in place (clear `provisional` flag), never deleted-and-reinserted.

**Decay Pass & keep_score (D2-13..D2-16)**
- Phase 2 computes `keep_score` only; eviction and salience floor are Phase 3.
- `keep_score` computed on demand by a pure sync function (sans-I/O), NOT persisted.
- Recency reference time = `last_accessed` if set, else `created_at`.
- Decay step is a separate `decay()` function invoked at the end of consolidation and reusable by Phase 3.

### Claude's Discretion
- Exact cosine threshold for entity-resolution candidate match (~0.85 is the starting point; tune against fixtures).
- Extraction JSON schema for StubLLM (the shape of the structured output the stub returns).
- Whether the consolidation pipeline lives in `core/consolidation.py` or is split into sub-modules.
- Precise `keep_score` weights (w_recency, w_reinforcement, w_salience) and lambda (recency half-life); research recommends specific values below.

### Deferred Ideas (OUT OF SCOPE)
- Real cloud LLM extraction quality + flash-tier salience judging → Phase 4.
- Eviction, salience floor enforcement, budget-aware recall packer → Phase 3.
- Trained embedding-head classifier → still deferred.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONS-01 | Consolidation drains staging queue and extracts typed records via configured (cheap) LLM | StubLLM adapter pattern; `asyncio.Queue.get_nowait()` drain loop |
| CONS-02 | Consolidation judges salience per record; safety/medical content is pinned to `protected` | Reuse `_is_safety_claim()` from write_path.py; StubLLM returns salience float |
| CONS-03 | Entity resolution matches a new record against near records by same subject + same predicate | Cosine similarity over `vector_search`; type-narrowed query |
| CONS-04 | A contradicting match is actively superseded — old record gets `valid_until`, `superseded_by`, `supersedes` edge | Atomic SQLite transaction pattern; `graph_edges` JSON append |
| CONS-05 | A non-contradicting match is merged into the existing record | `model_copy(update={...})` + `record_store.upsert()` pattern |
| CONS-06 | Provisional records reconciled in place by `t0_id` identity; provisional flag cleared | `t0_ref` lookup query; in-place `update(provisional=False)` |
| CONS-07 | Consolidation is idempotent — re-running produces no duplicate live records | `t0_ref` uniqueness check before insert; idempotency test with re-run |
| CONS-08 | Protected / `fact`-type records are never auto-superseded on LLM contradiction alone | Structural pre-check in `_maybe_supersede()`; `contradiction_pending` edge; property-test |
| FORG-01 | A decay pass computes `keep_score` (recency decay + reinforcement + salience) over all live records | Pure sync `keep_score()` function; Ebbinghaus exponential + log-reinforcement formula |
</phase_requirements>

---

## Summary

Phase 2 builds the offline consolidation pipeline that turns raw T0 staging-queue items + provisional T1 records into clean, typed, deduped, non-contradicting records. The pipeline is fully local and deterministic: it uses a `StubLLM` (mirroring StubEmbedder) for extraction and contradiction judging in tests, with the real LLM adapter deferred to Phase 4 behind the existing `LLMProvider` Protocol.

The highest-correctness-risk surfaces are the CONS-08 safety invariant (a protected/FACT record must NEVER be auto-superseded by LLM output alone) and the supersession transaction atomicity (WR-05 carryover: `valid_until` + `superseded_by` + graph edge must all commit together or not at all). Both are addressable with patterns already present in the codebase.

The `keep_score` decay formula (FORG-01) is a pure synchronous function using only `math.exp` and `math.log` from stdlib — no numpy, no I/O, trivially unit-testable as a standalone module consumed by Phase 3 forgetting.

**Primary recommendation:** Implement consolidation as `core/consolidation.py` (the `ConsolidationPipeline` class) + `core/decay.py` (pure `keep_score` + `decay_pass`), with `StubLLM` in `adapters/llm/stub.py`. The `MemoryEngine.consolidate()` stub is replaced with a real implementation that drains `self._staging`, calls the pipeline, and calls `decay_pass`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Staging queue drain | Core (Engine) | — | `asyncio.Queue` already lives on `MemoryEngine._staging`; drain belongs in the same owner |
| LLM extraction prompt/response | Adapter (LLM port) | Core (Consolidation) | Prompt construction and parsing are adapter concerns; control flow is core |
| Safety pinning (protected + salience 1.0) | Core (Consolidation) | — | Content-driven rule (`_is_safety_claim`) is pure logic; must not live inside the LLM adapter |
| Entity resolution candidate fetch | Adapter (VectorIndex) | Core (Consolidation) | Vector search is adapter I/O; threshold comparison + verdict dispatch is core logic |
| Contradiction verdict | Adapter (LLM port) | Core (Consolidation) | LLM produces the verdict string; core decides what to do with it |
| CONS-08 protected-fact gate | Core (Consolidation) | — | Load-bearing safety invariant — must be structural code in core, not a conditional inside the LLM adapter |
| Atomic supersession write | Adapter (SqliteT1) | — | Multi-statement atomic commit must be encapsulated in the store adapter, not scattered across callers |
| Provisional reconcile-by-t0_ref | Adapter (SqliteT1) | Core (Consolidation) | Lookup query is adapter; "is this a reconcile or a new insert?" decision is core |
| keep_score computation | Core (Decay — sans I/O) | — | Pure math; zero I/O; must be synchronous so Phase 3 can call it without event loop |
| decay_pass iteration | Core (Decay) | Adapter (RecordStore) | Iteration over live records is adapter; per-record score computation is core |

---

## Standard Stack

### Core (already in pyproject.toml — no new dependencies needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `aiosqlite` | >=0.22 | Async SQLite I/O for atomic transactions | Already in use; `await db.rollback()` / `await db.commit()` verified [VERIFIED: Context7 omnilib/aiosqlite] |
| `pydantic` | >=2.12 | `model_copy(update={...})` for in-place record merge | Already in use; `model_copy` is the idiomatic Pydantic 2 partial-update pattern [VERIFIED: Context7 pydantic/pydantic] |
| `math` (stdlib) | 3.12 stdlib | `math.exp`, `math.log` for keep_score formula | Zero dependency; verified executing decay formula [VERIFIED: codebase Python execution] |
| `hashlib` (stdlib) | 3.12 stdlib | SHA-256 deterministic seeding for StubLLM | Same pattern as StubEmbedder [VERIFIED: src/mnema/adapters/embedding/stub.py] |

### No New Dependencies Required

All Phase 2 implementation uses packages already installed. The `StubLLM` follows the `StubEmbedder` pattern (stdlib only: `hashlib`). The decay formula uses `math.exp`/`math.log`. The atomic transaction uses existing `aiosqlite` connection methods. This keeps Phase 2 fully hermetic.

**Version verification:** Confirmed by inspecting `pyproject.toml` (aiosqlite>=0.22, pydantic>=2.12, numpy>=2.4, apscheduler>=3.11,<4). [VERIFIED: pyproject.toml]

---

## Architecture Patterns

### System Architecture Diagram

```
MemoryEngine.consolidate(force=False)
        │
        ▼
  [1] Drain asyncio.Queue(_staging)
        │  get_nowait() until Empty
        │  → list[{turn, t0_ref}]
        │
        ▼
  [2] StubLLM.extract(turn_content)
        │  → list[ExtractionResult]
        │    {content, record_type, salience, keywords}
        │
        ▼
  [3] Safety pin pass (core, NOT LLM)
        │  _is_safety_claim(content)?
        │    yes → protected=True, salience=1.0
        │
        ▼
  [4] Reconcile-by-t0_ref
        │  t1.find_by_t0_ref(t0_ref, user_id)?
        │    found → provisional record exists
        │      → upgrade in place (clear provisional, update fields)
        │      → reuse existing embedding (D2-04)
        │    not found → new record path
        │      → embed content (one embed call)
        │      → entity resolution path
        │
        ▼
  [5] Entity resolution (new records only)
        │  vector_search(embedding, k=5, record_type=same)
        │  cosine_similarity > MATCH_THRESHOLD (~0.85)?
        │    no match → insert new confirmed record
        │    match found → contradiction judge
        │
        ▼
  [6] Contradiction judge (StubLLM / real LLM)
        │  judge(new_content, existing_content)
        │  → {contradict | refine | distinct}
        │
        ├── distinct  → insert new confirmed record
        │
        ├── refine    → merge into existing (CONS-05)
        │               model_copy(update={...}) + upsert()
        │
        └── contradict → CONS-08 gate
                │
                ├── existing.protected=True OR existing.record_type=FACT
                │     → record contradiction_pending edge
                │     → leave existing live (NO supersession)
                │
                └── not protected/FACT
                      → atomic supersession (CONS-04)
                          BEGIN TRANSACTION
                            UPDATE t1_records SET valid_until=now, superseded_by=new_id
                            UPDATE new_record.graph_edges += [supersedes edge]
                            INSERT new record
                          COMMIT
        │
        ▼
  [7] decay_pass() (FORG-01)
        │  for each live record (valid_until IS NULL)
        │    compute keep_score(record, now)  ← pure sync, no I/O
        │    (Phase 3 will: evict if score < floor and not protected)
        │
        ▼
  Done
```

### Recommended Project Structure

```
src/mnema/
├── adapters/
│   └── llm/
│       ├── __init__.py
│       └── stub.py          # StubLLM — deterministic extractor/judge (new)
├── core/
│   ├── consolidation.py     # ConsolidationPipeline — orchestrates steps 2-6 (new)
│   └── decay.py             # keep_score(), decay_pass() — pure sync (new)
├── ports/
│   └── llm.py               # LLMProvider Protocol (EXISTS — add extract/judge methods)
```

The engine's `consolidate()` method in `engine.py` is replaced with a real implementation that constructs a `ConsolidationPipeline` and calls it.

### Pattern 1: StubLLM Deterministic Extractor

**What:** A deterministic `LLMProvider` adapter that uses a fixed rule-table keyed on keyword patterns, seeded from `hashlib.sha256` for salience variation within a range. Returns structured data (list of extraction dicts) when the prompt is recognized as an extraction prompt, and a verdict string when recognized as a contradiction-judge prompt.

**When to use:** All Phase 2 tests; replaced transparently by `QwenLLMProvider` in Phase 4.

**Design:**

The `LLMProvider.complete(prompt)` signature returns a `str`. The consolidation pipeline constructs prompts in a structured format and parses the `str` response. The `StubLLM` mimics this by:

1. Examining the prompt for a sentinel string (e.g. `"EXTRACT_RECORDS:"`) to enter extraction mode.
2. Returning a JSON string with a fixed-format list of record dicts.
3. Examining the prompt for `"JUDGE_CONTRADICTION:"` to enter verdict mode, returning one of `"contradict"`, `"refine"`, or `"distinct"` deterministically based on a hash of the two content strings.

This pattern keeps the stub transparent — the consolidation core never knows whether it's talking to `StubLLM` or `QwenLLMProvider`.

```python
# Source: mirrors src/mnema/adapters/embedding/stub.py pattern [VERIFIED: codebase]
import hashlib, json

class StubLLM:
    """Deterministic LLM for hermetic CI. Mirrors StubEmbedder pattern."""

    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        if "EXTRACT_RECORDS:" in prompt:
            return self._extract(prompt)
        if "JUDGE_CONTRADICTION:" in prompt:
            return self._judge(prompt)
        return ""

    def _extract(self, prompt: str) -> str:
        # Keyword-table extraction: scan prompt content for known patterns
        content = prompt.split("EXTRACT_RECORDS:", 1)[1].strip()
        records = _keyword_extract(content)   # pure deterministic rule table
        return json.dumps(records)

    def _judge(self, prompt: str) -> str:
        # Deterministic verdict: hash of (existing, new) content pair
        body = prompt.split("JUDGE_CONTRADICTION:", 1)[1].strip()
        h = int(hashlib.sha256(body.encode()).hexdigest(), 16) % 3
        return ["distinct", "refine", "contradict"][h]
```

**Key insight:** The extraction sentinel approach means the real `QwenLLMProvider` uses exactly the same prompt format — the sentinel text is part of the consolidation pipeline's prompt template, not the stub's magic.

### Pattern 2: Atomic Supersession Transaction

**What:** A single SQLite transaction that atomically sets `valid_until` + `superseded_by` on the old record, appends the `supersedes` edge to the new record's `graph_edges`, and inserts the new record. Addresses WR-05 from the Phase 1 code review.

**When to use:** Whenever a contradiction verdict is reached and the existing record is not protected/FACT.

**Design:** Add a new method `supersede(old_id, new_record, embedding)` to `SqliteT1` that wraps all writes in `BEGIN ... COMMIT / ROLLBACK`:

```python
# Source: aiosqlite transaction pattern [VERIFIED: Context7 omnilib/aiosqlite]
async def supersede(
    self,
    old_id: str,
    new_record: MemoryRecord,
    embedding: list[float],
) -> None:
    """Atomic supersession: retire old record + insert new record in one transaction."""
    now_str = _dt_to_str(datetime.now(timezone.utc))
    try:
        # Step 1: retire the old record
        await self._db.execute(
            "UPDATE t1_records SET valid_until=?, superseded_by=? WHERE id=?",
            (now_str, new_record.id, old_id),
        )
        # Step 2: insert the new record (new_record.graph_edges already has supersedes edge)
        await self._db.execute(INSERT_SQL, _record_params(new_record))
        # Step 3: insert the new vector
        await self._db.execute(
            "INSERT OR REPLACE INTO vec_t1(record_id, embedding) VALUES (?, ?)",
            (new_record.id, _v32(embedding)),
        )
        await self._db.commit()
    except Exception:
        await self._db.rollback()
        raise
```

Note: `aiosqlite` with `isolation_level=""` (autocommit off, which is the default for DML) means `execute()` calls are implicitly in a transaction until `commit()` or `rollback()`. [VERIFIED: Context7 omnilib/aiosqlite]

### Pattern 3: Reconcile-by-t0_ref (CONS-06/07 Idempotency)

**What:** Before inserting a new extracted record, look up whether a provisional record with the same `t0_ref` already exists in T1. If found, upgrade it in place. If not found, proceed to entity resolution. This is what makes re-running consolidation idempotent.

**Design:** Add `find_by_t0_ref(t0_ref, user_id)` to `SqliteT1`:

```python
# Source: existing SELECT pattern in sqlite_t1.py [VERIFIED: codebase]
async def find_by_t0_ref(self, t0_ref: str, user_id: str) -> MemoryRecord | None:
    cursor = await self._db.execute(
        "SELECT * FROM t1_records WHERE t0_ref=? AND user_id=? AND valid_until IS NULL",
        (t0_ref, user_id),
    )
    row = await cursor.fetchone()
    return row  # type: ignore[return-value]
```

When the provisional record is found, the consolidation pipeline calls `record_store.update(record.id, provisional=False, salience=..., record_type=..., keywords=..., summary=...)`. No delete-and-reinsert; no new embedding call; no duplicate.

**Idempotency guarantee:** If consolidation crashes after step [3] but before step [4], the second run finds the same staging items in the queue (queue is not popped until work completes), does the same reconcile, and produces the same result. The `t0_ref` uniqueness check (`find_by_t0_ref`) is the idempotency fence.

### Pattern 4: LLMProvider Protocol Extension

**What:** The existing `LLMProvider.complete(prompt, *, model)` Protocol in `ports/llm.py` needs two usage modes (extract + judge). Both can be served through the single `complete()` method with prompt-level conventions. The Protocol does NOT need new methods — the consolidation pipeline constructs prompt strings and parses `str` responses.

**Rationale:** Adding `extract()` and `judge()` to the Protocol would force Phase 4 adapters to implement three methods instead of one. The real `QwenLLMProvider` can serve all three modes through one `complete()` endpoint. Keeping the Protocol narrow preserves the Phase 4 adapter surface.

**Alternative considered:** Typed structured-output Protocol with `extract(content: str) -> list[ExtractionResult]`. Rejected for Phase 2 because it pre-designs the Phase 4 adapter contract before we know the Qwen/Claude structured-output shapes. The string-based contract gives Phase 4 full freedom to use tool-calls, JSON mode, or structured output. [ASSUMED — the specific Phase 4 adapter design is deferred; this judgment is based on current codebase direction]

### Pattern 5: keep_score Pure Sync Function

**What:** A module `core/decay.py` with a single pure function `keep_score(record, now)` returning a float in [0.0, 1.0]. No I/O, no async, no event loop. A companion `decay_pass(record_store, user_id, now)` async generator computes scores over live records (consumed by Phase 3 for eviction).

**Formula (from `mnema-build-plan.md` §4, verified):**

```python
# Source: mnema-build-plan.md §4 [VERIFIED: mnema-build-plan.md], formula executed [VERIFIED: codebase]
import math
from datetime import datetime, timezone

# Tunable weights — document in code, default values here
W_RECENCY      = 0.4   # weight on exponential recency decay
W_REINFORCE    = 0.3   # weight on logarithmic access reinforcement
W_SALIENCE     = 0.3   # weight on LLM-judged long-term salience
LAMBDA_DECAY   = 0.05  # recency half-life ≈ 14 days (ln(2)/0.05 ≈ 13.9)

def keep_score(record: MemoryRecord, now: datetime | None = None) -> float:
    """Pure sync keep_score: recency_decay + reinforcement + salience.

    Reference time: last_accessed if set, else created_at (D2-15).
    Protected records are NOT scored by this function — callers must
    skip them BEFORE calling keep_score (FORG-03 structural guarantee).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    ref_time = record.last_accessed if record.last_accessed is not None else record.created_at
    age_days = max(0.0, (now - ref_time).total_seconds() / 86400.0)

    recency = math.exp(-LAMBDA_DECAY * age_days)
    reinforce = math.log(1.0 + record.access_count)
    score = W_RECENCY * recency + W_REINFORCE * reinforce + W_SALIENCE * record.salience
    # Clamp to [0, 1] since reinforce can push score above 1 at high access_count
    return min(1.0, max(0.0, score))
```

**Why these defaults:**
- `LAMBDA_DECAY = 0.05`: ln(2)/0.05 ≈ 13.9 days half-life. A record not accessed in two weeks decays to ~0.22 of its recency contribution. Reasonable for dietary preferences that update weekly. [ASSUMED — no project-specific calibration data exists yet; tune against the Phase 5 demo evaluation]
- `W_REINFORCE = 0.3` + `math.log(1 + count)`: log-linear reinforcement follows the Ebbinghaus spacing effect — early reinforcements have highest marginal value. An accessed 5-times record gets `log(6) ≈ 1.79` reinforcement; the 0.3 weight caps its contribution at ~0.54. [ASSUMED — consistent with the build plan; specific weights need empirical tuning in Phase 3/5]
- `W_SALIENCE = 0.3`: at `salience=1.0` (protected fact), the salience contribution alone is 0.3, making it hard to fall below any reasonable eviction floor even with zero access. Combined with the structural `protected` flag skip, this is defense-in-depth. [ASSUMED]

### Anti-Patterns to Avoid

- **Calling `keep_score` on protected records:** The Phase-3 decay loop must check `record.protected` BEFORE calling `keep_score`. Putting the guard inside `keep_score` would hide the FORG-03 invariant. The structural pattern is: `if record.protected: continue` in the caller.
- **Committing supersession in multiple transactions:** The old record update, new record insert, and vector insert must be a single `COMMIT`. An interim crash with a partially-applied supersession leaves the old record live-but-with-`superseded_by` pointing at a non-existent new record. Use the `supersede()` method on `SqliteT1`.
- **Deleting-and-reinserting provisional records:** Drops the embedding; requires a new embed call; loses the original `t0_ref`; breaks the idempotency check. Always upgrade in place.
- **Embedding extracted content when a provisional ancestor exists:** D2-04 locked decision. The provisional record already has an embedding. Reuse it. A new embed call costs money and produces a marginally different vector for the same semantic content.
- **Trusting LLM salience for safety records:** `_is_safety_claim()` must run on every extracted record regardless of the LLM's salience judgment. The LLM may return `salience=0.6` for "I take metformin daily"; the content rule must override to `protected=True, salience=1.0`.
- **Superseding protected/FACT records on LLM contradiction alone:** This is the CONS-08 invariant. The check must happen BEFORE the verdict is acted on, not inside the LLM adapter.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic multi-statement SQLite transaction | Custom two-phase commit | `aiosqlite` `commit()` / `rollback()` within one connection | SQLite's WAL + single-writer model guarantees atomicity at the connection level |
| Pydantic model partial update (merge) | Manual dict unpacking + reconstruction | `record.model_copy(update={...})` | Preserves validators, type safety, and default values; idiomatic Pydantic 2 [VERIFIED: Context7] |
| Cosine similarity | Manual dot-product | `vector_search()` on `SqliteT1` (already uses sqlite-vec distance) | sqlite-vec's L2 distance over L2-normalized vectors is equivalent to cosine similarity [VERIFIED: codebase — StubEmbedder produces L2-normalized vectors] |
| Queue drain with `Empty` catch | `while not queue.empty(): queue.get()` (race-prone) | `while True: try: item = queue.get_nowait() except asyncio.QueueEmpty: break` | `queue.empty()` is not thread-safe; `get_nowait()` + `QueueEmpty` is the correct asyncio pattern [VERIFIED: Python asyncio docs] |
| Structured LLM output parsing | Custom regex parser | JSON parsing of the `str` response from `complete()` | The consolidation pipeline formats prompts with JSON output instructions; `json.loads()` on the response is the standard pattern |

**Key insight:** The existing `SqliteT1.update()` already provides the partial-update primitive. The atomic supersession needs a NEW `supersede()` method, not modifications to `update()`. Keep `update()` as the general partial-update primitive.

---

## Runtime State Inventory

Phase 2 is a new pipeline with no rename/refactor. The staging queue (`asyncio.Queue`) is in-memory and restarted fresh on each process start. No persistent naming or runtime state to migrate.

**Nothing found in any category — verified:**
- Stored data: None — staging queue is in-memory; no Phase 2 state in SQLite yet.
- Live service config: None — no external services configured for Phase 2.
- OS-registered state: None.
- Secrets/env vars: None — Phase 2 is fully local/deterministic.
- Build artifacts: None — no Phase 2 artifacts installed.

---

## Common Pitfalls

### Pitfall 1: `asyncio.Queue` Drain Ordering

**What goes wrong:** `queue.empty()` is not atomic with `get_nowait()`. Between `queue.empty()` returning `True` and `get_nowait()`, another coroutine can `put()` an item, making the drain non-deterministic in multi-producer scenarios.

**Why it happens:** The staging queue has one producer (`WritePath.execute()`) and one consumer (consolidation). In Phase 2, this is inherently sequential (consolidation runs between turns), but the pattern should be correct by construction.

**How to avoid:** Use `get_nowait()` + catch `asyncio.QueueEmpty`:

```python
items = []
while True:
    try:
        items.append(self._staging.get_nowait())
    except asyncio.QueueEmpty:
        break
```

**Warning signs:** Consolidation occasionally misses items that were enqueued just before it started.

### Pitfall 2: CONS-08 Gate Applied After Verdict, Not Before

**What goes wrong:** The pipeline gets the LLM's `contradict` verdict and then checks `existing.protected`. By this point, code is already structured to apply supersession. Developers add `if not existing.protected: supersede()` but accidentally nest the graph-edge insertion inside the same block, forgetting to record `contradiction_pending`.

**Why it happens:** The gate feels like an "exception to supersession" rather than a "structurally separate code path."

**How to avoid:** Structure the code as two completely separate branches at the top of the supersession decision:

```python
if existing.protected or existing.record_type == RecordType.FACT:
    # CONS-08: record contradiction_pending, leave live
    _record_pending_contradiction(existing, new_record, record_store)
    return
# Only reach here if supersession is permitted
await record_store.supersede(existing.id, new_record, embedding)
```

**Warning signs:** Test `test_cons08_protected_fact_not_superseded` fails intermittently or only under certain record_type combinations.

### Pitfall 3: Provisional Reconcile Misses Records Created by Type-Hint

**What goes wrong:** The provisional reconcile path (`find_by_t0_ref`) correctly finds provisional records created by `WritePath`. However, a test that calls `engine.remember(..., type_hint="fact")` with an explicit type hint creates a provisional record whose `record_type` is already `FACT` — not the `PREFERENCE` default. The consolidation extraction may also classify the same content as `FACT`. The merge then sees `record_type` already set correctly and proceeds without noticing; this is actually fine. The pitfall is assuming ALL provisionals were written with `record_type=PREFERENCE`.

**How to avoid:** The reconcile path should update `record_type` from the extraction result even if the provisional was already set to `FACT`. Use `update(..., record_type=extracted_type, ...)` unconditionally.

### Pitfall 4: Cosine Distance vs. Cosine Similarity Threshold

**What goes wrong:** `sqlite-vec`'s `vec0` table returns `distance` (lower = closer). When the `StubEmbedder` produces L2-normalized vectors, the returned distance is L2-distance, which equals `sqrt(2 - 2*cosine_similarity)`. A threshold of `0.85` cosine similarity corresponds to an L2-distance of approximately `0.55`. Using the threshold directly on the raw distance value produces wrong matches.

**How to avoid:** The `MATCH_THRESHOLD` constant must be expressed in the same units as the returned distance. Either:

(a) Convert: `max_distance = math.sqrt(2.0 - 2.0 * cosine_threshold)` at the call site, or

(b) Express the threshold in L2-distance units in the code comment and constant name: `ENTITY_MAX_DISTANCE = 0.55  # ≈ cosine similarity >= 0.85 for L2-normalized vectors`.

Option (b) is simpler and avoids a runtime computation. [VERIFIED: L2-normalized vector geometry — verified by computing sqrt(2 - 2*0.85) = 0.5477]

```python
import math
print(math.sqrt(2 - 2 * 0.85))  # 0.5477...
```

**Warning signs:** Entity-resolution tests fail with no matches even when content is semantically identical; or too many false-positive matches.

### Pitfall 5: `model_copy` Shallow Copy of `graph_edges`

**What goes wrong:** `record.model_copy(update={"graph_edges": new_edges})` creates a new model instance with `new_edges` as `graph_edges`. However, if the caller mutates the list before passing it (e.g., `edges = record.graph_edges; edges.append(...); model_copy(update={"graph_edges": edges})`), the original record's `graph_edges` is also mutated because Python lists are mutable.

**How to avoid:** Always pass a new list to `model_copy`:

```python
new_edges = list(record.graph_edges) + [{"rel": "supersedes", "target": old_id}]
updated = record.model_copy(update={"graph_edges": new_edges})
```

**Warning signs:** Graph edges accumulate across multiple consolidation runs unexpectedly.

### Pitfall 6: SQLite WAL + `aiosqlite` Single Connection — No Separate Transaction Object

**What goes wrong:** Developers familiar with `psycopg3` or `SQLAlchemy` expect a transaction context manager (`async with db.transaction()`). `aiosqlite` does not expose a `transaction()` context manager. Transactions are implicit: SQLite begins one automatically on the first DML statement within a session.

**How to avoid:** Wrap multi-statement writes with explicit `try/except` + `await db.commit()` / `await db.rollback()`. This is the pattern used in the existing `upsert()` method and confirmed by Context7 docs. [VERIFIED: Context7 omnilib/aiosqlite]

---

## Code Examples

Verified patterns from official sources and the live codebase.

### Drain asyncio.Queue

```python
# Source: Python asyncio stdlib [ASSUMED — standard asyncio pattern]
import asyncio

async def _drain_staging(queue: asyncio.Queue) -> list[dict]:
    items: list[dict] = []
    while True:
        try:
            items.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return items
```

### Atomic Supersession Transaction

```python
# Source: aiosqlite transaction pattern [VERIFIED: Context7 omnilib/aiosqlite]
async def supersede(self, old_id: str, new_record: MemoryRecord, embedding: list[float]) -> None:
    now_str = _dt_to_str(datetime.now(timezone.utc))
    try:
        await self._db.execute(
            "UPDATE t1_records SET valid_until=?, superseded_by=? WHERE id=?",
            (now_str, new_record.id, old_id),
        )
        # new_record already has graph_edges with supersedes edge
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

### Provisional Reconcile (CONS-06/07)

```python
# Source: existing SELECT + update() pattern [VERIFIED: src/mnema/adapters/vector_store/sqlite_t1.py]
async def reconcile_provisional(
    self,
    t0_ref: str,
    user_id: str,
    extracted: dict,
) -> bool:
    """Upgrade a provisional record in place. Returns True if reconciled."""
    existing = await self.find_by_t0_ref(t0_ref, user_id)
    if existing is None:
        return False
    await self.update(
        existing.id,
        provisional=False,
        record_type=extracted["record_type"],
        salience=extracted["salience"],
        summary=extracted["summary"],
        keywords=extracted["keywords"],
    )
    return True
```

### keep_score Pure Function

```python
# Source: mnema-build-plan.md §4 formula; execution verified [VERIFIED: codebase Python]
import math
from datetime import datetime, timezone

W_RECENCY = 0.4
W_REINFORCE = 0.3
W_SALIENCE = 0.3
LAMBDA_DECAY = 0.05  # ~14-day half-life

def keep_score(record: "MemoryRecord", now: datetime | None = None) -> float:
    if now is None:
        now = datetime.now(timezone.utc)
    ref_time = record.last_accessed if record.last_accessed is not None else record.created_at
    age_days = max(0.0, (now - ref_time).total_seconds() / 86400.0)
    recency = math.exp(-LAMBDA_DECAY * age_days)
    reinforce = math.log(1.0 + float(record.access_count))
    score = W_RECENCY * recency + W_REINFORCE * reinforce + W_SALIENCE * record.salience
    return min(1.0, max(0.0, score))
```

### CONS-08 Gate

```python
# Source: design decision D2-08 [VERIFIED: 02-CONTEXT.md]
from mnema.core.schema import RecordType

def _is_supersession_permitted(existing: "MemoryRecord") -> bool:
    """Return True only if the existing record can be auto-superseded."""
    return not existing.protected and existing.record_type != RecordType.FACT
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LLM on write path for extraction | LLM only in offline consolidation | This project's design | Write path stays fast + cheap (WRITE-03) |
| Hard-coded salience thresholds | Structural `protected` boolean + computed score | This project's design | Safety invariant is structural code, not a tunable number |
| Single `update()` + manual graph edge append | Dedicated `supersede()` transactional method | Phase 2 (WR-05 resolution) | Eliminates partial-write crash window |
| Cosine similarity in external vector DB | sqlite-vec L2-distance on L2-normalized vectors | Phase 1 | Equivalent to cosine; portable to laptop |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Keeping `LLMProvider.complete(prompt) -> str` as a single-method Protocol is sufficient for Phase 4 | Architecture Patterns (Pattern 4) | If Phase 4 adapters need a typed structured-output Protocol, the consolidation pipeline's prompt-construction + JSON-parsing layer would need refactoring |
| A2 | `LAMBDA_DECAY = 0.05` (~14-day half-life) is a reasonable default | Code Examples (keep_score) | If dietary preferences update faster (e.g., daily), a higher lambda (shorter half-life) may be needed; tune in Phase 3/5 eval |
| A3 | `W_RECENCY=0.4, W_REINFORCE=0.3, W_SALIENCE=0.3` default weights are reasonable | Code Examples (keep_score) | Weights affect eviction decisions in Phase 3; the Phase 5 demo evaluation is the calibration point |
| A4 | `ENTITY_MAX_DISTANCE ≈ 0.55` (cosine >= 0.85) is a reasonable entity-resolution threshold | Common Pitfalls (Pitfall 4) | False positives at 0.85 cause spurious supersessions; false negatives miss real contradictions; tune against fixtures |

---

## Open Questions

1. **StubLLM extraction fidelity for test coverage**
   - What we know: `StubLLM` must be deterministic; it uses keyword-table extraction for `record_type` and salience.
   - What's unclear: How many extraction fixture cases are needed to make CONS-01..08 tests meaningfully cover the pipeline? The minimum is: (a) allergy → protected/FACT, (b) preference → PREFERENCE with non-1.0 salience, (c) dietary change → contradict verdict, (d) refinement → refine verdict, (e) unrelated → distinct verdict.
   - Recommendation: Define the fixture set in Wave 0 test setup. The StubLLM keyword table is tuned to produce the correct verdicts for these specific fixtures.

2. **graph_edges schema for `contradiction_pending`**
   - What we know: `graph_edges` is a `list[dict[str, Any]]` stored as JSON. Existing schema supports `{"rel": "supersedes", "target": id}`.
   - What's unclear: Should `contradiction_pending` edges live on the existing record, the extracted record, or be logged elsewhere?
   - Recommendation: Store on the existing (live) record as `{"rel": "contradiction_pending", "target": extracted_record_id, "ts": now_iso}`. This preserves the audit trail on the record that survived.

3. **Consolidation wiring: does `MemoryEngine.consolidate()` construct `ConsolidationPipeline` inline?**
   - What we know: The engine currently has a stub; `LLMProvider` is not yet injected into the engine.
   - What's unclear: Should `LLMProvider` be added to `MemoryEngine.__init__` as a required parameter in Phase 2, or should the `ConsolidationPipeline` be constructed with a default `StubLLM` and optionally overridden?
   - Recommendation: Add `llm: LLMProvider` as a parameter to `MemoryEngine.__init__` with a default of `StubLLM()` (similar to how a default embedder could be provided). This keeps the engine configurable and avoids hard-coupling the engine to the stub.

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies introduced — Phase 2 uses only packages already installed and verified in Phase 1).

Current environment confirmed:

| Dependency | Required By | Available | Version |
|------------|-------------|-----------|---------|
| Python | Engine | ✓ | 3.14.2 (venv) |
| aiosqlite | SqliteT1 transactions | ✓ | >=0.22 installed |
| pydantic | model_copy, schema | ✓ | >=2.12 installed |
| pytest-asyncio | All tests | ✓ | >=1.4 installed |
| math (stdlib) | keep_score | ✓ | stdlib |
| hashlib (stdlib) | StubLLM | ✓ | stdlib |

Note on Python 3.14.2: pyproject.toml has no upper cap (`>=3.12`), and the venv resolved Python 3.14.2, which is above the CLAUDE.md-recommended ≤3.13 cap. The 23 existing tests pass on 3.14.2. Phase 2 introduces no new C-extension wheels (the new `StubLLM` and `decay.py` are pure Python), so this deviation does not create new risk in Phase 2. [VERIFIED: test run — 23 passed]

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio >=1.4 (asyncio_mode=auto) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/Scripts/pytest.exe -q tests/test_consolidation.py -x` |
| Full suite command | `.venv/Scripts/pytest.exe -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONS-01 | `consolidate()` drains staging queue and extracts records | integration | `pytest tests/test_consolidation.py::TestConsolidation::test_staging_queue_drained -x` | Wave 0 |
| CONS-02 | Safety content pinned protected + salience 1.0, non-safety salience is LLM-judged | unit | `pytest tests/test_consolidation.py::TestConsolidation::test_safety_content_pinned_protected -x` | Wave 0 |
| CONS-03 | Entity resolution matches same-subject same-predicate near records | unit | `pytest tests/test_consolidation.py::TestConsolidation::test_entity_resolution_finds_match -x` | Wave 0 |
| CONS-04 | Contradicting match supersedes old record atomically | integration | `pytest tests/test_consolidation.py::TestConsolidation::test_contradiction_supersession_atomic -x` | Wave 0 |
| CONS-05 | Non-contradicting match merges into existing record | unit | `pytest tests/test_consolidation.py::TestConsolidation::test_refinement_merges_in_place -x` | Wave 0 |
| CONS-06 | Provisional records reconciled in place by t0_ref; flag cleared | integration | `pytest tests/test_consolidation.py::TestConsolidation::test_provisional_reconciled_in_place -x` | Wave 0 |
| CONS-07 | Consolidation idempotent — second run produces no duplicates | integration | `pytest tests/test_consolidation.py::TestConsolidation::test_idempotent_rerun -x` | Wave 0 |
| CONS-08 | Protected/FACT records never auto-superseded | property-test | `pytest tests/test_consolidation.py::TestConsolidation::test_cons08_protected_never_superseded -x` | Wave 0 |
| FORG-01 | keep_score computed for all live records; protected records skipped | unit | `pytest tests/test_decay.py::TestDecay::test_keep_score_values -x` | Wave 0 |
| FORG-03 (partial) | Protected records skipped before keep_score math | property-test | `pytest tests/test_decay.py::TestDecay::test_protected_skipped_before_score_math -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest -q tests/test_consolidation.py tests/test_decay.py -x` (new files only, fast)
- **Per wave merge:** `.venv/Scripts/pytest.exe -q` (full 23+ tests)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_consolidation.py` — covers CONS-01..08; needs `StubLLM` fixture
- [ ] `tests/test_decay.py` — covers FORG-01 + FORG-03 guard (partial)
- [ ] `src/mnema/adapters/llm/__init__.py` — package init for new llm adapter dir
- [ ] `src/mnema/adapters/llm/stub.py` — `StubLLM` implementation
- [ ] `src/mnema/core/consolidation.py` — `ConsolidationPipeline` class
- [ ] `src/mnema/core/decay.py` — `keep_score()`, `decay_pass()`
- [ ] No new framework install needed — pytest-asyncio already installed

---

## Security Domain

Security enforcement is enabled (not set to false in config.json). Phase 2 is a fully local, in-process pipeline with no network calls, no new external inputs, and no user-facing authentication surface. ASVS categories below:

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No new auth surface in Phase 2 |
| V3 Session Management | No | Sessions are provenance metadata, not access tokens |
| V4 Access Control | Partial | `user_id` isolation must be preserved through all consolidation writes |
| V5 Input Validation | Yes | LLM response parsing (`json.loads`) must not crash on malformed output |
| V6 Cryptography | No | No new crypto — `hashlib.sha256` in StubLLM is for determinism, not security |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM response injection (malformed JSON from StubLLM or real LLM) | Tampering | `try/except json.JSONDecodeError` with a safe fallback (skip the record, log) |
| Cross-user supersession (consolidation overwrites another user's record) | Elevation of Privilege | `user_id` predicate on every `find_by_t0_ref` and `supersede()` call; existing `_ALLOWED_COLUMNS` whitelist on `update()` |
| `contradiction_pending` edge revealing existence of suppressed records | Information Disclosure | Low risk in Phase 2 (single-user local); flag for Phase 4 multi-user MCP surface |
| SQL injection via `graph_edges` content written by LLM | Tampering | Already mitigated — `graph_edges` is JSON-serialized as a parameter value, not interpolated into SQL |

---

## Sources

### Primary (HIGH confidence)
- `src/mnema/adapters/vector_store/sqlite_t1.py` — existing transaction, update(), upsert_vector() patterns [VERIFIED: codebase]
- `src/mnema/adapters/embedding/stub.py` — StubLLM mirror pattern [VERIFIED: codebase]
- `src/mnema/core/write_path.py` — `_is_safety_claim()`, `_SAFETY_KEYWORDS` reuse [VERIFIED: codebase]
- `src/mnema/core/schema.py` — all MemoryRecord columns available for Phase 2 [VERIFIED: codebase]
- `mnema-build-plan.md` §3b + §4 — consolidation pseudocode + keep_score formula [VERIFIED: codebase]
- `.planning/phases/02-consolidation-supersession/02-CONTEXT.md` — all D2-01..D2-16 decisions [VERIFIED: codebase]
- Context7 `/omnilib/aiosqlite` — `commit()` / `rollback()` transaction pattern [VERIFIED: Context7]
- Context7 `/pydantic/pydantic` — `model_copy(update={...})` partial-update pattern [VERIFIED: Context7]
- `pyproject.toml` — installed dependency versions [VERIFIED: codebase]
- Python execution — `math.exp`, `math.log` keep_score formula [VERIFIED: codebase execution]
- `.venv/Scripts/pytest.exe --collect-only` — 23 existing tests, all passing [VERIFIED: codebase execution]

### Secondary (MEDIUM confidence)
- L2-distance to cosine-similarity equivalence for L2-normalized vectors: `sqrt(2 - 2*cos_sim)` — standard linear algebra, `sqrt(2 - 2*0.85) = 0.5477` computed [VERIFIED: math]
- Phase 1 deferred code-review items WR-01, WR-05, IN-01 — sourced from `.planning/todos/pending/phase-01-code-review-deferred.md` [VERIFIED: codebase]

### Tertiary (LOW / ASSUMED)
- Default decay weights (W_RECENCY=0.4, W_REINFORCE=0.3, W_SALIENCE=0.3, LAMBDA=0.05) — reasonable starting point per build plan; requires empirical calibration in Phase 3/5 [ASSUMED]
- LLM Protocol staying single-method (`complete()`) being sufficient for Phase 4 adapters [ASSUMED]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages already installed, verified by test run
- Architecture: HIGH — all patterns are extensions of existing Phase 1 code; no speculative new tech
- Pitfalls: HIGH (aiosqlite transaction model, CONS-08 gate, cosine/distance threshold) / MEDIUM (StubLLM extraction fidelity for test fixtures)
- Decay formula: MEDIUM — formula is from the build plan; weights are assumed reasonable defaults requiring calibration

**Research date:** 2026-06-13
**Valid until:** 2026-07-13 (stable stack; no external dependencies changing)
