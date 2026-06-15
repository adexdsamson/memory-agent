# Roadmap: MNEMA

## Overview

MNEMA is built inside-out. We write the record schema and the six ports first, ship local reference adapters (sqlite-vec + local FS + in-process scheduler), and prove the entire memory core — write path, consolidation, forgetting, recall — against those local adapters with zero cloud dependencies. The hardest correctness surface (consolidation/supersession) and the headline safety guarantee (a protected fact provably cannot be forgotten) both land while the system is small and fully deterministic. Only once the core is provably backend-agnostic do real cloud providers and storage backends land, each gated by the same conformance suite the local adapters already pass. A nutrition-coach reference demo and a before/after evaluation close the loop by consuming only the public SDK — proving the seam holds.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Schema, Ports & Local Core Foundation** - Scoped schema, six ports, local adapters, and `remember` + `recall(dense)` end-to-end on the local stack (completed 2026-06-10)
- [x] **Phase 2: Consolidation & Supersession** - Offline extraction, salience, entity resolution, active supersession, and provisional reconciliation (completed 2026-06-14)
- [x] **Phase 3: Forgetting, Salience Floor, Budget Packer & MCP** - Provable protected-fact survival, recoverable eviction, two-pass budget recall, T2 vault, and the MCP surface (completed 2026-06-14)
- [ ] **Phase 4: Cloud Providers & Backends** - Real Qwen/Anthropic/Voyage adapters, pgvector/OSS/git backends, config factory, and conformance on ≥2 backends per axis
- [x] **Phase 5: Reference Demo & Evaluation** - Nutrition-coach demo and a naive-vs-MNEMA before/after baseline (completed 2026-06-15)

## Phase Details

### Phase 1: Schema, Ports & Local Core Foundation

**Goal**: A scope-isolated, typed memory engine that remembers and recalls (dense) end-to-end on a fully-local stack, with the safety-critical schema columns and capability-defined ports in place before any data is written.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: CORE-01, CORE-02, CORE-03, CORE-04, CORE-05, TIER-01, TIER-02, TIER-04, WRITE-01, WRITE-02, WRITE-03, WRITE-04, RECALL-01, RECALL-02, RECALL-06, RECALL-07, PROV-01, PROV-02, PROV-06, SCHED-01, SCHED-02, IFACE-01, EVAL-01
**Success Criteria** (what must be TRUE):

  1. Calling `remember` then `recall` through the SDK returns the stored fact, scoped to the caller's `user_id`/`agent_id`/`session_id` and never leaking across scopes.
  2. A durable-looking claim stated in a turn is recallable cross-session before any consolidation runs (provisional T1 write), and a same-session statement is recallable immediately via the buffer.
  3. The fast write path appends T0 + buffer + provisional T1 without ever blocking on a reasoning LLM, and every record persists scope ids, type, embedding provenance (`embedding_model`/`embedding_dim`/`embedding_version`), and a structural `protected` flag.
  4. The whole core runs against local adapters only (sqlite-vec + local FS + in-process scheduler with `trigger_now()`), with the LLM and embedding ports independently configurable and a 5-test harness green.
  5. `expand(id)` returns verbatim T0 detail and accessing a record updates `access_count`/`last_accessed`.

**Plans**: 5 plans

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Project scaffold, pytest harness, RED test stubs (Walking Skeleton)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Pydantic schema, six Protocol ports, SqliteT1 + LocalFS adapters
- [x] 01-03-PLAN.md — StubEmbedder, InProcessScheduler adapters

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-04-PLAN.md — WritePath, RecallPath, MemoryEngine, ScopedHandle, SDK re-export

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-05-PLAN.md — Full 5-test harness GREEN, schema unit tests, phase gate

### Phase 2: Consolidation & Supersession

