---
phase: 04-cloud-providers-backends
plan: "01"
subsystem: conformance-testing
tags: [conformance, contract-tests, safety-invariants, tdd, red-stubs]
dependency_graph:
  requires: [04-00]
  provides: [conformance contract stubs for 04-02 through 04-07]
  affects: [tests/conformance/, tests/test_cron.py, tests/test_factory.py, tests/test_reindex.py]
tech_stack:
  added: []
  patterns: [parametrized pytest fixtures, class-based contract tests, sentinel counter pattern, RED stub pattern]
key_files:
  created:
    - tests/conformance/test_llm_contract.py
    - tests/conformance/test_embedding_contract.py
    - tests/conformance/test_vault_contract.py
    - tests/conformance/test_scheduler_contract.py
    - tests/conformance/test_record_store_contract.py
    - tests/conformance/test_vector_index_contract.py
    - tests/conformance/test_object_store_contract.py
    - tests/test_cron.py
    - tests/test_factory.py
    - tests/test_reindex.py
  modified: []
decisions:
  - "Used EXTRACT_RECORDS: sentinel prefix in LLM contract test prompt so StubLLM always returns non-empty string — pure plain-text prompts return '' by design"
  - "Record store and vector index contract tests share both t1_backend and embedder_backend fixtures; dim mismatch causes pytest.skip (not test failure)"
  - "RED stub imports are deferred inside test bodies (not at module top) so --collect-only works without mnema.config, mnema.migrate, or cron adapter installed"
metrics:
  duration_minutes: 22
  completed_date: "2026-06-15"
  tasks_completed: 2
  tasks_total: 2
  files_created: 10
  files_modified: 0
---

# Phase 04 Plan 01: Conformance Contract Test Stubs + Standalone RED Stubs Summary

**One-liner:** 7 parametrized conformance contract tests (one per port, safety invariants per backend) + 3 standalone RED stubs gating plans 04-04/07.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | LLM, embedding, vault, scheduler conformance contract tests | 28628a8 | test_llm_contract.py, test_embedding_contract.py, test_vault_contract.py, test_scheduler_contract.py |
| 2 | Record store, vector index, object store contracts + standalone RED stubs | de06739 | test_record_store_contract.py, test_vector_index_contract.py, test_object_store_contract.py, test_cron.py, test_factory.py, test_reindex.py |

## What Was Built

### Conformance Contract Tests (tests/conformance/)

Seven contract test modules, one per adapter port. Each is parametrized via the conftest.py fixture registry from plan 04-00. Local-always backends run unconditionally; cloud/gated backends skip cleanly via `pytest.mark.skipif`.

**test_llm_contract.py** — `TestLLMContract`
- `test_complete_returns_nonempty_string`: complete() returns non-empty str
- `test_complete_accepts_model_kwarg`: complete(model=None) does not raise
- Uses `EXTRACT_RECORDS:` sentinel prefix so StubLLM returns a meaningful response

**test_embedding_contract.py** — `TestEmbeddingContract`
- `test_dim_property_is_positive_int`: dim is a positive int
- `test_embed_returns_correct_shape`: shape matches (n_texts, dim)
- `test_embed_returns_l2_normalized`: norm ~= 1.0 (< 0.01 tolerance)
- `test_embed_single_text`: single-text list returns one vector

**test_vault_contract.py** — `TestVaultContract`
- `test_promote_and_get_user_model_roundtrip`: roundtrip asserts summary in model
- `test_promote_deduplication`: double promote gives count==1
- `test_get_user_model_unknown_user_returns_empty_string`: no raise for unknown user

**test_scheduler_contract.py** — `TestSchedulerContract`
- `test_trigger_now_fires_function`: sentinel counter >= 1 after trigger_now()
- `test_schedule_does_not_fire_immediately`: counter == 0 before trigger_now()

**test_record_store_contract.py** — `TestRecordStoreContract`
- `test_upsert_and_get_roundtrip`: upsert_with_vector + get by id
- `test_live_records_excludes_superseded`: supersede() removes old from live_records
- `test_update_fields_changes_attribute`: update(salience=0.9) reflects in get()
- `test_scope_isolation_user_a_cannot_read_user_b` **(SECURITY INVARIANT D4-02)**: user A's records must not appear in user B's live_records
- `test_protected_record_survives_decay` **(SAFETY INVARIANT FORG-03)**: protected=True records are never yielded by decay_pass — seeded with salience=0.0, access_count=0, 365 days old
- `test_eviction_does_not_hard_delete` **(SAFETY INVARIANT FORG-04)**: get() after update(valid_until)+delete_vector() still returns a row

**test_vector_index_contract.py** — `TestVectorIndexContract`
- `test_vector_search_returns_closest`: exact embedding query returns that record as top result
- `test_vector_search_filters_live_only` **(CORE-05)**: retired (valid_until set) records excluded from search results
- `test_vector_search_scope_isolation`: same embedding, two users — search with user_b only returns user_b's record

