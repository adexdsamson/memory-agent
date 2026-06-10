---
phase: 01-schema-ports-local-core-foundation
verified: 2026-06-10T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 1: Schema, Ports & Local Core Foundation Verification Report

**Phase Goal:** A scope-isolated, typed memory engine that remembers and recalls (dense)
end-to-end on a fully-local stack, with the safety-critical schema columns and
capability-defined ports in place before any data is written.
**Verified:** 2026-06-10
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | Calling `remember` then `recall` through the SDK returns the stored fact, scoped to user_id/agent_id/session_id and never leaking across scopes | VERIFIED | `test_remember_and_recall_scoped` + `test_recall_does_not_leak_across_users` + `test_user_id_required_kwarg` — all GREEN. `vector_search` has mandatory `user_id` kwarg; `RecallPath` passes it; `as_candidates_for_user` enforces user-only buffer reads. |
| SC-2 | A durable-looking claim stated in a turn is recallable cross-session before any consolidation runs (provisional T1 write), and a same-session statement is recallable immediately via the buffer | VERIFIED | `test_cross_session_provisional_recall` + `test_within_session_buffer_freshness` GREEN. WritePath writes provisional T1 on classifier match; `RecentSessionBuffer` keyed by `(user_id, session_id)` with `as_candidates_for_user` providing cross-session reads. |
| SC-3 | The fast write path appends T0 + buffer + provisional T1 without ever blocking on a reasoning LLM, and every record persists scope ids, type, embedding provenance, and a structural `protected` flag | VERIFIED | `test_fast_write_schema_columns` GREEN. `WritePath` has no `LLMProvider` injection at all — physically impossible to call LLM. `MemoryRecord` has `embedding_model`, `embedding_dim`, `embedding_version`, `protected: bool`, and all scope fields confirmed present by `test_un_retrofittable_columns_present`. |
| SC-4 | The whole core runs against local adapters only (sqlite-vec + local FS + in-process scheduler with `trigger_now()`), with the LLM and embedding ports independently configurable and a 5-test harness green | VERIFIED | 23 tests pass (`uv run --extra dev pytest tests/ -q`: `23 passed in 1.26s`). `EmbeddingProvider` and `LLMProvider` are separate Protocols. `StubEmbedder` satisfies `EmbeddingProvider` structurally. `SqliteT1 + LocalFS + InProcessScheduler` are the full local stack. sqlite-vec extension confirmed loaded (`v0.1.9` on Windows). |
| SC-5 | `expand(id)` returns verbatim T0 detail and accessing a record updates `access_count`/`last_accessed` | VERIFIED | `test_expand_and_access_count` asserts `t0_ref is not None`, then calls `expand()` unconditionally and asserts `turn.content == "I batch-cook on Sundays"`. `RecallPath` increments `access_count` in store and on in-memory object after each recall. |