**Goal**: The slow offline pipeline turns raw turns into clean, deduped, non-contradicting typed records — the highest-risk correctness surface — while still fully local and deterministic.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: CONS-01, CONS-02, CONS-03, CONS-04, CONS-05, CONS-06, CONS-07, CONS-08, FORG-01
**Success Criteria** (what must be TRUE):

  1. Consolidation drains the staging queue, extracts typed records via the cheap LLM, judges salience, and pins safety/medical content to `protected`.
  2. A contradicting claim actively supersedes the old record (sets `valid_until` + `superseded_by` + records a `supersedes` edge in the same transaction), while a non-contradicting refinement merges in place.
  3. Provisional records are reconciled by `t0_id` identity and upgraded in place — never re-extracted into a parallel duplicate — and re-running consolidation is idempotent (no duplicate live records, no dangling pointers).
  4. A protected/`fact`-type record is never auto-superseded on an LLM contradiction alone (it requires an explicit `forget`), proven by a seeded contradiction test.
  5. A decay pass computes `keep_score` (recency decay + reinforcement + salience) over all live records.

**Plans**: 5 plans

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — StubLLM adapter + RED test stubs for all 10 Phase 2 tests (walking skeleton)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — keep_score + decay_pass pure-sync module (TDD: RED → GREEN, FORG-01)
- [x] 02-03-PLAN.md — SqliteT1 new methods: supersede() + find_by_t0_ref() (CONS-04/06/07)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-04-PLAN.md — ConsolidationPipeline + engine.consolidate() wired (CONS-01..08, FORG-01)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 02-05-PLAN.md — All 10 tests GREEN + pyright phase gate (full suite: 33 tests passing)

### Phase 3: Forgetting, Salience Floor, Budget Packer & MCP

**Goal**: Deliberate, recoverable forgetting with a provable protected-fact guarantee, budget-aware recall that surfaces critical facts first, T2 promotion, and the MCP surface over the now-complete core.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: FORG-02, FORG-03, FORG-04, RECALL-03, RECALL-04, RECALL-05, CONS-09, TIER-03, IFACE-02
**Success Criteria** (what must be TRUE):

  1. Records below the keep threshold and not protected are evicted to cold storage — recoverable and auditable, with no hard-delete path anywhere in the engine.
  2. A protected record is skipped before any score math and survives every decay pass under any input, proven by an invariant/property test (not an example).
  3. `recall` re-ranks by relevance × salience × recency and packs summaries under a caller-supplied token budget, with a two-pass packer that reserves protected/active-constraint slots first so a large off-topic history cannot push a critical fact out of budget (verified by an adversarial test).
  4. Stable records are promoted into the T2 canonical vault (merged, deduped, human-readable user model).
  5. An MCP server exposes `remember`/`recall`/`forget`/`consolidate`/`expand` as a thin wrapper over the same SDK core.

**Plans**: 5 plans

Plans:
**Wave 0**

- [x] 03-00-PLAN.md — Phase 3 deps (fastmcp, tiktoken, hypothesis), VaultStore Protocol, RED test stubs (4 files)

**Wave 1** *(blocked on Wave 0 completion)*

- [x] 03-01-PLAN.md — engine.forget() + engine.evict() + LocalFS.append_audit() + KEEP_THRESHOLD (FORG-02/03/04)
- [x] 03-02-PLAN.md — packer.py (re_rank + TokenCounter + pack_records) + recall.py budget wiring (RECALL-03/04/05)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-03-PLAN.md — LocalFSVault + consolidation vault+eviction hooks + engine vault wiring (CONS-09, TIER-03)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-04-PLAN.md — MCP server + in-process tests GREEN + Phase 3 phase gate (IFACE-02)

### Phase 4: Cloud Providers & Backends

