# Phase 5: Reference Demo & Evaluation - Research

**Researched:** 2026-06-15
**Domain:** SDK-consumer layer (demo + eval) over the complete MNEMA engine
**Confidence:** HIGH — all findings are derived from direct codebase inspection; no third-party library research required because no new dependencies are introduced.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D5-01:** CLI interactive chat + meal-planning loop (`python -m mnema.demo.coach`) on `build_engine(LocalConfig)`.
- **D5-02:** StubLLM by default — hermetic, deterministic, zero credentials. Real Qwen/Claude opt-in via config/env.
- **D5-03:** DEMO-02..05 are each a deterministic automated pytest scenario AND reproducible via the loop:
  - DEMO-02 cross-session: constraint in session 1 recalled in session 2 over the same persistent store.
  - DEMO-03 supersession: diet change retires old record, surfaces `valid_until`/`superseded_by` via `forget()` + consolidation.
  - DEMO-04 decay + protected: seeded backdated transient evicted then recovered; pinned allergy survives.
  - DEMO-05 budget packing: large history packed under budget with one verbatim `expand()`.
- **D5-04:** Meal planning is a deterministic, constraint-respecting suggestion from recalled facts.
- **D5-05:** Compare naive "stuff the whole T0 transcript" vs MNEMA `recall(budget=…)` on the same scripted probe suite.
- **D5-06:** Metrics: (a) protected-fact retention, (b) superseded-fact avoidance, (c) cross-session recall accuracy, (d) context tokens used.
- **D5-07:** Containment-based deterministic scoring — no LLM-answer grading.
- **D5-08:** Output `EVAL.md` with our own numbers + methodology.
- **D5-09:** Code in `src/mnema/demo/coach.py` + `src/mnema/eval/baseline.py` (+ tests under `tests/`).
- **D5-10:** Demo uses a fixed local sqlite + LocalFS data dir (not `:memory:`) for cross-session persistence.
- **D5-11:** MVP-proof polish — clear, scripted, reproducible behaviors + eval numbers.

### Carried-Forward Locked Decisions
- Uses `build_engine(LocalConfig)` + five async verbs + `ScopedHandle`. `pyright` strict; `pytest-asyncio`; `ruff`; `uv run --extra dev`.

### Claude's Discretion
- All three grey areas were accepted as recommended (smart-discuss autonomous mode).

### Deferred Ideas (OUT OF SCOPE)
- Real-LLM coach + LLM-graded answers.
- Web/GUI demo; real nutrition database; multi-user demo.
- Hybrid retrieval / extra providers.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEMO-01 | Interactive nutrition-coach app running on the engine (chat loop + meal planning) | `build_engine(LocalConfig)` + `ScopedHandle` are the exact entry point; `StubLLM` handles extraction deterministically |
| DEMO-02 | Cross-session recall — constraints from session 1 respected in session 2 | Persistent `LocalConfig` with fixed `sqlite_path` + `local_fs_path` reopens cleanly; see §Persistent Store Reopen below |
| DEMO-03 | Supersession — diet change retires old record, surfaces `valid_until`/`superseded_by` | `forget()` + `consolidate()` path documented; `_find_new_content_for_verdict` pattern from `test_consolidation.py` enables deterministic contradiction |
| DEMO-04 | Decay + protected fact — backdated transient evicted then recovered; pinned allergy survives | Direct `t1.upsert()` for backdating; `engine.evict()` + `LocalFS.archive()` + `engine.expand()` for recovery |
| DEMO-05 | Budget packing — large history packed under budget with one verbatim `expand()` | `recall(budget=N)` two-pass packer in `packer.py`; `TiktokenCounter` for token counting; `expand(record_id)` for verbatim Turn |
| EVAL-02 | Before/after baseline: naive full-transcript stuffing vs MNEMA `recall(budget)` on scripted probe suite | `TiktokenCounter` for both sides; containment-based metric compares context strings deterministically |
</phase_requirements>

---

## Summary

Phase 5 is a pure SDK consumer. It builds on top of the already-complete engine (Phases 1–4) without touching any engine internals. The entire phase is essentially a proof: wire `build_engine(LocalConfig)`, call the five verbs in scripted sequences, and assert the core value guarantees hold. No new runtime dependencies are needed — `tiktoken` (already in `pyproject.toml` core deps), `aiosqlite`, and the existing `StubLLM`/`StubEmbedder` cover everything.

The critical design surfaces in this phase are: (1) **persistent-store reopen** for DEMO-02 cross-session, (2) **deterministic supersession triggering** for DEMO-03 using the sha256-hash verdict mechanic of `StubLLM`, (3) **backdating records** for DEMO-04 through `t1.upsert()` with an explicit `created_at` in the past, and (4) **containment-based eval scoring** that avoids any LLM grading.

The main pitfall cluster is isolation: demo tests that share a persistent store must use separate tmp dirs per test function; `asyncio.Queue` state in the engine is not persisted across engine reopens; and `InProcessScheduler` consolidation must be driven manually via `engine.consolidate()` in tests rather than relying on the timer.

