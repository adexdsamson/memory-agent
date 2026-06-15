# Phase 3: Forgetting, Salience Floor, Budget Packer & MCP - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous) — all four grey areas **Accepted as recommended**. The decisions below are locked for planning, at Claude's discretion only on tuning constants and MVP-depth tradeoffs, provided the requirement guarantees (FORG-02/03/04, RECALL-03/04/05, CONS-09, TIER-03, IFACE-02) and Phase 1–2 locked decisions hold.

<domain>
## Phase Boundary

Four capabilities layered over the now-complete local core: (1) deliberate, recoverable **forgetting/eviction** with a provable protected-fact guarantee; (2) **budget-aware recall** — relevance×salience×recency re-rank + a two-pass token-budget packer that reserves critical-fact slots; (3) **T2 canonical vault** promotion of stable records; (4) an **MCP server** exposing the five verbs as a thin wrapper over the same SDK `MemoryEngine`.

**Out of scope:** real cloud providers/backends (Phase 4); the nutrition-coach demo + eval baseline (Phase 5). Forgetting still runs on the local stack; eviction target is the local cold store.
</domain>

<decisions>
## Implementation Decisions

### Area 1 — Forgetting & eviction (FORG-02/03/04) [Accepted]
- **D3-01:** Eviction compares Phase-2 `keep_score` against a tunable module-level constant `KEEP_THRESHOLD` (≈0.3, Claude's discretion to tune). Evict iff `keep_score < KEEP_THRESHOLD AND not protected`.
- **D3-02:** Eviction target is the **T0/LocalFS cold store** — set `valid_until`, remove the vector from the index, and write a recoverable cold-store record. **No hard-delete path anywhere in the engine** (CLAUDE.md invariant).
- **D3-03 (FORG-03, load-bearing):** Protected records are skipped **before any score math** — eviction consumes `decay_pass` output, which already never yields protected records (Phase 2), so a protected record is unevictable **by construction**. Proven by a **Hypothesis property test** (`hypothesis` added as a dev dependency): for arbitrary generated record sets, assert no protected record is ever evicted. Not an example test.
- **D3-04:** Append-only **JSONL eviction audit** recording `{record_id, user_id, keep_score, evicted_at, reason}` — recoverable + auditable (FORG-04).

### Area 2 — Budget packer & re-rank (RECALL-03/04/05) [Accepted]
- **D3-05:** Re-rank score is the **multiplicative** blend `rank_score · salience · recency_decay` (pure sync, reuses the decay recency term; D-12). Tunable.
- **D3-06:** Token counting via a **pluggable counter** with a portable default approximation (tiktoken-style); the packer packs record `summary` fields under the caller-supplied budget (RECALL-04).
- **D3-07 (RECALL-05, load-bearing):** **Two-pass packer.** Pass 1 reserves slots for the critical set; Pass 2 fills the remaining budget by re-rank score. An **adversarial test** floods recall with a large off-topic history and asserts a protected/critical fact still appears in the packed output.
- **D3-08:** The reserved "active-constraint" set for Phase 3 = `protected ∪ (record_type == FACT, live)`. Claude's discretion to refine.

### Area 3 — T2 canonical vault (CONS-09, TIER-03) [Accepted]
- **D3-09:** New **`VaultStore` Protocol — the 6th adapter axis** (completes the LLM / Embedding / Object-T0 / T1 / **Vault-T2** / Scheduler model in CLAUDE.md). Static-checked Protocol per D-07/D-10; one LocalFS-backed adapter now.
- **D3-10:** LocalFS vault writes a **human-readable, git-versioned per-user markdown** user-model file (TIER-03), sectioned by `record_type`.
- **D3-11:** Promotion during consolidation: a **confirmed (non-provisional)** record above a salience threshold is promoted into T2 (CONS-09). Claude's discretion on the exact stability rule.
- **D3-12:** Vault dedup/merge by entity (subject+predicate) into canonical lines; MVP keeps it simple (dedup by summary/content).

### Area 4 — MCP server (IFACE-02) [Accepted]
- **D3-13:** **fastmcp 3.x** (stack pick) — a thin wrapper exposing `remember`/`recall`/`forget`/`consolidate`/`expand` as MCP tools that delegate to the same `MemoryEngine` (the SAME Python functions, per the architecture thesis). Add `fastmcp` dependency.
- **D3-14:** `user_id` is an **explicit, required MCP tool argument** (D-01/D-02/D-03 — non-defaulted hard isolation; the server calls the explicit-kwarg engine path, never ambient scope).
- **D3-15:** **stdio** transport for the MVP (local); the server is constructed over an injected `MemoryEngine` so it is testable in-process.
- **D3-16:** Tests use **FastMCP's in-process client** (no transport) — hermetic assertions that the tool surface exists and delegates to the engine.

### Carried-forward locked decisions
- D-11 async verbs/ports (FastMCP async tools + async adapters); D-12 sans-I/O pure logic for re-rank/keep_score/packing math; D-02/D-03 user_id hard isolation on every read/write incl. MCP tools; D-07/D-08/D-10 segregated Protocols, static-checked; the content-driven `protected` rule + CONS-08 supersession guard must remain intact (see [[mnema-protected-flag-content-driven]]).
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/mnema/core/decay.py` — `keep_score()` (pure sync) + `decay_pass()` (async generator that already skips protected) — the eviction pass consumes this directly (D3-03).
- `src/mnema/core/engine.py` — `forget()` is a stub ("set valid_until, move to T0 cold storage, clear from vector index, add to eviction audit log") — Phase 3 implements exactly that. `recall()` returns unranked dense+buffer union — Phase 3 adds re-rank + packer.
- `src/mnema/core/recall.py` — explicitly defers "No salience/recency re-ranking" and "No token-budget packing" to Phase 3.
- `src/mnema/adapters/object_store/local_fs.py` — LocalFS T0 adapter; the eviction cold-store + (new) vault markdown writer mirror its file-writing pattern.
- `src/mnema/adapters/vector_store/sqlite_t1.py` — has `live_records`, a vector-delete path is needed for eviction (remove from vec index); `supersede`/`valid_until` patterns from Phase 2.
- `src/mnema/core/consolidation.py` — promotion hook (CONS-09) attaches at the end of a consolidation pass (after confirm).
- `src/mnema/ports/` — six Protocols today; Phase 3 adds `vault.py` (VaultStore) as the 6th axis.

### Established Patterns
- Async Protocol + structural-typing adapters; pyright strict; pytest-asyncio (`asyncio_mode=auto`); hermetic stubs; `uv run --extra dev`; no hard DELETE (valid_until/cold-store).

### Integration Points
- `forget()` and the decay/eviction pass on `MemoryEngine`; `recall()` packer; consolidation promotion hook; new MCP server module (e.g. `src/mnema/mcp/server.py`) over the engine.
- New deps: `fastmcp` (runtime), `hypothesis` (dev).

### Open code-review carryover (fold in if convenient)
- `.planning/todos/pending/phase-01-code-review-deferred.md` (IN-01 update() re-scope guard touches the eviction/update surface).
- `.planning/todos/pending/phase-02-code-review-deferred.md` (WR-03 malformed-LLM handling — relevant once promotion uses the LLM).
</code_context>

<specifics>
## Specific Ideas
- FORG-03 demands an **invariant/property** proof, not an example — Hypothesis is the chosen tool. The protected-fact guarantee is the project's headline promise; this test is its proof.
- RECALL-05's two-pass reservation is the mechanism that makes "a large off-topic history cannot push a critical fact out of budget" true — the adversarial test is mandatory.
- The MCP server must be a **thin** wrapper — the same engine functions, no business logic duplicated in the tool layer.
</specifics>

<deferred>
## Deferred Ideas
- Real cloud Vault/object backends (OSS, git remote) and the OpenAI/Voyage/Qwen provider adapters → Phase 4.
- Hybrid retrieval (BM25 + graph + RRF) — the KeywordIndex/GraphStore/HybridSearch Protocols (HYBRID-01/02/03) remain a later additive phase.
- HTTP/SSE MCP transport and auth beyond explicit user_id → post-MVP.
</deferred>
