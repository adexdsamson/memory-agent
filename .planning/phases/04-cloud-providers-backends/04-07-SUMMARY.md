---
phase: 04-cloud-providers-backends
plan: "07"
status: complete
completed: 2026-06-15
requirements: [STORE-03, STORE-04, STORE-05, PROV-07]
---

# Plan 04-07 Summary — Config factory + reindex migration

## What was built (executed inline by the orchestrator — subagent Bash unavailable)
- **`src/mnema/config.py`** — `LocalConfig` + `QwenAlibabaConfig` Pydantic models + async `build_engine(config)` factory wiring all six axes (STORE-04/05). API keys are `SecretStr` (T-04-07-01). STORE-03: both configs wire the existing `LocalFSVault` — no new vault adapter.
- **`src/mnema/migrate.py`** — `reindex_all(t1, embedder, user_id)` (re-embeds live records, preserves protected flag, touches vectors only) + `migrate_embedder(t1, new_embedder, *, user_id)` = `recreate_vector_store(new_dim)` → `reindex_all` (PROV-07 full sequence).
- **`SqliteT1.recreate_vector_store(new_dim)`** — drop/recreate vec_t1 at new_dim; t1_records untouched.
- **`PostgresT1.recreate_vector_store(new_dim)`** — drop HNSW index + embedding column, re-add at new_dim, recreate index (in one transaction).
- **`test_factory.py`** (GREEN) — local build + end-to-end remember/recall + consolidate + SecretStr-hiding + gated Qwen build.
- **`test_reindex.py`** (GREEN) — reindex count, and `test_dim_switch_requires_explicit_reindex` (PROV-07 proof: dim-64 seed incl. a protected record → MemoryEngine(dim=128) raises ValueError BEFORE migration → migrate_embedder → engine constructs → protected record survives `protected=True`, `valid_until=None`).

## Bug fixed during execution
`SqliteT1.upsert_vector` used `INSERT OR REPLACE INTO vec_t1`, but sqlite-vec's **vec0 virtual table does not honor INSERT OR REPLACE** for an existing record_id (raises UNIQUE PK error rather than replacing) — latent until re-embedding. Changed to **DELETE-then-INSERT** (the documented vec0 upsert pattern). This is what makes `reindex_all` idempotent on the local backend.

## Verification
- `uv run --extra dev pytest -q` → **117 passed, 71 skipped** (full hermetic suite GREEN; all Phase 4 RED stubs resolved)
- `uv run --extra dev --extra cloud pyright` → **0 errors**
- `uv run --extra dev ruff check src/ tests/` → clean