**Primary recommendation:** Write all four DEMO scenarios as async pytest functions under `tests/test_demo_scenarios.py`, sharing a `persistent_engine` fixture that constructs `LocalConfig(sqlite_path=str(tmp_path/"mnema.db"), local_fs_path=str(tmp_path/"t0"), vault_path=str(tmp_path/"vault"))`. Eval lives in a separate `tests/test_eval_baseline.py`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CLI chat loop | demo module (SDK consumer) | — | Pure user-facing I/O; calls engine verbs, presents results |
| Memory read/write | Engine (SDK) | — | All five verbs; coach never touches adapters directly |
| Cross-session persistence | LocalFS + SqliteT1 (storage adapters) | LocalConfig (factory) | Fixed `sqlite_path` file + fixed `local_fs_path` dir survive between engine instances |
| Supersession mechanics | ConsolidationPipeline (engine internals) | StubLLM (adapter) | Demo calls `forget()` + `consolidate()`; never directly manipulates supersession fields |
| Decay + eviction | decay_pass + engine.evict() (engine) | LocalFS.archive() (adapter) | Demo seeds backdated record via `t1.upsert()`; triggers eviction via `engine.evict()` |
| Budget packing | packer.py (engine core) | RecallPath | `recall(budget=N)` delegates; demo asserts result fits budget |
| Token counting (eval) | TiktokenCounter (packer.py) | ByteLengthCounter (fallback) | Already wired into RecallPath; reused directly in eval |
| Eval naive baseline | eval module (SDK consumer) | LocalFS.get() (T0 read) | Collects raw T0 turns to simulate "stuff the whole transcript" |

---

## Standard Stack

### Core (no new deps — everything already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mnema` (this project) | local | Engine SDK | The entire demo/eval is a consumer of the SDK |
| `tiktoken` | `>=0.13` (already pinned) | Token counting for eval budget metric | `TiktokenCounter` already shipped in `packer.py`; `cl100k_base` encoding [VERIFIED: src/mnema/core/packer.py] |
| `aiosqlite` | `>=0.22` (already pinned) | Persistent SQLite T1 reopen | The same `aiosqlite.connect(db_path)` used in `SqliteT1.open()` persists across engine instances when `db_path` is a real file path [VERIFIED: src/mnema/adapters/vector_store/sqlite_t1.py] |
| `pytest-asyncio` | `asyncio_mode=auto` | Async test runner | Already configured in `pyproject.toml` [VERIFIED: pyproject.toml] |

**No new `pyproject.toml` entries are required for Phase 5.**

---

## Architecture Patterns

### System Architecture Diagram

```
  CLI loop (coach.py)
       |
  build_engine(LocalConfig(...fixed paths...))
       |
  ScopedHandle.remember() / recall(budget=N) / forget() / consolidate() / expand()
       |
  MemoryEngine
    |          |           |
  WritePath  RecallPath  ConsolidationPipeline
    |           |             |
  SqliteT1   packer.py    StubLLM / decay_pass
  (file DB)  TiktokenCounter
    |
  LocalFS (local_fs_path)
    |          |
  T0 turns  archived.jsonl (cold store → expand() reads back)

  eval/baseline.py
    |         |
  LocalFS   TiktokenCounter
  .get()    .count()
  [naive    [MNEMA
   context]  context]
       |         |
  containment_check(context_str, probe_list)
```

### Recommended Project Structure
```
src/mnema/
├── demo/
│   ├── __init__.py
│   └── coach.py            # __main__ entrypoint; CLI chat + meal loop
├── eval/
│   ├── __init__.py
│   └── baseline.py         # probe suite + naive vs MNEMA comparison + EVAL.md writer
tests/
├── test_demo_scenarios.py  # DEMO-02..05 deterministic pytest scenarios
└── test_eval_baseline.py   # EVAL-02: before/after comparison
```

---

## Persistent-Store Reopen (DEMO-02)

**What it requires:** Two sequential engine instances over the same SQLite file and same `local_fs_path` dir, simulating session 1 → session 2.

**How it works** [VERIFIED: src/mnema/adapters/vector_store/sqlite_t1.py, src/mnema/config.py]:

1. `LocalConfig` defaults `sqlite_path=":memory:"` and `local_fs_path=tempfile.mkdtemp()`. For DEMO-02 you MUST override both:

```python
from pathlib import Path
import asyncio
from mnema.config import LocalConfig, build_engine

async def demo_cross_session(data_dir: Path):
    cfg = LocalConfig(
        sqlite_path=str(data_dir / "mnema.db"),
        local_fs_path=str(data_dir / "t0"),
        vault_path=str(data_dir / "vault"),
    )
    # Session 1
    engine1 = await build_engine(cfg)
    scope1 = engine1.scope(user_id="coach_user")
    await scope1.remember(
        "I am allergic to peanuts",
        session_id="session-1",
    )
    # CRITICAL: SqliteT1 has no explicit close() method.
    # The underlying aiosqlite connection is closed when the engine is GC'd
    # or when the aiosqlite context manager exits.
    # For tests: use `await engine1._t1._db.close()` directly.
    await engine1._t1._db.close()

    # Session 2 — new engine over the SAME files
    engine2 = await build_engine(cfg)
    scope2 = engine2.scope(user_id="coach_user")
    results = await scope2.recall("food allergies", budget=500)
    assert any("peanut" in r.content for r in results)
```

**Pitfall: `SqliteT1` has no `close()` public method.** [VERIFIED: src/mnema/adapters/vector_store/sqlite_t1.py — no `close()` defined]

The internal aiosqlite connection is `engine._t1._db`. In tests you call `await engine._t1._db.close()` explicitly before reopening the same file path. In the CLI demo, natural process exit flushes the WAL. The planner should include a Wave 0 task to add `SqliteT1.close()` as a thin wrapper around `await self._db.close()` — this is a missing but trivial public method.

**Pitfall: `asyncio.Queue` (staging queue) is not persisted.** [VERIFIED: src/mnema/core/engine.py line 127 — `self._staging: asyncio.Queue[Any] = asyncio.Queue()`]

Any turns staged but not yet consolidated are lost when `engine1` is discarded. For DEMO-02 this is fine: call `await engine1.consolidate()` before closing to flush provisional records to confirmed T1 records (persisted in SQLite), then close.

**Pitfall: `InProcessScheduler` is stateless.** [VERIFIED: src/mnema/config.py lines 113-119]

