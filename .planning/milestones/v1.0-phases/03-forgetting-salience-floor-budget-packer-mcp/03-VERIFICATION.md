---
phase: 03-forgetting-salience-floor-budget-packer-mcp
verified: 2026-06-14T00:00:00Z
status: passed
score: 9/9
overrides_applied: 0
---

# Phase 3: Forgetting, Salience Floor, Budget Packer & MCP — Verification Report

**Phase Goal:** Deliberate, recoverable forgetting with a provable protected-fact guarantee, budget-aware recall that surfaces critical facts first, T2 promotion, and the MCP surface over the now-complete core.
**Verified:** 2026-06-14
**Status:** passed
**Re-verification:** No — initial verification

---

## Tool Output Summary

All three gate commands ran to completion:

| Command | Result |
|---------|--------|
| `uv run --extra dev pytest tests/ -q` | **56 passed** in 20.73s |
| `uv run --extra dev pyright` | **0 errors, 0 warnings, 0 informations** |
| `uv run --extra dev ruff check src/ tests/` | **All checks passed** |

Phase 3 test files alone: `pytest tests/test_forgetting.py tests/test_recall_packer.py tests/test_vault.py tests/test_mcp_server.py -v` → **23 passed** in 11.13s.

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Records below keep threshold and not protected are evicted to cold storage — recoverable and auditable, no hard-delete path anywhere | VERIFIED | `engine.evict()` performs 4-step sequence (update valid_until → delete_vector → archive → append_audit). `grep "DELETE FROM t1_records" src/` returns zero hits. Only `DELETE FROM vec_t1` exists (vector ghost-record removal). `TestEviction` tests all GREEN. |
| 2 | A protected record is skipped before any score math and survives every decay pass under any input, proven by a Hypothesis invariant test | VERIFIED | `decay_pass` in `decay.py` has structural `if record.protected: continue` before `yield`. `test_protected_records_never_evicted` is a `@given(record_set_strategy()) @settings(max_examples=100)` sync property test consuming `decay_pass` directly — GREEN. |
| 3 | `recall` re-ranks by relevance × salience × recency and packs summaries under a caller-supplied token budget, with two-pass packer that reserves protected/active-constraint slots first | VERIFIED | `packer.py` implements `re_rank()` (composite = similarity × salience × exp(−λ×age)) and `pack_records()` (Pass 1: critical set; Pass 2: fill). `recall.py` wires both. Adversarial test `test_critical_fact_survives_large_off_topic_history` GREEN (100 filler records cannot displace allergy). `test_protected_fact_retained_when_budget_smaller_than_critical_set` GREEN (protected records always included even when budget < their token cost). |
| 4 | Stable records are promoted into the T2 canonical vault (merged, deduped, human-readable user model) | VERIFIED | `LocalFSVault.promote()` writes `{base_dir}/{user_id}.md` sectioned by record_type, with exact bullet-line dedup and atomic write via `os.replace()`. `test_promotion_on_consolidation`, `test_vault_promotion_before_eviction`, `TestLocalFSVault` all GREEN. |
| 5 | An MCP server exposes `remember`/`recall`/`forget`/`consolidate`/`expand` as a thin wrapper over the same SDK core | VERIFIED | `create_mcp_server()` in `src/mnema/mcp/server.py` creates a FastMCP instance with exactly 5 tools. All 5 delegate immediately to engine methods with no business logic duplication. `test_mcp_tools_list`, `test_mcp_remember_recall_roundtrip`, `test_mcp_consolidate_passes_user_id` all GREEN. |

**Score:** 5/5 roadmap success criteria verified.

---

### Goal-Backward Correctness Checks (per verification brief)

#### 1. FORG-03 — Hypothesis property test proves no input evicts a protected record

**Status: VERIFIED**

- `test_protected_records_never_evicted` in `tests/test_forgetting.py` is a **sync** `def` (not `async def`) decorated with `@given(record_set_strategy())` and `@settings(max_examples=100)`.
- The strategy generates up to 30 `MemoryRecord` objects with arbitrary `protected` (bool) values.
- The test body calls `asyncio.run(_collect_eviction_candidates())` which runs `decay_pass` then filters by `score < KEEP_THRESHOLD`.
- The assert is `protected_evicted == []`.
- This test directly consumes `decay_pass`'s structural `if record.protected: continue` skip — the structural guarantee is what the test proves.
- **Test is GREEN** in the run output.

#### 2. FORG-04 / never-hard-delete — no `DELETE FROM t1_records` path; eviction-without-t0 RAISES

**Status: VERIFIED**

