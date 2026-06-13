# Phase 2: Consolidation & Supersession - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous) — all four grey areas returned **Claude's Discretion**; the recommended approaches below are the plan of record, at Claude's discretion to refine during planning provided the requirement guarantees (CONS-01…08, FORG-01) and the Phase-1 locked decisions (D-01…D-13) hold.

<domain>
## Phase Boundary

The slow, offline, **fully-local and deterministic** consolidation pipeline that turns raw T0 turns + provisional T1 records into clean, deduped, non-contradicting typed records. Covers: staged-turn draining, typed extraction, salience judging, safety pinning, entity resolution, active supersession of contradictions, in-place merge of refinements, provisional reconciliation by identity, idempotency, the CONS-08 protected-fact guarantee, and a `keep_score` decay computation (FORG-01).

**Out of scope (later phases):** eviction / salience-floor enforcement and the budget packer (Phase 3); real cloud LLM/embedding/storage providers (Phase 4); the MCP surface (Phase 3); the demo (Phase 5). Phase 2 computes `keep_score` but does NOT evict.
</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion (granted for all four areas — recommended direction recorded)

**Area 1 — LLM extraction (local + deterministic)**
- **D2-01:** Ship a deterministic **`StubLLM`** adapter behind the existing `LLMProvider` Protocol (mirrors the StubEmbedder hermetic-CI pattern). This satisfies "extract via the cheap LLM" while keeping Phase 2 fully local/deterministic; real Qwen/Claude adapters land in Phase 4 (honors D-06: the LLM's rightful home is offline consolidation, not the write path).
- **D2-02:** Extraction yields **0..N typed records per turn** (a turn may produce multiple facts or none).
- **D2-03:** **Safety/medical content is pinned `protected` + salience 1.0 by the Phase-1 content-driven rule** (`_SAFETY_KEYWORDS`), NEVER by trusting the LLM's salience judgment (D-05). See [[mnema-protected-flag-content-driven]]. The LLM judges salience for non-safety records only.
- **D2-04:** On reconciliation, **reuse the provisional record's existing embedding**; only embed newly-extracted records that had no provisional ancestor (CONS-06, cost discipline).

**Area 2 — Entity resolution & contradiction (CONS-03/04/05/08)**
- **D2-05:** "Same subject + same predicate" candidate match (CONS-03) via **dense cosine similarity over live records**, user-scoped (D-02) and narrowed by `record_type`; candidates above threshold are passed to the contradiction judge. (StubEmbedder is deterministic, keeping this hermetic.)
- **D2-06:** The (Stub)LLM judge returns a verdict **{contradict | refine | distinct}**; deterministic for seeded test fixtures.
- **D2-07:** Match threshold is a **tunable constant (~cosine 0.85)**, Claude's discretion to tune against fixtures; documented in code.
- **D2-08 (CONS-08 — load-bearing):** A **structural pre-check** gates supersession: if the matched live record is `protected` OR `record_type == FACT`, the pipeline **never auto-supersedes on an LLM contradiction alone** — it records a `contradiction_pending` graph edge / log and leaves the record live; only an explicit `forget()` supersedes it. Proven by a seeded contradiction test. This is the structural twin of the Phase-1 protected guarantee.

**Area 3 — Supersession transaction & idempotency (CONS-04/06/07)**
- **D2-09:** Supersession is **atomic in a single SQLite transaction**: set `valid_until` + `superseded_by` on the old record AND insert the `supersedes` graph edge together (also resolves code-review WR-05 atomicity).
- **D2-10:** Idempotency identity key is the **existing `t0_ref`** (`t0://session/offset`); the success criteria's `t0_id` refers to this — **no new schema column** (avoids an un-retrofittable column).
- **D2-11:** **Drain the staging queue + reconcile-by-`t0_ref`** yields idempotency regardless of crash timing; re-running consolidation upgrades the existing record rather than inserting a duplicate (CONS-07).
- **D2-12:** Provisional records are **upgraded in place** (clear the `provisional` flag), never deleted-and-reinserted and never duplicated into a parallel record (CONS-06).

**Area 4 — Decay pass & keep_score (FORG-01)**
- **D2-13:** Phase 2 **computes `keep_score` only** (`recency_decay(age) + reinforcement(access_count) + salience`, tunable weights); **eviction and the salience floor are Phase 3.**
- **D2-14:** `keep_score` is **computed on demand by a pure synchronous function** (D-12, sans-I/O so it's unit-testable without an event loop) and **NOT persisted** — it is derived data; persisting it would need an un-retrofittable column and couple weights to stored values.
- **D2-15:** Recency reference time = **`last_accessed` if set, else `created_at`**.
- **D2-16:** The decay computation is a **separate `decay()` step** invoked at the end of consolidation and reusable by the Phase-3 forgetting/packer path.

### Carried-forward locked decisions (Phase 1)
- D-11 async-first verbs/ports; D-12 sans-I/O pure logic for all salience/decay math; D-05/D-06 safety bias + LLM-in-consolidation; D-02/D-03 user_id hard isolation on every read/write; D-07/D-08 segregated role Protocols over one physical T1 adapter.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/mnema/core/engine.py` — `MemoryEngine.consolidate(force=False)` is a **stub** (only awaits `scheduler.trigger_now()`); the `asyncio.Queue` staging queue (`self._staging`) already receives `{turn, t0_ref}` dicts from `WritePath`.
- `src/mnema/core/write_path.py` — `_is_safety_claim(content)` + `_SAFETY_KEYWORDS` (content-driven safety detection) — **reuse directly** for D2-03 pinning.
- `src/mnema/core/schema.py` — `MemoryRecord` already has every column Phase 2 needs: `provisional`, `valid_until`, `superseded_by`, `salience`, `confidence`, `graph_edges` (for the `supersedes`/`contradiction_pending` edges), `t0_ref`, `access_count`, `last_accessed`. **No schema migration required.**
- `src/mnema/adapters/embedding/stub.py` — the deterministic-stub pattern to mirror for `StubLLM`.
- `src/mnema/adapters/vector_store/sqlite_t1.py` — `SqliteT1` (RecordStore+VectorIndex over one aiosqlite conn); dense `vector_search` for candidate matching; partial index `WHERE valid_until IS NULL` for "live records".
- `src/mnema/ports/llm.py` — `LLMProvider` Protocol exists (no adapter yet) — Phase 2 ships the first (`StubLLM`).

### Established Patterns
- Async Protocol ports + structural-typing adapters (D-08); pyright strict; pytest-asyncio (`asyncio_mode=auto`); hermetic stub providers; `--extra dev` for the test/type toolchain.
- Single aiosqlite connection, WAL, transactions for multi-write atomicity.

### Integration Points
- `consolidate()` verb (already on `MemoryEngine`) is the entry point; the scheduler (`InProcessScheduler`) already fires it.
- New `StubLLM` registers under `src/mnema/adapters/llm/`.
- Decay `keep_score` consumed by Phase 3 (forgetting + budget packer).

### Open code-review carryover
- `.planning/todos/pending/phase-01-code-review-deferred.md` — WR-05 (upsert/vector atomicity) is naturally addressed by D2-09's transaction; WR-01 (`get_latest` missing `valid_until IS NULL`) and IN-01 (`update()` can re-scope user) touch surfaces Phase 2 builds on — fold in if convenient.
</code_context>

<specifics>
## Specific Ideas

- The CONS-08 guarantee and the Phase-1 content-driven `protected` rule are the two load-bearing safety invariants — consolidation **must never clear `protected`** during re-classification (see [[mnema-protected-flag-content-driven]]).
- Determinism is a hard Phase-2 constraint (goal: "fully local and deterministic") — every test runs against `StubLLM` + `StubEmbedder`, no network, reproducible.
</specifics>

<deferred>
## Deferred Ideas

- Real cloud LLM extraction quality + flash-tier salience judging → Phase 4 (behind `LLMProvider`).
- Eviction, salience floor enforcement, budget-aware recall packer → Phase 3.
- Trained embedding-head classifier (D-04 deferred) → still deferred until the eval harness shows need.
</deferred>