`build_engine` calls `await scheduler.start()` and `await scheduler.schedule(engine.consolidate, ...)` on every call. When you call `build_engine(cfg)` a second time, a fresh scheduler is wired — no conflict with the first. The scheduler state (job registrations) is per-process-instance, not persisted to the SQLite file.

**Pitfall: WAL checkpoint.** SQLite WAL mode (`PRAGMA journal_mode=WAL`, set in `SqliteT1.open()`) writes to a `-wal` sidecar. The WAL is checkpointed automatically on connection close with `aiosqlite`. Between `engine1` close and `engine2` open in the same test process, WAL is fully flushed because `aiosqlite.close()` invokes the SQLite `sqlite3_close()` which checkpoints the WAL. No explicit checkpoint call is needed.

---

## DEMO-03: Deterministic Supersession Mechanics

**The path** [VERIFIED: src/mnema/core/consolidation.py, src/mnema/adapters/llm/stub.py]:

Supersession for a non-protected preference record requires:
1. An existing confirmed record with content `A` (diet preference: "I prefer vegetarian food").
2. A new contradicting record with content `B` seeded so `StubLLM._judge(f"{A}\n{B}") == "contradict"`.
3. Entity resolution finds the existing record (same user_id, similar embedding via StubEmbedder — same content → same deterministic embedding → distance = 0).
4. `_apply_verdict("contradict", ...)` calls `record_store.supersede(old_id, new_record, embedding)` which atomically sets `valid_until + superseded_by` on the old record.

**StubLLM verdict formula** [VERIFIED: src/mnema/adapters/llm/stub.py lines 119-132]:

```python
import hashlib
def _verdict_for_pair(existing_content: str, new_content: str) -> str:
    body = f"{existing_content}\n{new_content}"
    h = int(hashlib.sha256(body.encode()).hexdigest(), 16) % 3
    return ["distinct", "refine", "contradict"][h]
```

**Finding a "contradict" pair** — use the helper pattern from `test_consolidation.py` [VERIFIED: tests/test_consolidation.py lines 45-58]:

```python
def _find_new_content_for_verdict(existing_content: str, target: str, prefix: str) -> str:
    for i in range(1000):
        candidate = f"{prefix}_{i}_{existing_content[:20]}"
        if _verdict_for_pair(existing_content, candidate) == target:
            return candidate
    raise RuntimeError("...")
```

Pre-compute the demo pair at module load time so the test never iterates at runtime:

```python
DIET_OLD = "I prefer vegetarian food"
DIET_NEW = _find_new_content_for_verdict(DIET_OLD, "contradict", prefix="diet_update")
# Verify in test: assert _verdict_for_pair(DIET_OLD, DIET_NEW) == "contradict"
```

**Critical constraint on entity resolution** [VERIFIED: src/mnema/adapters/embedding/stub.py + runtime-computed]: For the contradiction judge to fire, the entity resolution step (Step 5 of the pipeline) must find a near-match. `StubEmbedder` uses `sha256(text.encode()).digest()` → normalized float vector. Two different content strings produce different vectors. Empirically verified: `l2_dist(embed("spicy food preference item 0"), embed("diet_update_0_spicy food preference i")) = 0.724`, which is above `ENTITY_MAX_DISTANCE = 0.548`. Only **identical** content strings produce distance = 0, guaranteeing entity resolution fires.

**Required approach for DEMO-03:** Use identical content for both remember() calls. `StubLLM` with the body `f"{A}
{A}"` (same A) produces hash-deterministic verdict. Verified: `sha256("spicy food preference item 0
spicy food preference item 0") % 3 = 2` → "contradict". The same content seeded twice will: (1) distance = 0 → entity resolution fires, (2) judge returns "contradict", (3) old record superseded.

The demo must use `'spicy food preference item 0'` as the content string for the diet-preference record. Remembering it a second time (after consolidating the first) will deterministically trigger supersession. Do NOT use `'I prefer vegetarian food'` — that content produces verdict "refine" with itself (verified: `sha256("I prefer vegetarian food
I prefer vegetarian food") % 3 = 1`).

**What to assert on the superseded record** [VERIFIED: src/mnema/core/schema.py lines 78-79, src/mnema/adapters/vector_store/sqlite_t1.py lines 268-275]:

After `await engine.consolidate()`:
- Old record: `valid_until IS NOT NULL` (set to `now` in `supersede()`), `superseded_by = new_record.id`
- New record: `graph_edges` contains `{"rel": "supersedes", "target": old_record.id}`
- `await engine.t1.get(old_record_id)` returns the retired record with both fields set
- `await engine.recall("food preference")` does NOT return the old record (because `vector_search` filters `valid_until IS NULL`)

---

## DEMO-04: Backdating Records + Eviction + Cold-Store Recovery

### Backdating a Record

`MemoryRecord.created_at` has a Pydantic default factory `_utcnow()` [VERIFIED: src/mnema/core/schema.py line 88]. To backdate, pass an explicit `created_at` value:

```python
from datetime import datetime, timedelta, timezone
from mnema.core.schema import MemoryRecord, RecordType

past = datetime.now(timezone.utc) - timedelta(days=60)  # 60-day-old record
backdated = MemoryRecord(
    user_id="coach_user",
    session_id="seed-session",
    record_type=RecordType.PREFERENCE,
    content="I used to enjoy kale smoothies",
    summary="kale smoothie preference",
    salience=0.2,   # low salience → keep_score below KEEP_THRESHOLD=0.3
    protected=False,
    provisional=False,
    created_at=past,
    last_accessed=past,  # IMPORTANT: last_accessed drives recency (see decay.py L105)
)
```

Then write it directly to T1 — bypassing the write-path classifier (which would try to do a provisional write that consolidation would reconcile):