**Score: 5/5 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mnema/core/schema.py` | MemoryRecord with all un-retrofittable columns | VERIFIED | `MemoryRecord` has CORE-01/02/03/04/05 columns: scope ids, RecordType StrEnum, embedding provenance (3 fields), `protected: bool`, `valid_until: Optional[datetime]`, `access_count`, `last_accessed`, `t0_ref`. |
| `src/mnema/ports/embedding.py` | EmbeddingProvider Protocol (PROV-02) | VERIFIED | Protocol with `dim: int` property and `async embed()`. Docstring explicitly documents independent-axis design. |
| `src/mnema/ports/llm.py` | LLMProvider Protocol (PROV-01) | VERIFIED | Separate Protocol with `async complete()`. Not injected into `WritePath` — LLM/embedding axes are independently configurable. |
| `src/mnema/ports/object_store.py` | ObjectStorePort Protocol (TIER-01) | VERIFIED | `append/get/archive` methods. `append` returns `t0://` ref. `get` backs `expand()`. |
| `src/mnema/ports/record_store.py` | RecordStore Protocol (TIER-02) | VERIFIED | `upsert/get/update/live_records`. `live_records` async-iterates `valid_until IS NULL` records (CORE-05). |
| `src/mnema/ports/vector_index.py` | VectorIndex Protocol (TIER-02) | VERIFIED | `upsert_vector/vector_search/delete_vector`. `vector_search` has `user_id` as non-defaulted kwarg (D-02 isolation). |
| `src/mnema/ports/scheduler.py` | Scheduler Protocol (SCHED-01) | VERIFIED | CR-01 fix confirmed: all four methods are `async def`. `trigger_now()` fires immediately in tests. |
| `src/mnema/adapters/vector_store/sqlite_t1.py` | SqliteT1 local T1 adapter (TIER-02) | VERIFIED | Satisfies both `RecordStore` and `VectorIndex` by structural typing. Partial index `idx_t1_live_user WHERE valid_until IS NULL` in DDL (CORE-05). `vec0` virtual table for KNN. |
| `src/mnema/adapters/object_store/local_fs.py` | LocalFS T0 adapter (TIER-01) | VERIFIED | JSONL per session, append-only. Returns `t0://session_id/offset` ref. session_id validated against alphanumeric/hyphen/underscore allowlist. |
| `src/mnema/adapters/embedding/stub.py` | StubEmbedder (PROV-01/02) | VERIFIED | Hash-based deterministic L2-normalized embedder. `dim` property. Satisfies `EmbeddingProvider` structurally. |
| `src/mnema/adapters/scheduler/in_process.py` | InProcessScheduler (SCHED-02) | VERIFIED | APScheduler 3.x pinned `<4`. `trigger_now()` sets `next_run_time=datetime.now()`. `test_trigger_now_fires_consolidate` GREEN. |
| `src/mnema/core/write_path.py` | WritePath — fast write (WRITE-01/02/03/04) | VERIFIED | Step 1: T0 append. Step 2: buffer push (sync). Step 3: embed + provisional T1 (no LLM). Step 4: staging queue enqueue. No `LLMProvider` injected at all. |
| `src/mnema/core/recall.py` | RecallPath — dense+buffer recall (RECALL-01/02/07) | VERIFIED | Dense KNN via `vector_search` (RECALL-01), union with buffer via `as_candidates_for_user` (RECALL-02), access_count increment (RECALL-07), content-based dedup so a same-session fact is never returned twice. |
| `src/mnema/core/engine.py` | MemoryEngine + ScopedHandle (IFACE-01) | VERIFIED | Five-verb engine. `remember`/`recall`/`expand`/`forget`/`consolidate`. `scope()` returns `ScopedHandle`. PROV-06 startup dim assertion present. `forget` and `consolidate` are documented stubs for Phase 3/2. |
| `src/mnema/core/buffer.py` | RecentSessionBuffer (TIER-04) | VERIFIED | Keyed by `(user_id, session_id)`. `as_candidates_for_user` filters strictly by `user_id`. Bounded deque with `maxlen=k`. |
| `src/mnema/core/classifier.py` | Durable-claim classifier (WRITE-02) | VERIFIED | First-person stative regex, question/modal suppression. Pure logic, zero imports except `re`. |
| `src/mnema/__init__.py` | SDK re-export (IFACE-01) | VERIFIED | `from mnema import MemoryEngine, ScopedHandle` — two public names. |
| `tests/test_remember_recall.py` | 5 remember/recall tests covering SC-1..SC-5 | VERIFIED | 6 test functions (5 + dedup test). All GREEN. |
| `tests/test_scope_isolation.py` | Scope isolation tests | VERIFIED | Cross-user leak test + TypeError-on-missing-user_id. Both GREEN. |
| `tests/test_schema.py` | Schema unit tests (CORE-02/03/04/05) | VERIFIED | 7 synchronous Pydantic tests. All GREEN. Locks un-retrofittable column contract. |
| `tests/test_write_path.py` | Write path + CR-04 safety fix tests | VERIFIED | 4 tests including `test_allergy_is_protected_without_type_hint` and `test_safety_claim_forces_durable_write`. All GREEN. |
| `tests/test_providers.py` | PROV-06 dim-mismatch test | VERIFIED | `test_dim_mismatch_raises_at_startup` GREEN. |
| `tests/test_scheduler.py` | SCHED-02 trigger_now test | VERIFIED | `test_trigger_now_fires_consolidate` GREEN with `asyncio.sleep(0.2)` to allow dispatch. |
| `tests/test_sdk_interface.py` | IFACE-01 public surface test | VERIFIED | `test_public_surface_importable` + `test_engine_scope_returns_scoped_handle` GREEN. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `WritePath.execute` | `ObjectStorePort.append` | `await self._t0.append(session_id, turn)` | WIRED | `t0_ref` returned and stored on `MemoryRecord.t0_ref` |
| `WritePath.execute` | `EmbeddingProvider.embed` | `await self._embedder.embed([content])` | WIRED | Called before provisional T1 write; LLM never called |
| `WritePath.execute` | `RecordStore.upsert` | `await self._record_store.upsert(record)` | WIRED | Provisional T1 record written with all schema columns |
| `WritePath.execute` | `VectorIndex.upsert_vector` | `await self._vector_index.upsert_vector(record.id, embedding)` | WIRED | Vector stored for dense KNN |
| `WritePath.execute` | `RecentSessionBuffer.push` | `self._buffer.push(turn, session_id, user_id)` | WIRED | Sync push; freshness guarantee for same-session recall |
| `RecallPath.execute` | `VectorIndex.vector_search` | `await self._vector_index.vector_search(q_vec, k, user_id=user_id)` | WIRED | user_id is non-defaulted keyword arg; always scope-filtered |
| `RecallPath.execute` | `RecentSessionBuffer.as_candidates_for_user` | `self._buffer.as_candidates_for_user(user_id)` | WIRED | User-scoped buffer reads; no cross-user leak |
| `RecallPath.execute` | `RecordStore.update` | `await self._record_store.update(record.id, access_count=..., last_accessed=...)` | WIRED | access_count incremented + persisted for all T1 results |
| `MemoryEngine.expand` | `RecordStore.get` then `ObjectStorePort.get` | scope check on user_id, then `await self._t0.get(record.t0_ref)` | WIRED | Scope guard: returns None if user_id mismatch; tested unconditionally |
| `MemoryEngine.consolidate` | `Scheduler.trigger_now` | `await self._scheduler.trigger_now()` | WIRED | CR-01 fix: direct await, no iscoroutine branching |
| `MemoryEngine.__init__` | PROV-06 dim assertion | `if hasattr(t1, "_dim") and embedder.dim != t1._dim: raise ValueError` | WIRED | Works because SqliteT1 exposes `_dim`; uses private attr (WR-04 deferred) |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `RecallPath.execute` | `dense_hits` | `SqliteT1.vector_search` → sqlite-vec KNN JOIN t1_records | Yes — real SQLite/sqlite-vec query with user_id scope | FLOWING |
| `RecallPath.execute` | `t1_records` | `SqliteT1.get(record_id)` for each dense hit | Yes — SELECT * FROM t1_records WHERE id = ? | FLOWING |
| `RecallPath.execute` | `buffer_turns` | `RecentSessionBuffer.as_candidates_for_user` | Yes — in-memory deque, populated by WritePath.execute | FLOWING |
| `MemoryEngine.expand` | `Turn` | `LocalFS.get(t0_ref)` → reads JSONL file at computed offset | Yes — reads real file written by `append()` | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CR-04: allergy without type_hint gets `protected=True` | `uv run python -c "..."` inline smoke test | `protected=True, type=bool` confirmed | PASS |
| SC-1: u2 cannot see u1's records | Inline smoke test | `u2 sees 0 records` | PASS |
| SC-5: expand returns verbatim content | Inline smoke test | `turn.content='I am allergic to peanuts'` | PASS |
| CORE-03: embedding provenance set at write | Inline smoke test | `embedding_model=StubEmbedder, dim=128` | PASS |
| Full test suite | `uv run --extra dev pytest tests/ -q` | `23 passed in 1.26s` | PASS |
| Pyright strict | `uv run --extra dev pyright` | `0 errors, 0 warnings, 0 informations` | PASS |
| Ruff lint | `uv run --extra dev ruff check src/ tests/` | `All checks passed!` | PASS |