- `grep -rn "DELETE FROM t1_records" src/` returns **zero hits**.
- The only `DELETE FROM` in the eviction path is `DELETE FROM vec_t1` in `SqliteT1.delete_vector()` — this removes the vector embedding to prevent ghost-record recall (correct; the record row remains with `valid_until` set).
- `engine.evict()` (engine.py lines 321–372): 4-step sequence with `update(valid_until=now)` → `delete_vector` → `archive` → `append_audit`. No SQL DELETE on records.
- `ConsolidationPipeline.run()` (consolidation.py lines 249–265): after CR-04 fix, if `self._t0 is None` when eviction would occur, **raises `RuntimeError`** with message referencing FORG-04. Silent skip no longer possible.
- Eviction audit JSONL fields verified by `test_eviction_audit_jsonl`: `record_id`, `user_id`, `keep_score`, `evicted_at`, `reason` — all present and correct.

#### 3. RECALL-05 — two-pass packer; adversarial test GREEN; budget < critical-set test GREEN

**Status: VERIFIED**

- `pack_records()` in `packer.py` (lines 138–228): Pass 1 partitions by `r.protected or (r.record_type == RecordType.FACT and r.valid_until is None)`. Protected records are unconditionally appended (line 199–201: `if rec.protected: packed.append(rec); used += cost` — no budget check). Non-protected critical records respect budget.
- `test_critical_fact_survives_large_off_topic_history`: 100 large filler records (salience=0.9) placed before the protected allergy fact in `ranked`. Budget=200. Allergy fact has `protected=True`. Result: `allergy.id in packed_ids` — GREEN.
- `test_protected_fact_retained_when_budget_smaller_than_critical_set` (post-review-fix WR-03): two protected allergies, `tight_budget = max(cost_peanuts, cost_shellfish) - 1`. Both are expected in output regardless. GREEN.

#### 4. CONS-09 ordering — vault promotion BEFORE eviction; two separate loops; protected never cleared

**Status: VERIFIED**

- `consolidation.py` lines 205–265: inside the `for uid in processed_user_ids:` loop, there are **two separate `async for` loops**:
  - Loop 1 (lines 208–227): `async for record in record_store_any.live_records(uid)` → promotes qualifying records via `await self._vault.promote(rec)`.
  - Loop 2 (lines 230–265): `async for record, score in decay_pass(...)` → evicts records below `KEEP_THRESHOLD`.
- These are structurally separate loops, not a single merged loop. Vault loop completes entirely before eviction loop begins.
- `test_vault_promotion_before_eviction`: seeds a record with `salience=0.72` (above `VAULT_SALIENCE_THRESHOLD=0.7`) and `created_at` backdated 180 days with `access_count=0` (keep_score well below 0.3). After `consolidate(user_id="u1")`, asserts (a) vault contains `"borderline high-salience old fact"` and (b) `valid_until is not None`. Both GREEN.
- Protected-flag monotonicity is enforced in `_apply_verdict()` (lines 438, 487) and reconciliation path (line 349): `protected_final = bool(...) or existing.protected` — consolidation can set but never clear the protected flag.

#### 5. TIER-03 — LocalFSVault writes human-readable markdown atomically; path-traversal validated; dedup by exact line

**Status: VERIFIED**

- `LocalFSVault.promote()` (local_fs_vault.py lines 76–130):
  - Validates `record.user_id` against `_VALID_USER_ID = re.compile(r"^[A-Za-z0-9_\-]+$")` — raises `ValueError` for `"../../etc/passwd"`.
  - Computes `bullet_line = f"- {summary}\n"` and checks `if bullet_line in existing: return` (exact bullet-line match, not raw substring — post CR-02 fix).
  - Atomic write: `tempfile.mkstemp()` → `os.fdopen()` → `os.replace()` (post CR-01 fix). Crash-safe.
  - Sections by record_type: `f"## {record.record_type.value.capitalize()}s"`.
- `test_promote_deduplication`: promotes same record twice, checks `content.count("prefers vegetarian food") == 1` — GREEN.
- `test_promote_sectioned_by_type`: promotes FACT and PREFERENCE records, checks for `"## Facts"` and `"## Preferences"` — GREEN.

#### 6. IFACE-02 — MCP server thin wrapper; every tool requires user_id and passes it through; in-process tests GREEN

**Status: VERIFIED**