```python
# Option A: direct upsert (no embedding vector — won't appear in KNN, only in decay_pass)
await engine.t1.upsert(backdated)

# Option B: upsert_with_vector (appears in KNN results too)
embedding = (await engine._embedder.embed([backdated.content]))[0]
await engine.t1.upsert_with_vector(backdated, embedding)
```

Use Option B for DEMO-04 so the record is in both the record table and the vector index; this validates that eviction also removes it from the KNN index via `delete_vector`.

### Keep-Score Math for DEMO-04

[VERIFIED: src/mnema/core/decay.py]:

```
LAMBDA_DECAY = 0.05
W_RECENCY = 0.4, W_REINFORCE = 0.3, W_SALIENCE = 0.3
keep_score = W_RECENCY * exp(-0.05 * 60) + W_REINFORCE * log(1+0) + W_SALIENCE * 0.2
           = 0.4 * exp(-3.0) + 0.3 * 0 + 0.3 * 0.2
           = 0.4 * 0.0498 + 0 + 0.06
           = 0.0199 + 0.06 = 0.0799
```

`0.0799 < KEEP_THRESHOLD (0.3)` — confirmed, a 60-day-old record with salience=0.2 and zero accesses will be evicted. [VERIFIED: src/mnema/core/engine.py line 50 — `KEEP_THRESHOLD = 0.3`]

### Protected Record Survival

The allergy record must be seeded with `protected=True`. `decay_pass` explicitly skips protected records before calling `keep_score` [VERIFIED: src/mnema/core/decay.py line 156 — `if record.protected: continue`]. The demo should assert:
- After `engine.evict(user_id=...)` → the backdated transient count returned is >= 1
- After eviction → `engine.recall("allergy peanuts")` still returns the protected record
- After eviction → `engine.recall("kale smoothie")` returns 0 live results for that record

### Cold-Store Recovery via expand()

After eviction, the record is archived to `LocalFS`:
- `LocalFS.archive(record)` appends to `{local_fs_path}/archived.jsonl` [VERIFIED: src/mnema/adapters/object_store/local_fs.py lines 119-127]
- The archived record's `t0_ref` points to the original T0 turn (e.g. `t0://seed-session/0`)
- `engine.expand(record_id, user_id=...)` tries to fetch the T0 turn via `self._t0.get(record.t0_ref)`

**Important nuance:** `engine.expand()` fetches from the T0 turn log, NOT from `archived.jsonl`. The evicted record's `t0_ref` must therefore point to a valid T0 turn. This means the backdated record MUST have been originally written via `engine.remember()` (which appends to T0 via `LocalFS.append()`), or you must manually assign a valid `t0_ref` that exists in the T0 JSONL files.

**Simplest approach for DEMO-04:** For the transient record, call `engine.remember("I used to enjoy kale smoothies", ...)` normally (this creates a T0 turn + a provisional T1 record), then after consolidation get the record ID, then `await engine.t1.update(record_id, created_at=past, last_accessed=past, salience=0.2)` to backdate it in-place. This ensures the `t0_ref` is valid.

[VERIFIED: src/mnema/adapters/vector_store/sqlite_t1.py — `_ALLOWED_COLUMNS` includes `created_at`, `last_accessed`, `salience`]

---

## DEMO-05: Budget Packing + Verbatim Expand

### recall(budget=N) Behavior

[VERIFIED: src/mnema/core/recall.py lines 186-188, src/mnema/core/packer.py]:

```python
results = await scope.recall("meal plan", budget=200)
# Returns: pack_records(ranked, budget=200, TiktokenCounter())
# - Pass 1: all protected records included (even if budget exceeded)
# - Pass 2: fill remaining tokens with highest-ranked non-critical records
```

**Asserting "under budget"** — use `TiktokenCounter` directly:

```python
from mnema.core.packer import TiktokenCounter
counter = TiktokenCounter()
total_tokens = sum(counter.count(r.summary or r.content[:80]) for r in results)
assert total_tokens <= budget  # or <= budget + some slack for protected overflow
```

Note: protected records may cause `total_tokens > budget` by design (`pack_records` includes them unconditionally). The assertion should be `total_tokens <= budget + protected_overhead` or check that non-protected records alone are within budget.

**Seeding a "large history"** — seed N records (e.g. 20) via `remember()` + `consolidate()` so that without a budget, recall returns many records, but with `budget=200` only a subset fits. The protected allergy must appear in the budgeted result regardless.

### expand() Returning Verbatim Turn

[VERIFIED: src/mnema/core/engine.py lines 240-262]:

```python
turn = await scope.expand(record_id)
# Returns: Turn object with .content, .session_id, .created_at
# Scope check: record.user_id must == user_id (raises None, not ValueError)
# Returns None if record not found or scope mismatch or t0_ref is None
```

For DEMO-05, `expand()` should be called on a record that was written via `remember()` (has a valid `t0_ref`). Provisional records and directly-upserted records without a T0 turn will return `None`. Assert `turn is not None` and `turn.content == original_content`.

---

## EVAL-02: Containment-Based Eval Design

### Architecture

The eval compares two context-assembly strategies on the same scripted probe suite:

| Strategy | Assembly | Token count |
|----------|----------|-------------|
| **Naive baseline** | Concatenate ALL T0 turns for the user into one string | `TiktokenCounter().count(all_turns_joined)` |
| **MNEMA** | `recall(query=probe_query, budget=EVAL_BUDGET)` + format summaries | `sum(counter.count(r.summary) for r in results)` |

Both are run against the same seeded data and the same probe questions.

### Probe Suite Design

Each probe is a `(query, expected_retained: list[str], expected_excluded: list[str])` triple:

