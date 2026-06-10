# Roadmap: MNEMA

## Overview

MNEMA is built inside-out. We write the record schema and the six ports first, ship local reference adapters (sqlite-vec + local FS + in-process scheduler), and prove the entire memory core — write path, consolidation, forgetting, recall — against those local adapters with zero cloud dependencies. The hardest correctness surface (consolidation/supersession) and the headline safety guarantee (a protected fact provably cannot be forgotten) both land while the system is small and fully deterministic. Only once the core is provably backend-agnostic do real cloud providers and storage backends land, each gated by the same conformance suite the local adapters already pass. A nutrition-coach reference demo and a before/after evaluation close the loop by consuming only the public SDK — proving the seam holds.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Schema, Ports & Local Core Foundation** - Scoped schema, six ports, local adapters, and `remember` + `recall(dense)` end-to-end on the local stack
- [ ] **Phase 2: Consolidation & Supersession** - Offline extraction, salience, entity resolution, active supersession, and provisional reconciliation
- [ ] **Phase 3: Forgetting, Salience Floor, Budget Packer & MCP** - Provable protected-fact survival, recoverable eviction, two-pass budget recall, T2 vault, and the MCP surface
- [ ] **Phase 4: Cloud Providers & Backends** - Real Qwen/Anthropic/Voyage adapters, pgvector/OSS/git backends, config factory, and conformance on ≥2 backends per axis
- [ ] **Phase 5: Reference Demo & Evaluation** - Nutrition-coach demo and a naive-vs-MNEMA before/after baseline

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
- [ ] 01-01-PLAN.md — Project scaffold, pytest harness, RED test stubs (Walking Skeleton)
- [ ] 01-02-PLAN.md — Pydantic schema, six Protocol ports, SqliteT1 + LocalFS adapters
- [ ] 01-03-PLAN.md — StubEmbedder, InProcessScheduler adapters
- [ ] 01-04-PLAN.md — WritePath, RecallPath, MemoryEngine, ScopedHandle, SDK re-export
- [ ] 01-05-PLAN.md — Full 5-test harness GREEN, schema unit tests, phase gate

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
**Plans**: TBD

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
**Plans**: TBD

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
**Plans**: TBD

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
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Schema, Ports & Local Core Foundation | 0/5 | In progress | - |
| 2. Consolidation & Supersession | 0/TBD | Not started | - |
| 3. Forgetting, Salience Floor, Budget Packer & MCP | 0/TBD | Not started | - |
| 4. Cloud Providers & Backends | 0/TBD | Not started | - |
| 5. Reference Demo & Evaluation | 0/TBD | Not started | - |
