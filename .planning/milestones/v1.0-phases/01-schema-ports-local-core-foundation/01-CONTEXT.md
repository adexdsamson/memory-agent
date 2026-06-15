# Phase 1: Schema, Ports & Local Core Foundation - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning

<domain>
## Phase Boundary

A scope-isolated, typed memory engine that does `remember` + `recall(dense)` end-to-end on a **fully-local stack** (sqlite-vec + local FS + in-process scheduler with `trigger_now()`), with the safety-critical schema columns and the capability-defined ports in place **before any data is written**.

In scope: the v2 record schema (incl. `protected`, embedding provenance, scope ids), the six adapter ports, local reference adapters, the fast write path (T0 append + buffer push + provisional T1 write + staging enqueue), dense recall unioned with the buffer, `expand(id)`, access-count reinforcement, and a 5-test harness — all behind the importable SDK (IFACE-01).

Out of scope (later phases, do not pull in): consolidation/supersession (Phase 2), forgetting/decay/salience-floor/budget-packer/MCP server (Phase 3), cloud providers & backends + config factory (Phase 4), reference demo (Phase 5), and hybrid retrieval (BM25/graph/RRF — HYBRID-* are v2).
</domain>

<decisions>
## Implementation Decisions

These four were researched against MNEMA's constraints (advisor mode, `full_maturity` tier) and locked by the user. Each picked the researched recommendation.

### Scope Model & Recall Boundary
- **D-01 — Scope passing (layered):** Build **explicit required keyword args** as the load-bearing wire format — `remember(content, *, user_id, session_id, agent_id=None)`, `recall(query, *, user_id, agent_id=None)` — AND expose **`engine.scope(user_id=..., agent_id=None)`** as the ergonomic SDK front door (a thin view over one shared engine; the handle carries `user_id`/`agent_id`, `session_id` is passed per-`remember` as write-time provenance). The MCP server (Phase 3) calls the explicit-kwarg path directly off tool args; SDK users bind a scope once.
- **D-02 — Recall isolation rule (LOCKED):** `user_id` = the **hard isolation boundary**, a mandatory predicate on every read *and* write, composed with the existing partial index `WHERE valid_until IS NULL`. `session_id` = **stamped at write, never in the recall WHERE-clause** (this is what lets a session-1 allergy surface in session-5 recall). `agent_id` = **optional narrowing filter inside the user boundary**, never its own security domain. v1 is single-subject/single-tenant.
- **D-03 — Enforcement:** Make `user_id` a **non-defaulted** kwarg at the Protocol level (omission → `TypeError`, never a silent unscoped scan). Enforce the `user_id` predicate **centrally in the store's query builder**, not per caller, so no adapter or future tool can issue an unscoped read.
- **Rejected:** constructor-bound per-user client (couples expensive adapters/pools to a per-user lifetime — bad for a multi-user MCP process); `contextvars`/ambient scope (makes the isolation boundary invisible — a forgotten reset silently recalls the wrong user, the exact failure MNEMA sells against).

### Provisional-Write Trigger (`looks_like_durable_claim`)
- **D-04 — Phase-1 trigger:** Ship the **always-on heuristic floor** (first-person + stative-verb cues, no `?`, modal filtering) + **honor a caller-supplied hint** (`type=` / `durable=True`; the MCP `remember` contract already has an optional `type?` field) as an authoritative override. **Design the classifier seam but DEFER** the trained embedding-head (SetFit-style) until the eval harness shows the heuristic missing real durable claims.
- **D-05 — Error-cost bias:** Bias the trigger toward **recall on safety/`fact` claims** (a missed allergy is the highest-cost error in the system) and toward precision on `event` chit-chat (a false positive is just cheap noise that consolidation cleans up later).
- **D-06 — Boundaries:** Flash-tier LLM micro-classify is **rejected on the write path** (it is a reasoning-LLM round-trip → violates WRITE-03 and breaks the fully-local path; its rightful home is offline consolidation). Keep **embed-everything-provisionally as a config toggle** (safety net for tiny/short-lived deployments or if the heuristic underperforms).
- **Deferred classifier note:** when built, the embedding-head reuses the *single embedding WRITE-02 already mandates* (≈ a dot product, sub-ms, CPU, no API), but needs a labeled seed set + a versioned head artifact coupled to `embedding_dim` — hence deferred out of the foundation phase.