---

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` files in repository; phase relies on pytest suite as the gate.

---

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| CORE-01 | Scope ids on every record, all reads filter by scope | SATISFIED | `MemoryRecord` fields; `vector_search` mandatory `user_id`; `live_records` takes `user_id` |
| CORE-02 | Typed record (StrEnum), full v2 schema | SATISFIED | `RecordType` StrEnum with 4 values; `MemoryRecord` has all fields |
| CORE-03 | Embedding provenance (model/dim/version) | SATISFIED | Three `Optional` fields on schema; WritePath sets all three from embedder |
| CORE-04 | Structural `protected: bool` independent of salience | SATISFIED | `protected: bool = False` on schema; `_is_safety_claim` sets it content-driven, no type_hint gate |
| CORE-05 | Partial index: only `valid_until IS NULL` on hot path | SATISFIED | `_DDL_IDX_LIVE_USER` with `WHERE valid_until IS NULL`; `vector_search` adds `AND r.valid_until IS NULL` |
| TIER-01 | T0 append-only cold object store | SATISFIED | `LocalFS` JSONL append; `ObjectStorePort` Protocol |
| TIER-02 | T1 working memory with vector index | SATISFIED | `SqliteT1` implements `RecordStore + VectorIndex`; sqlite-vec KNN |
| TIER-04 | Recent-session buffer (last K turns) | SATISFIED | `RecentSessionBuffer` bounded deque keyed by (user_id, session_id) |
| WRITE-01 | T0 append + buffer push at zero model cost | SATISFIED | `WritePath` step 1+2; always executed regardless of classifier |
| WRITE-02 | Durable claim → provisional T1 with embedding (recallable cross-session) | SATISFIED | `WritePath` step 3; `looks_like_durable_claim` classifier |
| WRITE-03 | Fast path never blocks on reasoning LLM | SATISFIED | `LLMProvider` not injected into `WritePath` at all |
| WRITE-04 | Turn enqueued to staging queue for deferred extraction | SATISFIED | `await self._staging_queue.put({"turn": turn, "t0_ref": t0_ref})` |
| RECALL-01 | Embed query, dense vector search over live records | SATISFIED | `RecallPath` embeds query, calls `vector_search` with `valid_until IS NULL` filter |
| RECALL-02 | Union vector results with buffer, buffer-wins dedup | SATISFIED | Content-based dedup in `RecallPath`; T1 record wins over buffer turn |
| RECALL-06 | `expand(id)` returns verbatim T0 detail | SATISFIED | `MemoryEngine.expand` reads `t0_ref` from T1 record, fetches from `LocalFS` |
| RECALL-07 | Accessing a record updates `access_count`/`last_accessed` | SATISFIED | `RecordStore.update` called for every T1 hit in recall; in-memory object updated too |
| PROV-01 | LLM provider behind single interface | SATISFIED | `LLMProvider` Protocol in `ports/llm.py`; Phase 1 uses no real LLM |
| PROV-02 | Embedding provider independently configurable from LLM | SATISFIED | `EmbeddingProvider` separate Protocol; `LLMProvider` and `EmbeddingProvider` are separate constructor params |
| PROV-06 | Embeddings normalized; dim asserted at startup | SATISFIED | `StubEmbedder.embed` returns L2-normalized vectors; `MemoryEngine.__init__` raises ValueError on dim mismatch |
| SCHED-01 | Consolidation/decay trigger behind scheduler port | SATISFIED | `Scheduler` Protocol with `schedule/trigger_now/start/shutdown` |
| SCHED-02 | In-process scheduler with `trigger_now()` | SATISFIED | `InProcessScheduler` passes `test_trigger_now_fires_consolidate` |
| IFACE-01 | Importable SDK: `remember/recall/forget/consolidate/expand` | SATISFIED | `from mnema import MemoryEngine, ScopedHandle`; all five verbs on `MemoryEngine` |
| EVAL-01 | 5-capability test harness | SATISFIED | 23 tests across 7 test files covering all 5 SC scenarios + schema unit tests + dedup + providers |

All 23 Phase 1 requirements SATISFIED.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/mnema/core/engine.py` | 225-226 | `# TODO Phase 3: evict to cold storage` in `forget()` body | Info | Correctly scoped stub — intentional placeholder with explicit phase reference. Not a blocker. |
| `src/mnema/core/engine.py` | 238-240 | `# TODO Phase 2: drain staging queue` in `consolidate()` body | Info | Correctly scoped stub — intentional placeholder with explicit phase reference. Not a blocker. |