```python
PROBES = [
    # (a) protected-fact retention
    Probe(
        query="food allergies",
        must_contain=["peanut"],        # allergy must appear in MNEMA context
        must_not_contain=[],
        req_id="DEMO-04-protection",
    ),
    # (b) superseded-fact avoidance
    Probe(
        query="dietary preference",
        must_contain=["new_diet_content"],
        must_not_contain=["old_diet_content"],  # stale preference must be excluded
        req_id="DEMO-03-supersession",
    ),
    # (c) cross-session recall accuracy
    Probe(
        query="constraints from last session",
        must_contain=["session1_constraint"],
        must_not_contain=[],
        req_id="DEMO-02-cross-session",
    ),
    # (d) budget: tokens used (measured separately, not a containment check)
]
```

### Containment Metric

```python
def containment_check(context: str, must_contain: list[str], must_not_contain: list[str]) -> bool:
    contained = all(phrase.lower() in context.lower() for phrase in must_contain)
    excluded = all(phrase.lower() not in context.lower() for phrase in must_not_contain)
    return contained and excluded
```

### Naive Baseline — How to Assemble

The naive baseline requires reading ALL T0 turns for the user. `LocalFS` does not expose a `list_all_turns(user_id)` method; it organizes turns by session_id JSONL files. The baseline can:

Option A: Enumerate `{local_fs_path}/*.jsonl` files and read all turns [VERIFIED: src/mnema/adapters/object_store/local_fs.py — `_base = Path(base_dir)`, JSONL per session].

Option B: Use `engine.t1.get_live_records(user_id)` to get all live T1 records, then for each call `engine.expand(r.id)` to get the verbatim T0 content. This only gives records that have `t0_ref` set, but it's a faithful approximation of "stuffing the agent's known history."

**Recommended:** Option A (iterate JSONL files directly in `baseline.py`) for a true naive baseline that includes ALL raw turns, not just the ones that made it to T1.

### EVAL.md Output Format

```markdown
# MNEMA Eval Report — Phase 5

**Date:** {datetime.now().isoformat()}
**Method:** Containment-based deterministic scoring (no LLM grading)
**Suite:** {N} scripted probes

## Results

| Probe | Naive Passes | MNEMA Passes | MNEMA Tokens | Naive Tokens |
|-------|-------------|-------------|--------------|--------------|
| protected-fact retention | ✓/✗ | ✓ | N | M |
| superseded-fact avoidance | ✓/✗ | ✓ | N | M |
| cross-session recall | ✓/✗ | ✓ | N | M |

## Token Efficiency
- MNEMA budget: {EVAL_BUDGET}
- Average MNEMA tokens used: {avg_mnema}
- Average naive tokens: {avg_naive}
- Reduction: {reduction:.0f}%

## Methodology
[1-paragraph description: deterministic seeded data, StubLLM, containment check, no LLM grading]
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token counting for eval | Custom word-splitter | `TiktokenCounter` from `packer.py` | Already shipped; consistent with what `recall(budget=)` uses internally |
| Contradiction pair search | Manual string crafting | `_find_new_content_for_verdict()` pattern from `test_consolidation.py` | Uses the same SHA256 formula as `StubLLM._judge`; proven by existing tests |
| Async fixture for persistent engine | `asyncio.run()` inside test | pytest-asyncio with `asyncio_mode=auto` | Already configured; just use `async def test_...` |
| Backdating records via the write path | Patching `datetime.now` globally | Direct `t1.update(record_id, created_at=past, last_accessed=past)` | `_ALLOWED_COLUMNS` already includes both fields; no monkey-patching needed |

---

## Common Pitfalls

### Pitfall 1: Using `:memory:` or `tmpdir` defaults for DEMO-02 cross-session
**What goes wrong:** `LocalConfig()` with no args defaults `sqlite_path=":memory:"` and generates a fresh tmpdir for `local_fs_path`. Session 2's engine opens a completely empty database.
**How to avoid:** Always pass all three paths explicitly for any cross-session test. Verify by checking that `config.sqlite_path != ":memory:"`.
**Warning signs:** DEMO-02 test passes in isolation but the assertion `"peanut" in recall result` fails — the database is empty in engine 2.

### Pitfall 2: Forgetting to consolidate before closing engine 1 (DEMO-02)
**What goes wrong:** `remember()` writes to T0 and the staging queue. The staging queue is in-memory only. If you close engine 1 before consolidating, the provisional T1 record may not be flushed as confirmed. The `find_by_t0_ref` reconciliation on engine 2 won't find anything.
**How to avoid:** Call `await engine1.consolidate()` before `await engine1._t1._db.close()`.
**Warning signs:** Engine 2 recall returns records but they are `provisional=True` — the consolidation never ran.

### Pitfall 3: Entity resolution not firing for DEMO-03 supersession
**What goes wrong:** The two content strings produce distant embeddings from `StubEmbedder`, so `vector_search` returns them as separate entities and the judge is never called. Verdict is always "distinct", old record survives.
**How to avoid:** Use the same content string as both the first and second remember() content, OR use the pre-verified content pairs from `test_consolidation.py` (e.g., `'spicy food preference item 0'`). For the demo, identical content strings guarantee distance = 0 → entity resolution fires.
**Warning signs:** Old record `valid_until` is still `None` after consolidation.

### Pitfall 4: DEMO-03 with protected content accidentally hitting CONS-08
**What goes wrong:** If the supersession demo content contains safety keywords (allerg, anaphyl, etc.), `_is_safety_claim()` pins it as `protected=True` during extraction, and CONS-08 blocks supersession — recording `contradiction_pending` instead.
**How to avoid:** Use non-safety content strings for the diet-preference supersession demo (e.g., "spicy food preference", not "I am allergic to shellfish").
**Warning signs:** Old record stays live with `graph_edges` containing `contradiction_pending` — not `superseded_by`.

### Pitfall 5: expand() returning None for directly-upserted backdated records (DEMO-04)
**What goes wrong:** A record inserted via `t1.upsert()` with a manually crafted `MemoryRecord` has `t0_ref=None`. `engine.expand(record_id)` returns `None` when `record.t0_ref is None`.
**How to avoid:** For DEMO-04 cold-store recovery, seed the transient record via `engine.remember()` to get a valid `t0_ref`, THEN backdate it via `t1.update(record_id, created_at=past, last_accessed=past, salience=0.2)`.
**Warning signs:** `turn = await scope.expand(record_id)` returns `None` even though the record is archived.

### Pitfall 6: SqliteT1 has no public close() method
**What goes wrong:** Attempting `await engine.t1.close()` raises `AttributeError`.
**How to avoid:** Use `await engine._t1._db.close()` in tests (internal access). Add a `SqliteT1.close()` public method in Wave 0 of this phase.
**Warning signs:** AttributeError on `engine.t1.close()`.

### Pitfall 7: InProcessScheduler consolidation fires unexpectedly in tests
**What goes wrong:** The scheduler registered in `build_engine` fires `engine.consolidate` on a 3600-second interval. In tests this won't fire unless triggered. But if the test holds open a long-running event loop (e.g., integration test with explicit `await asyncio.sleep()`), a scheduler tick could fire mid-test.
**How to avoid:** Always trigger consolidation explicitly with `await engine.consolidate()`. Never rely on the scheduler timer firing in tests.

### Pitfall 8: Two-pass packer includes protected records even when budget is exceeded
**What goes wrong:** `pack_records` always includes `protected=True` records regardless of budget [VERIFIED: packer.py lines 196-201]. The token count of results may slightly exceed `budget` when protected records are large.
**How to avoid:** Assert `total_protected_tokens + remaining_tokens <= budget` rather than `total_tokens <= budget`. Or: assert that ALL protected records appear in the result, and that ALL remaining records collectively fit under `budget - protected_tokens`.

### Pitfall 9: Naive baseline JSONL scanning misses archived records
**What goes wrong:** `LocalFS.archive()` writes to `archived.jsonl`, not to the per-session JSONL files. A naive baseline that iterates `*.jsonl` files will include `archived.jsonl` and inflate the "naive context" with evicted records.
**How to avoid:** Exclude `archived.jsonl` and `eviction_audit.jsonl` when scanning session files. Only process files matching the `{session_id}.jsonl` pattern.

---

## Code Examples

### Pattern 1: Persistent engine pair for DEMO-02

```python
# Source: VERIFIED from src/mnema/config.py + src/mnema/adapters/vector_store/sqlite_t1.py
import pytest
from pathlib import Path
from mnema.config import LocalConfig, build_engine