### Port Seam Granularity (the T1 axis)
- **D-07 — Segregated role Protocols (ISP):** Author **`RecordStore`** (typed-record CRUD) + **`VectorIndex`** (dense search) **now** (dense-only, as Phase 1 is scoped). Add **`KeywordIndex`** (HYBRID-01), **`GraphStore`** (HYBRID-02), **`HybridSearch`** (HYBRID-03) as **separate Protocols in their own phase** — purely additive, **zero breaking change** to existing adapters/consumers. This defeats the "adding a method forces every adapter to implement it at once" retrofit trap from the architecture-gotchas memo.
- **D-08 — Physical unity:** One physical adapter class structurally satisfies whichever roles are live over a single connection — e.g. `class SqliteT1(RecordStore, VectorIndex): ...` now, growing to `(…, KeywordIndex, GraphStore)` later. Split port = a **typing seam, not a deployment seam** (one backend still owns all of T1).
- **D-09 — Mental model:** Frame the T1 axis as **one "port family" of segregated roles** so the six-axis model in CLAUDE.md (LLM, Embedding, Object/T0, T1, Vault/T2, Scheduler) still reads as "six ports" even though T1 internally uses multiple role-Protocols.
- **D-10 — Enforcement:** Static checking (pyright/mypy strict, per CLAUDE.md) is the contract enforcement; reserve `@runtime_checkable` only if plugin-style capability discovery is later needed (runtime `isinstance` on Protocols is slow and checks method *presence*, not signatures).