**test_object_store_contract.py** — `TestObjectStoreContract`
- `test_append_and_get_roundtrip`: Turn content preserved through append/get
- `test_append_ref_format`: ref starts with `t0://sess_01/`
- `test_archive_returns_ref`: non-empty ref string
- `test_append_audit_does_not_raise`: no exception on valid audit dict
- `test_invalid_session_id_raises` **(T-04-01-03)**: `../../etc/passwd` raises ValueError

### Standalone RED Stubs (tests/)

Three RED stub files that fail with ImportError until the referenced plans ship.

**tests/test_cron.py** — `TestCronScheduler` (RED until plan 04-04)
- `test_cron_scheduler_imports`: `from mnema.adapters.scheduler.cron import CronScheduler`
- `test_cron_schedule_and_trigger`: CronScheduler("*/5 * * * *") + trigger_now sentinel pattern

**tests/test_factory.py** — `TestBuildEngine` (RED until plan 04-07)
- `test_build_engine_imports`: `from mnema.config import build_engine, LocalConfig`
- `test_local_config_builds_engine`: `build_engine(LocalConfig())` returns `MemoryEngine`
- `test_local_config_end_to_end`: remember + recall roundtrip via factory-built engine

**tests/test_reindex.py** — `TestReindex` (RED until plan 04-07)
- `test_reindex_all_imports`: `from mnema.migrate import reindex_all, migrate_embedder`
- `test_reindex_all_re_embeds_live_records`: seeds 3 records, reindex_all() returns count==3
- `test_dim_switch_requires_explicit_reindex` **(D4-14 behavioral proof)**:
  1. SqliteT1 at dim=64
  2. MemoryEngine(embedder=StubEmbedder(dim=128)) raises ValueError
  3. migrate_embedder() upgrades dim
  4. MemoryEngine constructs without error
  5. Protected record survives migration

## Test Results

| Scope | Passed | Skipped | Failed |
|-------|--------|---------|--------|
| tests/conformance/ | 33 | 80 | 0 |
| tests/test_cron.py | 0 | 0 | 2 (RED — expected) |
| tests/test_factory.py | 0 | 0 | 3 (RED — expected) |
| tests/test_reindex.py | 0 | 0 | 3 (RED — expected) |
| Existing 56 tests | 56 | 0 | 0 |
| pyright | 0 errors | — | — |

All conformance local-backend parametrizations PASS. Cloud-gated parametrizations SKIP cleanly. RED stubs FAIL with ImportError (no collection ERROR).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] StubLLM returns empty string for non-sentinel prompts**
- **Found during:** Task 1 verification
- **Issue:** `test_complete_returns_nonempty_string` used plain `"hello"` as prompt. StubLLM.complete() returns `""` for any prompt not starting with `EXTRACT_RECORDS:` or `JUDGE_CONTRADICTION:` — by design.
- **Fix:** Changed test prompt to `"EXTRACT_RECORDS: hello"` so StubLLM always returns a non-empty JSON string. This is consistent with `test_fixture_smoke.py` which already uses `"EXTRACT_RECORDS: hello"`.
- **Files modified:** `tests/conformance/test_llm_contract.py`
- **Commit:** 28628a8

## Known Stubs

None — all conformance tests assert real behavior against existing local adapters. The RED stub test files (test_cron.py, test_factory.py, test_reindex.py) are intentionally incomplete pending plans 04-04 and 04-07.

## Threat Flags

No new security-relevant surfaces introduced. All new files are test-only.

The threat mitigations from the plan's `<threat_model>` are covered:
- T-04-01-01 (scope isolation): `test_scope_isolation_user_a_cannot_read_user_b` asserts user_id predicate
- T-04-01-02 (non-destructive eviction): `test_eviction_does_not_hard_delete` asserts row survives
- T-04-01-03 (path-traversal guard): `test_invalid_session_id_raises` asserts ValueError on `../../etc/passwd`
- T-04-01-04 (moto_s3 stub): accepted — moto_s3 backend skips until plan 04-06

## Self-Check: PASSED

**Files exist:**
- FOUND: tests/conformance/test_llm_contract.py
- FOUND: tests/conformance/test_embedding_contract.py
- FOUND: tests/conformance/test_vault_contract.py
- FOUND: tests/conformance/test_scheduler_contract.py
- FOUND: tests/conformance/test_record_store_contract.py
- FOUND: tests/conformance/test_vector_index_contract.py
- FOUND: tests/conformance/test_object_store_contract.py
- FOUND: tests/test_cron.py
- FOUND: tests/test_factory.py
- FOUND: tests/test_reindex.py

**Commits exist:**
- FOUND: 28628a8 (Task 1: LLM, embedding, vault, scheduler contract tests)
- FOUND: de06739 (Task 2: record store, vector index, object store + RED stubs)