No unreferenced TBD/FIXME/XXX markers found. The two TODO comments reference specific future phases, satisfying the debt-marker gate.

Deferred tech-debt from code review (tracked in `.planning/todos/pending/phase-01-code-review-deferred.md`, not re-blocked here per user instructions):

- CR-02: `cursor.row_factory = None` timing in `vector_search` — fragile but currently working
- CR-03: LocalFS `append()` TOCTOU — latent under concurrent `gather` writes (Phase 1 is sequential)
- CR-05: `object.__setattr__` for access_count — cosmetic; record is not frozen
- WR-01 through WR-05, IN-01 through IN-03: low/medium severity; none breaks Phase 1 gate

---

### CR-04 Fix Confirmed

The user's specific request to verify the CR-04 fix is confirmed:

`_is_safety_claim(content: str)` in `write_path.py` line 66 takes only `content` — the `type_hint` parameter was removed from the signature. The function checks safety keywords against `content.lower()` unconditionally. `WritePath.execute` sets `is_safety = _is_safety_claim(content)` before checking the classifier, and `protected = is_safety`. The dedicated test `test_allergy_is_protected_without_type_hint` asserts `records[0].protected is True` for `engine.remember("I am allergic to peanuts", user_id="u1", session_id="s1")` with no `type_hint` — GREEN.

---

### Human Verification Required

None. All success criteria are verified programmatically by the test suite.

The phase includes one manual verification item that was already performed and documented:

- sqlite-vec Windows extension loading: confirmed `vec_version v0.1.9` on 2026-06-10 (recorded in `01-VALIDATION.md`).

---

### Deferred Items

None. All Phase 1 requirements are SATISFIED. The items in `.planning/todos/pending/phase-01-code-review-deferred.md` are tech-debt items from the code review, not missing Phase 1 requirements. None of them affect the observable phase goal.

---

### Gaps Summary

No gaps. All 5 roadmap success criteria are observable in the codebase and verified by the test suite. The phase gate (`uv run --extra dev pytest tests/ -q && uv run --extra dev pyright`) exits 0 with 23 tests passing and 0 type errors.

---

_Verified: 2026-06-10T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