**Goal**: Real cloud providers and storage backends land behind the existing ports, each gated by the shared conformance suite, with a config factory wiring the documented default (Qwen + Alibaba) and a fully-local config.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: PROV-03, PROV-04, PROV-05, PROV-07, STORE-01, STORE-02, STORE-03, STORE-04, STORE-05, STORE-06, SCHED-03
**Success Criteria** (what must be TRUE):

  1. Qwen (DashScope) LLM + embedder, Anthropic (Claude) LLM, and a Claude-compatible embedder (Voyage and/or local) all ship and pass the conformance suite.
  2. The object store (OSS + local-FS), vector store (Postgres+pgvector + sqlite-vec), and a git-versioned markdown vault all sit behind their ports, with every adapter passing the shared conformance suite on ≥2 backends per axis.
  3. A config-keyed factory wires each axis from configuration, and both the documented default (Qwen + Alibaba) and the fully-local config run the same suite end-to-end.
  4. Switching embedders triggers an explicit reindex/migration path (with startup dim assertion) rather than a silent config flip.
  5. A generic cron scheduler adapter ships behind the scheduler port.

**Plans**: 9 plans

Plans:
**Wave 0**

- [x] 04-00-PLAN.md — Cloud optional-dependency extra + conformance fixture registry (pyproject.toml + conftest)

**Wave 1** *(blocked on Wave 0 completion)*

- [x] 04-01-PLAN.md — Conformance contract test stubs + RED test stubs (all 10 conformance + standalone files)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-02-PLAN.md — AnthropicLLM + QwenLLM cloud adapters (PROV-03/04)
- [x] 04-03-PLAN.md — VoyageEmbedder + QwenEmbedder adapters (PROV-05)
- [x] 04-04-PLAN.md — CronScheduler adapter (SCHED-03)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 04-05-PLAN.md — PostgresT1 adapter (STORE-02)
- [x] 04-06-PLAN.md — OSSS3Store adapter + moto_s3 fixture wiring (STORE-01)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 04-07-PLAN.md — build_engine() config factory + reindex_all() migration (STORE-03/04/05, PROV-07)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 04-08-PLAN.md — Phase gate: full hermetic suite GREEN + pyright + ruff

### Phase 5: Reference Demo & Evaluation

**Goal**: An interactive nutrition coach proves the engine end-to-end through the SDK alone, and a before/after baseline quantifies MNEMA against naive transcript-stuffing on the same suite.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: DEMO-01, DEMO-02, DEMO-03, DEMO-04, DEMO-05, EVAL-02
**Success Criteria** (what must be TRUE):

  1. The nutrition coach runs as an interactive chat + meal-planning loop on the engine and respects a constraint stated in an early session during a later session (cross-session recall).
  2. A diet change in the coach retires the old record and visibly surfaces `valid_until`/`superseded_by` (the supersession mechanism, not just the chat outcome).
  3. A seeded backdated transient is evicted then recovered while a pinned allergy survives the decay pass untouched (decay + protected fact), and a large history is packed under budget with one verbatim `expand` on demand.
  4. A before/after baseline compares naive "stuff the whole transcript" vs MNEMA on the same harness, reporting our own numbers with methodology.

**Plans**: 4 plans

Plans:
**Wave 0**

- [x] 05-00-PLAN.md — SqliteT1.close() gap fix + demo/eval package markers + RED test stubs (DEMO-01..05, EVAL-02)

**Wave 1** *(blocked on Wave 0 completion)*

- [x] 05-01-PLAN.md — DEMO-01..03 GREEN: coach entrypoint, cross-session recall, supersession surfaces fields

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-02-PLAN.md — DEMO-04..05 GREEN: decay+protected+recovery, budget packing+expand

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 05-03-PLAN.md — EVAL-02 GREEN: baseline.py + test_eval_baseline + EVAL.md report

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Schema, Ports & Local Core Foundation | 5/5 | Complete   | 2026-06-10 |
| 2. Consolidation & Supersession | 5/5 | Complete   | 2026-06-14 |
| 3. Forgetting, Salience Floor, Budget Packer & MCP | 5/5 | Complete   | 2026-06-14 |
| 4. Cloud Providers & Backends | 8/9 | In Progress|  |
| 5. Reference Demo & Evaluation | 4/4 | Complete   | 2026-06-15 |