- `create_mcp_server()` in `server.py`: 5 `@mcp.tool` async functions, each closing over `engine`. No business logic duplication — each is 1–3 lines delegating to the engine.
- Every tool signature requires `user_id: str` as a positional argument (no default value).
- `consolidate` tool: `await engine.consolidate(user_id=user_id)` — D3-14 isolation is real (not `engine.consolidate()` without user_id).
- Tests use `async with Client(mcp_server) as client:` — FastMCP in-process transport (no subprocess, no network).
- `result.data` attribute confirmed by Task 1 probe documented in test file header.
- All 5 MCP tests GREEN: `test_mcp_tools_list`, `test_mcp_remember_recall_roundtrip`, `test_mcp_forget_protected_raises`, `test_mcp_expand_returns_none_for_wrong_user`, `test_mcp_consolidate_passes_user_id`.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mnema/core/engine.py` | `forget()`, `evict()`, `KEEP_THRESHOLD`, `vault` kwarg, `consolidate(user_id=...)` | VERIFIED | All present. `KEEP_THRESHOLD = 0.3` at module level. `consolidate()` has `try/finally` for scheduler (CR-05). |
| `src/mnema/core/packer.py` | `TokenCounter`, `TiktokenCounter`, `ByteLengthCounter`, `pack_records()`, `re_rank()` | VERIFIED | All exported. D-12 compliant (no I/O, no async). |
| `src/mnema/core/recall.py` | `budget` param, `re_rank` called, `pack_records` called, `similarity_scores` built | VERIFIED | `RecallPath.execute()` accepts `budget: int | None = None`. Steps 6–8 wired. |
| `src/mnema/core/consolidation.py` | `VAULT_SALIENCE_THRESHOLD`, `KEEP_THRESHOLD`, vault loop + eviction loop (separate), `run(user_id=...)`, `t0=None` RAISES | VERIFIED | Both constants at module level. Two separate loops confirmed. CR-04 raise confirmed. WR-04 `processed_user_ids.add(user_id)` confirmed. |
| `src/mnema/adapters/vault/local_fs_vault.py` | `LocalFSVault`, path-traversal guard, atomic write, exact-line dedup | VERIFIED | All present post CR-01/CR-02 fixes. |
| `src/mnema/ports/vault.py` | `VaultStore` Protocol, `promote()`, `get_user_model()`, no `@runtime_checkable` | VERIFIED | Protocol with 2 async methods, TYPE_CHECKING import of MemoryRecord, no `@runtime_checkable`. |
| `src/mnema/adapters/object_store/local_fs.py` | `append_audit()` method | VERIFIED | Appends to `eviction_audit.jsonl`. |
| `src/mnema/ports/object_store.py` | `append_audit()` in Protocol | VERIFIED | Protocol updated with `async def append_audit(self, entry: dict) -> None`. |
| `src/mnema/mcp/server.py` | `create_mcp_server()`, 5 tools, `__main__` block | VERIFIED | Factory function, all 5 tools as closures, stdio `__main__` entry point. |
| `tests/conftest.py` | `engine_with_vault` fixture | VERIFIED | Present at line 107, creates `LocalFSVault` and passes `vault=vault_instance` to `MemoryEngine`. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `engine.evict()` | `decay_pass` | `async for record, score in decay_pass(self._t1, user_id, now=now)` | WIRED | engine.py line 349 |
| `engine.evict()` | `self._t0.append_audit` | `await self._t0.append_audit(entry)` | WIRED | engine.py line 370 |
| `engine.evict()` | `self._t1.delete_vector` | `await self._t1.delete_vector(record.id)` | WIRED | engine.py line 358 |
| `engine.forget()` | cross-user scope check | `if record.user_id != user_id: raise ValueError(...)` | WIRED | engine.py lines 294–297 |
| `recall.py RecallPath.execute()` | `re_rank` | `ranked = re_rank(combined, similarity_scores, now)` | WIRED | recall.py line 184 |
| `recall.py RecallPath.execute()` | `pack_records` | `if budget is not None: return pack_records(ranked, budget, TiktokenCounter())` | WIRED | recall.py lines 187–188 |
| `engine.recall()` | `RecallPath.execute()` | `budget` kwarg passed through | WIRED | engine.py line 237 |
| `consolidation.py run() vault loop` | `self._vault.promote(record)` | Loop 1, `await self._vault.promote(rec)` | WIRED | consolidation.py line 227 |
| `consolidation.py run() eviction loop` | `decay_pass` + 4-step eviction | Loop 2, separate `async for` | WIRED | consolidation.py lines 235–265 |
| `engine.consolidate()` | `pipeline.run(user_id=user_id)` | `await self._consolidation_pipeline.run(user_id=user_id)` | WIRED | engine.py line 402 |
| `engine.__init__` | `ConsolidationPipeline(vault=self._vault, t0=self._t0)` | Constructor kwargs | WIRED | engine.py lines 144–152 |
| `server.py consolidate tool` | `engine.consolidate(user_id=user_id)` | D3-14 isolation | WIRED | server.py line 145 |
| `tests/test_mcp_server.py` | `Client(mcp_server)` | `async with Client(mcp_server) as client:` | WIRED | All 5 MCP tests use in-process client |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `recall.py RecallPath.execute()` | `ranked` (list of MemoryRecord) | `dense_hits` from `vector_search` → `t1_records` fetched by `record_store.get()` | Yes — real DB queries via SqliteT1 | FLOWING |
| `local_fs_vault.py LocalFSVault.promote()` | vault markdown file | `MemoryRecord.summary` and `MemoryRecord.record_type` | Yes — record fields written to disk atomically | FLOWING |
| `consolidation.py run()` vault loop | `record` in `live_records(uid)` | SqliteT1.live_records() SQL query (`WHERE valid_until IS NULL`) | Yes — live DB records | FLOWING |
| `local_fs.py append_audit()` | JSONL audit file | `entry` dict from caller (contains `record_id`, `user_id`, `keep_score`, `evicted_at`, `reason`) | Yes — real eviction data | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 56 tests pass (Phase 1+2+3) | `uv run --extra dev pytest tests/ -q` | 56 passed in 20.73s | PASS |
| Phase 3 tests alone (23 tests) | `uv run --extra dev pytest tests/test_forgetting.py tests/test_recall_packer.py tests/test_vault.py tests/test_mcp_server.py -v` | 23 passed in 11.13s | PASS |
| Hypothesis property test passes | included in above | `test_protected_records_never_evicted` PASSED | PASS |
| Adversarial packer test passes | included in above | `test_critical_fact_survives_large_off_topic_history` PASSED | PASS |
| Vault ordering test passes | included in above | `test_vault_promotion_before_eviction` PASSED | PASS |
| User isolation test passes | included in above | `test_consolidate_user_isolation` PASSED | PASS |
| Protected-fact retained below budget | included in above | `test_protected_fact_retained_when_budget_smaller_than_critical_set` PASSED | PASS |

---

### Probe Execution

No probe scripts declared for this phase (`scripts/*/tests/probe-*.sh` — none found). Behavioral spot-checks above serve as the equivalent verification.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| FORG-02 | 03-01 | Records below keep threshold evicted to cold storage | SATISFIED | `engine.evict()` 4-step sequence; `TestEviction` GREEN; audit JSONL written |
| FORG-03 | 03-01 | Protected records skipped before any score math, invariant test | SATISFIED | Hypothesis property test GREEN; `decay_pass` structural `if record.protected: continue` |
| FORG-04 | 03-01 | Eviction recoverable and auditable, never hard-delete | SATISFIED | `eviction_audit.jsonl` written; no `DELETE FROM t1_records`; t0-None RAISES |
| RECALL-03 | 03-02 | Results re-ranked by relevance × salience × recency | SATISFIED | `re_rank()` implemented and wired in `RecallPath.execute()`; `TestReRank` GREEN |
| RECALL-04 | 03-02 | Recall packs summaries under caller-supplied token budget | SATISFIED | `pack_records()` + `TiktokenCounter`; `TestPacker` GREEN |
| RECALL-05 | 03-02 | Two-pass packer reserves protected/active-constraint slots first | SATISFIED | Adversarial test GREEN; protected records unconditionally included |
| CONS-09 | 03-03 | Stable records promoted into T2 canonical vault | SATISFIED | `LocalFSVault.promote()` wired in consolidation Loop 1; `test_promotion_on_consolidation` GREEN |
| TIER-03 | 03-03 | T2 vault holds merged, deduped, human-readable user model | SATISFIED | Sectioned markdown; exact-line dedup; atomic write; path-traversal guard |
| IFACE-02 | 03-04 | MCP server exposes 5 verbs as thin wrapper | SATISFIED | `create_mcp_server()`; 5 tools; all MCP tests GREEN |

---

### Anti-Patterns Found

Scanned: `src/mnema/core/engine.py`, `consolidation.py`, `packer.py`, `recall.py`, `src/mnema/adapters/vault/local_fs_vault.py`, `src/mnema/mcp/server.py`, `tests/test_forgetting.py`, `tests/test_recall_packer.py`, `tests/test_vault.py`, `tests/test_mcp_server.py`.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER found | — | None |

No debt markers, no placeholder implementations, no hardcoded empty return values in production paths.

---

### Human Verification Required

None. All must-haves are mechanically verifiable and verified.

---

### Gaps Summary

No gaps. All 9 requirement IDs are satisfied by GREEN tests and substantive code. The phase gate passes: 56 tests, 0 pyright errors, 0 ruff errors.

---

_Verified: 2026-06-14_
_Verifier: Claude (gsd-verifier)_