@pytest.fixture
async def persistent_engine_factory(tmp_path):
    """Factory that returns build_engine(cfg) with fixed paths, plus close_first()."""
    data_dir = tmp_path / "mnema_data"
    data_dir.mkdir()
    cfg = LocalConfig(
        sqlite_path=str(data_dir / "mnema.db"),
        local_fs_path=str(data_dir / "t0"),
        vault_path=str(data_dir / "vault"),
    )

    async def make_engine():
        return await build_engine(cfg)

    async def close_engine(eng):
        await eng._t1._db.close()
        await eng._scheduler.shutdown()

    yield make_engine, close_engine


async def test_cross_session_recall(persistent_engine_factory):
    make_engine, close_engine = persistent_engine_factory

    # Session 1
    eng1 = await make_engine()
    scope1 = eng1.scope(user_id="demo_user")
    await scope1.remember("I am allergic to peanuts", session_id="s1")
    await eng1.consolidate()                  # flush staging queue to confirmed T1
    await close_engine(eng1)

    # Session 2 — same SQLite file, new engine instance
    eng2 = await make_engine()
    scope2 = eng2.scope(user_id="demo_user")
    results = await scope2.recall("food allergies", budget=500)
    assert any("peanut" in r.content for r in results)
    await close_engine(eng2)
```

### Pattern 2: Deterministic supersession for DEMO-03

```python
# Source: VERIFIED from tests/test_consolidation.py + src/mnema/adapters/llm/stub.py
import hashlib

def _verdict_for_pair(existing: str, new: str) -> str:
    body = f"{existing}\n{new}"
    h = int(hashlib.sha256(body.encode()).hexdigest(), 16) % 3
    return ["distinct", "refine", "contradict"][h]

def _find_contradict_pair(existing: str, prefix: str = "diet_update") -> str:
    for i in range(1000):
        candidate = f"{prefix}_{i}_{existing[:20]}"
        if _verdict_for_pair(existing, candidate) == "contradict":
            return candidate
    raise RuntimeError("No contradict pair found")

# Pre-compute at module level for zero runtime cost
DIET_OLD = "spicy food preference item 0"   # known to produce "contradict" with itself
DIET_NEW = DIET_OLD                          # same content = distance 0 = entity resolution fires
# Because StubLLM uses sha256(f"{A}\n{B}") and for A==B the hash hits index 2 ("contradict")
# Verify: assert _verdict_for_pair(DIET_OLD, DIET_NEW) == "contradict"
```

### Pattern 3: Backdating + eviction for DEMO-04

```python
# Source: VERIFIED from src/mnema/core/decay.py + src/mnema/adapters/vector_store/sqlite_t1.py
from datetime import datetime, timedelta, timezone

