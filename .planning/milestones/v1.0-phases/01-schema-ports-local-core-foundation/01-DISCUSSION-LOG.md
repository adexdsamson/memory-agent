# Phase 1: Schema, Ports & Local Core Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-10
**Phase:** 1-Schema, Ports & Local Core Foundation
**Areas discussed:** Scope model & recall boundary, Provisional-write trigger, Port seam granularity, SDK concurrency & API style
**Mode:** Advisor (research-backed comparison tables; calibration tier `full_maturity` from Vendor Philosophy = thorough-evaluator). Non-technical-owner framing suppressed: the `learning_style: guided` signal was overridden by overwhelming evidence of a technical owner; flagged to the user.

---

## Scope model & recall boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Kwargs wire + scope handle | Explicit required `user_id` kwargs as wire format + `engine.scope()` ergonomic surface | ✓ |
| Explicit kwargs only | Required kwargs on every call; no once-bound ergonomics | |
| Scope handle only | `engine.scope(...)` as sole surface (MCP still needs explicit path underneath) | |
| Constructor-bound client | `MnemaClient(user_id=)` — researched, rejected (per-user lifetime couples expensive adapters) | |
| Ambient contextvars | Researched, rejected (invisible boundary → silent wrong-scope recall) | |

**User's choice:** Kwargs wire + scope handle.
**Notes:** Recall-matching rule presented as locked-unless-objected and not objected: `user_id` = hard isolation boundary (always), `session_id` = stamped-not-filtered, `agent_id` = optional narrowing. Convergent across Mem0/Zep/Letta. `user_id` made non-defaulted (TypeError on omission); predicate enforced centrally in the store query builder.

---

## Provisional-write trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Heuristic + caller hint | Heuristic floor + caller `type`/`durable` override now; trained classifier seam deferred | ✓ |
| Add embedding-head now | Full layered stack incl. SetFit-style classifier in Phase 1 | |
| Embed-everything provisionally | No trigger; provisional-write every turn, prune in consolidation | |
| Flash-tier LLM micro-classify | Researched, rejected on write path (violates WRITE-03, breaks local path) | |

**User's choice:** Heuristic + caller hint (classifier deferred).
**Notes:** Bias trigger toward recall on safety/`fact` claims (missed allergy = highest-cost error), precision on `event` chit-chat. Embed-everything retained as a config fallback toggle. Deferred classifier reuses the embedding WRITE-02 already mandates but needs labeled data + versioned head artifact — too heavy for the foundation phase.

---

## Port seam granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Segregated role Protocols | `RecordStore` + `VectorIndex` now; `KeywordIndex`/`GraphStore`/`HybridSearch` additive later | ✓ |
| Fat T1Store, stub later methods | One port declaring all methods now; later ones raise NotImplementedError (ISP smell) | |
| Minimal T1Store, extend later | Small port now; each addition is a breaking Protocol change forcing every adapter | |
| Capability-flag introspection | `supports("hybrid")` — researched, unneeded (PG & SQLite both cover all of T1) | |

**User's choice:** Segregated role Protocols (ISP).
**Notes:** One physical adapter class satisfies multiple roles over one connection (typing seam, not deployment seam). Future hybrid work is purely additive — zero breaking change. Framed as one T1 "port family" to preserve CLAUDE.md's six-axis model. Static checking (pyright/mypy strict) enforces the contract. Precedent: LlamaIndex DocumentStore/VectorStore split, Mem0 vector-vs-history split.

---

## SDK concurrency & API style

| Option | Description | Selected |
|--------|-------------|----------|
| Async-first + Sans-I/O core | `async def` core; pure scoring/packing/decay kept synchronous & event-loop-free | ✓ |
| Sync-first | Sync core; MCP server offloads to threadpool | |
| Dual API via unasync codegen | Author async, generate sync (httpx/psycopg3 pattern) | |

**User's choice:** Async-first + Sans-I/O core.
**Notes:** Decisive factor = retrofit asymmetry (sync→async recolors the whole hand-rolled seam; async→sync is a trivial wrapper). Matches psycopg3's own author-async-generate-sync choice. Sync adapters (e.g. dashscope) wrapped in `asyncio.to_thread` at the leaf. Dual sync codegen deferred until a sync surface is a proven requirement.

---

## Claude's Discretion

- Heuristic cue lexicon/thresholds for the provisional trigger (tune against the harness).
- Record persistence representation (JSON-blob + projected columns vs normalized) and Pydantic single-source-of-truth placement.
- `aiosqlite` vs `sqlite3` + `asyncio.to_thread` for the local vector path.
- Buffer (in-memory per-session deque, K turns) and staging-queue representation on the local stack.

## Deferred Ideas

- Hybrid retrieval (BM25 / graph-expand / RRF — HYBRID-01/02/03, v2).
- Trained embedding-head classifier for the provisional-write trigger.
- Dual sync/async SDK surface via unasync-style codegen.
- Flash-tier LLM judgement of durable claims (belongs in Phase 2 consolidation).

All roadmap-tracked; none are Phase-1 scope creep — they are the surfaces the Phase-1 ports/seams are shaped to accommodate.