### SDK Concurrency & API Style
- **D-11 — Async-first core:** `async def` for the five verbs (`remember`/`recall`/`forget`/`consolidate`/`expand`) and for every adapter Protocol method; sync consumers (tests, demo) call `asyncio.run(...)`. Native fit for FastMCP (async tools, Phase 3) and the async cloud backends (psycopg3 async pool, async provider clients, Phase 4); `asyncio.gather` over the future dense/sparse/graph lanes for RRF. Rationale: the retrofit asymmetry — **sync→async recolors the whole hand-rolled Protocol seam** (most expensive rework), async→sync is a trivial wrapper. This is psycopg3's own choice (author async, generate sync).
- **D-12 — Sans-I/O discipline:** Keep the **pure logic synchronous and event-loop-free** — scoring, budget packing (Phase 3), salience/decay math (Phase 2/3) — so the "provably never forgets a protected fact" invariant stays unit-testable without an event loop.
- **D-13 — Sync-adapter containment:** A sync-oriented dependency (e.g. dashscope in Phase 4, or `sqlite3` if `aiosqlite` isn't used) is wrapped in `asyncio.to_thread` **at the leaf inside its adapter**, hidden behind the async Protocol.
- **Deferred:** dual sync/async surface via `unasync`-style codegen — defer until a clean sync SDK surface is a *proven* hard requirement (cheap to add later; the codegen build step + CI gate aren't worth it now).

### Claude's Discretion
- Exact heuristic cue lexicon and thresholds for D-04 (tune against the harness).
- Record persistence representation (JSON-blob + projected index columns vs normalized columns) and where the Pydantic schema sits as single source of truth — planner/researcher call, constrained by D-07's role split and the cross-backend portability goal.
- Whether the local vector path uses `aiosqlite` vs `sqlite3` + `asyncio.to_thread` (D-13 governs either way).
- Buffer implementation details (in-memory per-session deque; K turns) and staging-queue representation on the local stack.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design source of truth (read first)
- `mnema-build-plan.md` — the origin v2 build plan. **§2 Tier-1 record schema** (the exact JSON record + `valid_until=null` semantics + index plan), **§3 the two phases** (fast online write pseudocode incl. `looks_like_durable_claim`, provisional write, staging), **§5 recall** (dense + buffer-union + access-count reinforcement; ignore the BM25/graph/RRF lines — those are later phases), **§6 MCP tool contracts** (`remember`/`recall`/`forget`/`consolidate` I/O shapes + `expand(id)`). Treat the pseudocode as a reference sketch, not literal API.
- `CLAUDE.md` — locked technology stack: Python 3.12+, hand-rolled Protocol adapters (NOT LiteLLM as the public seam), Pydantic 2.x record/config schema, sqlite-vec (local vector) + SQLite FTS5 (local keyword, later), local FS object store, APScheduler in-process scheduler, pytest + pytest-asyncio, pyright/mypy strict.

### Requirements & scope
- `.planning/REQUIREMENTS.md` — Phase-1 IDs: CORE-01..05, TIER-01/02/04, WRITE-01..04, RECALL-01/02/06/07, PROV-01/02/06, SCHED-01/02, IFACE-01, EVAL-01. (HYBRID-* are explicitly v2 — relevant only as the deferred surface D-07 keeps additive.)
- `.planning/ROADMAP.md` §"Phase 1" — goal + 5 success criteria (the goal-backward checklist for verification).
- `.planning/PROJECT.md` — Core Value, Constraints (independent LLM/embedding axes; freshness/no read-after-write hole; provable protected-fact survival), Out of Scope.

### Project memory (carried-forward constraints)
- Memory `mnema-architecture-gotchas` — inside-out build order; schema columns that can't be retrofitted; `protected` is **structural, not a salience threshold** (decay skips protected *before* any score math); independent LLM/embedding axes (normalize-at-adapter, assert dim at startup).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Greenfield** — no source code exists yet (only `CLAUDE.md`, `mnema-build-plan.md`, and `.planning/`). This is the first implementation phase; it establishes the patterns later phases reuse.

### Established Patterns
- None in-code yet. The intended patterns are documented (not yet coded): hand-rolled `typing.Protocol` adapters per axis; Pydantic record schema as the typed contract; the partial-index-on-`valid_until IS NULL` hot-path convention.

### Integration Points
- This phase defines the seams everything downstream plugs into: the six ports (LLMProvider, EmbeddingProvider, ObjectStore/T0, the T1 port family [RecordStore + VectorIndex now], Vault/T2 stub-or-defer, Scheduler) and the five-verb async SDK surface. Phase 2 consolidation depends on `RecordStore & VectorIndex`; Phase 3 forgetting iterates live records; Phase 4 cloud adapters re-implement these same Protocols against the shared conformance suite.
</code_context>

<specifics>
## Specific Ideas

- **Scope-naming trap to avoid:** Mem0's docs say `session_id` but its API parameter is actually `run_id` (mem0 issue #3855). MNEMA picks **`session_id`** and keeps it consistent across SDK + (future) MCP — no aliasing.
- **Reference-library convergence** on the recall rule (D-02): Mem0 ("always provide at least a `user_id`; it returns all that user's memories across runs/sessions"), Zep ("all sessions for a user feed one unified user-level graph"), Letta — all use `user_id` as the boundary and session/run as recorded-not-filtered. MNEMA adopts this directly.
- **Decomposition precedent** for D-07: LlamaIndex separates `BaseDocumentStore` from `VectorStore` even when one backend serves both; Mem0 separates `VectorStoreBase` from its SQLite history store. One backend, split interface.
</specifics>

<deferred>
## Deferred Ideas

All deferrals below are **already roadmap-tracked** — captured here so the seam is designed for them without pulling them into Phase 1:

- **Hybrid retrieval** (BM25 keyword, 1-hop graph-expand, RRF fusion — HYBRID-01/02/03, v2): D-07 keeps `KeywordIndex`/`GraphStore`/`HybridSearch` as additive Protocols so this lands without breaking adapters.
- **Trained embedding-head classifier** for the provisional-write trigger (per D-04): build when eval shows the heuristic missing durable claims.
- **Dual sync/async SDK surface** via `unasync`-style codegen (per D-11): add only when a clean sync surface is a proven requirement.
- **Flash-tier LLM judgement of durable claims** (rejected on the write path per D-06): belongs in Phase 2 offline consolidation, not the fast write path.

None of these are scope creep into Phase 1 — they are the future-facing surfaces the Phase-1 ports/seams are deliberately shaped to accommodate.
</deferred>

---

*Phase: 1-Schema, Ports & Local Core Foundation*
*Context gathered: 2026-06-10*