async def seed_backdated_transient(engine, user_id: str, session_id: str) -> str:
    """Seed a transient record, then backdate it so eviction fires."""
    # Step 1: normal remember() to get a valid t0_ref
    await engine.remember(
        "I used to enjoy kale smoothies",
        user_id=user_id,
        session_id=session_id,
    )
    await engine.consolidate()  # flush to confirmed T1
    # Step 2: find the record
    records = await engine.t1.get_live_records(user_id)
    kale_record = next(r for r in records if "kale" in r.content)
    # Step 3: backdate to 60 days ago with low salience
    past = datetime.now(timezone.utc) - timedelta(days=60)
    await engine.t1.update(
        kale_record.id,
        created_at=past,
        last_accessed=past,
        salience=0.2,
    )
    return kale_record.id


async def test_decay_and_recovery(persistent_engine_factory):
    make_engine, close_engine = persistent_engine_factory
    eng = await make_engine()
    scope = eng.scope(user_id="demo_user")

    # Seed allergy (protected=True via safety keyword detection)
    await scope.remember("I am allergic to peanuts", session_id="s1")
    # Seed backdated transient
    transient_id = await seed_backdated_transient(eng, "demo_user", "s1")

    # Evict
    evicted_count = await eng.evict(user_id="demo_user")
    assert evicted_count >= 1

    # Allergy survives
    allergy_results = await scope.recall("allergy")
    assert any("peanut" in r.content for r in allergy_results)

    # Transient is gone from live index
    live = await eng.t1.get_live_records("demo_user")
    assert not any("kale" in r.content for r in live)

    # Recover via expand (reads from T0 JSONL)
    turn = await scope.expand(transient_id)
    assert turn is not None
    assert "kale" in turn.content

    await close_engine(eng)
```

### Pattern 4: Token-budget assertion for DEMO-05

```python
# Source: VERIFIED from src/mnema/core/packer.py + src/mnema/core/recall.py
from mnema.core.packer import TiktokenCounter, ByteLengthCounter

EVAL_BUDGET = 300

async def test_budget_packing(engine):
    scope = engine.scope(user_id="demo_user")
    # Seed 20+ records
    for i in range(20):
        await scope.remember(f"meal fact {i}: I enjoy various foods item {i}", session_id="s1")
    await engine.consolidate()

    results = await scope.recall("meal history", budget=EVAL_BUDGET)
    counter = TiktokenCounter()
    protected_records = [r for r in results if r.protected]
    non_protected = [r for r in results if not r.protected]

    protected_tokens = sum(counter.count(r.summary or r.content[:80]) for r in protected_records)
    non_protected_tokens = sum(counter.count(r.summary or r.content[:80]) for r in non_protected)

    # Protected records always included (may slightly exceed budget)
    # Non-protected records fit within remaining budget
    assert non_protected_tokens <= EVAL_BUDGET

    # verbatim expand
    if results:
        turn = await scope.expand(results[0].id)
        # turn may be None if record has no t0_ref (directly consolidated from provisional)
        # For seeded records via remember(), t0_ref will be set
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global `datetime.now` monkey-patch for backdating | Direct `t1.update(id, created_at=past)` via `_ALLOWED_COLUMNS` whitelist | Phase 1 (schema design) | No global state mutation needed in tests |
| `StubLLM` always returns "distinct" | SHA256-hash verdict with explicit "contradict" for matching pairs | Phase 2 (consolidation) | Deterministic supersession tests without real LLM |
| Synchronous `sqlite3` | `aiosqlite` with WAL mode | Phase 1 | Concurrent reads safe; WAL checkpointed on `db.close()` |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A2 | `aiosqlite.close()` checkpoints the WAL fully before returning | DEMO-02 WAL pitfall | If WAL is not checkpointed, engine 2 may not see engine 1's writes [ASSUMED — sqlite3 docs say WAL is checkpointed on close but not verified against aiosqlite's asyncio wrapper] |
| A3 | `LocalFS` session filenames follow `{session_id}.jsonl` consistently | EVAL-02 naive baseline JSONL scanning | If naming changes, session file enumeration in baseline.py breaks [VERIFIED: local_fs.py line 78 `path = self._base / f"{session_id}.jsonl"`] |

> A1 (`StubEmbedder` is deterministic for identical content strings, distance = 0) was promoted to VERIFIED by direct code inspection and runtime computation.

> A3 is partially ASSUMED for `archived.jsonl` exclusion logic — the filename is hardcoded as `"archived.jsonl"` in `LocalFS.archive()` [VERIFIED: local_fs.py line 121], so the baseline scanner can reliably exclude it.

**Net unresolved assumptions:** A2 (WAL checkpoint behavior via aiosqlite wrapper).



---

## Open Questions (RESOLVED)

> Q1 (WAL checkpoint) → RESOLVED: Wave 0 (Plan 05-00 Task 1) adds an explicit `PRAGMA wal_checkpoint(FULL)` before `aiosqlite.close()` in `SqliteT1.close()`, so cross-session persistence does not rely on implicit WAL-flush behavior. Q2 (SqliteT1 needs a public `close()`) → RESOLVED: added in Wave 0 (Plan 05-00 Task 1).

1. **Does `aiosqlite.close()` reliably checkpoint the WAL in an asyncio context?**
   - What we know: CPython `sqlite3.close()` checkpoints the WAL by default. `aiosqlite` delegates all calls to a background thread.
   - What is unclear: Whether the thread-delegation path guarantees WAL flush before the coroutine returns.
   - Recommendation: Add an explicit `await engine._t1._db.execute("PRAGMA wal_checkpoint(FULL)")` before closing in the DEMO-02 fixture as a defensive measure.

2. **Does `SqliteT1` need a public `close()` method?**
   - What we know: No `close()` method exists on `SqliteT1` [VERIFIED].
   - Recommendation: Add `async def close(self) -> None: await self._db.close()` to `SqliteT1` in Wave 0.

---

## Environment Availability

Step 2.6: This phase is code-only; all runtime dependencies are the project own SDK. No new external tools.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| tiktoken | EVAL-02 token counting | checked | >=0.13 (pinned) | ByteLengthCounter (same file) |
| aiosqlite | DEMO-02 persistent SQLite | checked | >=0.22 (pinned) | none |
| sqlite-vec | SqliteT1 vector index | checked | >=0.1.9 (pinned) | none |
| pytest-asyncio | async test runner | checked | >=1.4 (dev dep) | none |

**Missing dependencies with no fallback:** None.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4.x |
| Config file | pyproject.toml [tool.pytest.ini_options] (asyncio_mode = auto) |
| Quick run command | `uv run --extra dev pytest tests/test_demo_scenarios.py -x -q` |
| Full suite command | `uv run --extra dev pytest -x -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEMO-01 | CLI coach entrypoint runs on build_engine(LocalConfig) | smoke | `pytest tests/test_demo_scenarios.py::test_coach_entrypoint -x` | no - Wave 0 |
| DEMO-02 | Constraint recalled in session 2 over same persistent store | integration | `pytest tests/test_demo_scenarios.py::test_cross_session_recall -x` | no - Wave 0 |
| DEMO-03 | valid_until + superseded_by set on old record after consolidation | integration | `pytest tests/test_demo_scenarios.py::test_supersession_surfaces_fields -x` | no - Wave 0 |
| DEMO-04 | Backdated transient evicted; allergy survives; expand() recovers turn | integration | `pytest tests/test_demo_scenarios.py::test_decay_protected_and_recovery -x` | no - Wave 0 |
| DEMO-05 | Budgeted recall fits under budget; expand() returns verbatim Turn | integration | `pytest tests/test_demo_scenarios.py::test_budget_packing_and_expand -x` | no - Wave 0 |
| EVAL-02 | MNEMA passes all probes; naive baseline fails superseded-avoidance probe | integration | `pytest tests/test_eval_baseline.py -x` | no - Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run --extra dev pytest tests/test_demo_scenarios.py tests/test_eval_baseline.py -x -q`
- **Per wave merge:** `uv run --extra dev pytest -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_demo_scenarios.py` -- covers DEMO-01..05
- [ ] `tests/test_eval_baseline.py` -- covers EVAL-02
- [ ] `src/mnema/demo/__init__.py` + `src/mnema/demo/coach.py` -- CLI entrypoint
- [ ] `src/mnema/eval/__init__.py` + `src/mnema/eval/baseline.py` -- eval harness
- [ ] `SqliteT1.close()` public method -- needed by DEMO-02 cross-session fixture

---

## Security Domain

Phase 5 adds no new attack surface, no new authentication paths, no new network endpoints.
All security controls are inherited from the engine (Phases 1-4).

| ASVS Category | Applies | Note |
|---------------|---------|------|
| V5 Input Validation | No | Demo uses hardcoded scripted inputs; no untrusted user content in eval harness |
| V2 Authentication | No | CLI demo; no auth surface added |
| V4 Access Control | No | Single-user demo; scope isolation enforced by engine |

---

## Sources

### Primary (HIGH confidence -- direct codebase inspection)

- `src/mnema/config.py` -- LocalConfig, build_engine(), sqlite_path default
- `src/mnema/core/engine.py` -- five verb signatures, evict(), consolidate(), expand(), KEEP_THRESHOLD=0.3
- `src/mnema/core/consolidation.py` -- _JUDGE_SENTINEL, _apply_verdict(), CONS-08 gate
- `src/mnema/adapters/llm/stub.py` -- SHA256 % 3 verdict formula
- `src/mnema/adapters/embedding/stub.py` -- SHA256-hash deterministic embedding formula (verified)
- `src/mnema/core/packer.py` -- TiktokenCounter, pack_records() two-pass, protected always included
- `src/mnema/core/recall.py` -- RecallPath.execute(), recall(budget=N) wiring
- `src/mnema/core/decay.py` -- keep_score() formula, KEEP_THRESHOLD, decay_pass() protected-skip
- `src/mnema/core/schema.py` -- MemoryRecord fields (created_at, last_accessed, valid_until, superseded_by)
- `src/mnema/adapters/vector_store/sqlite_t1.py` -- WAL pragma, no close(), _ALLOWED_COLUMNS, upsert_with_vector()
- `src/mnema/adapters/object_store/local_fs.py` -- archive() to archived.jsonl, append() to {session_id}.jsonl
- `tests/test_consolidation.py` -- _verdict_for_pair(), pre-verified content pairs
- `tests/conftest.py` -- fixture patterns
- `pyproject.toml` -- asyncio_mode=auto, tiktoken>=0.13 in core deps

### Tertiary (MEDIUM confidence -- runtime-computed in this session)

- StubEmbedder L2 distance between different-content strings: 0.724 > ENTITY_MAX_DISTANCE (0.548)
- StubLLM verdict for self-pair "spicy food preference item 0": SHA256 % 3 = 2 (contradict)
- StubLLM verdict for self-pair "I prefer vegetarian food": SHA256 % 3 = 1 (refine)
- keep_score for 60-day backdated transient (salience=0.2, access_count=0): 0.08 < 0.3

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new deps; read from pyproject.toml
- Architecture: HIGH -- all findings from direct code inspection of shipped engine
- Pitfalls: HIGH (DEMO-02/04/05) / MEDIUM (DEMO-03 entity resolution -- verified by runtime computation)
- Eval design: HIGH -- TiktokenCounter and LocalFS layout directly read

**Research date:** 2026-06-15
**Valid until:** Until engine internals change. Re-research if SqliteT1, packer.py, StubLLM, or StubEmbedder are modified.
