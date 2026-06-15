---
phase: 04-cloud-providers-backends
plan: "08"
status: complete
completed: 2026-06-15
requirements: [PROV-03, PROV-04, PROV-05, PROV-07, STORE-01, STORE-02, STORE-03, STORE-04, STORE-05, STORE-06, SCHED-03]
---

# Plan 04-08 Summary — Phase 4 gate

Phase-gate plan: run the full gate and fix any cross-plan integration issues. No new
behavior. Executed inline by the orchestrator.

## Gate result (integrated main tree)
- `uv run --extra dev pytest tests/ -q` → **117 passed, 71 skipped** (hermetic; cloud/Postgres params skip without creds/Docker)
- `uv run --extra dev --extra cloud pyright` → **0 errors** (cloud SDKs present for type-checking)
- `uv run --extra dev ruff check src/ tests/` → **All checks passed**

## Integration issues found + fixed during Phase 4 (cross-plan)
- `conftest.py` `object_store_backend`: `return` in an async-generator fixture → `SyntaxError` (04-06 unverified) — fixed to `yield`.
- `SqliteT1.upsert_vector`: `INSERT OR REPLACE` not honored by vec0 on re-embed → DELETE-then-INSERT (04-07).
- Cloud adapters need `--extra cloud` for pyright (dev-only venv shows missing-SDK type errors); boto3 client typed `Any`; dynamic psycopg SQL carries `# type: ignore[arg-type]`.

## Backend coverage (STORE-06 ≥2 backends/axis)
- **Object store:** LocalFS + moto-S3 (both hermetic, always-on) + OSS (gated) ✓
- **Vector store:** sqlite-vec (always-on) + Postgres/pgvector (testcontainers-gated) ✓
- **Vault:** LocalFSVault (always-on; STORE-03 already satisfied) ✓
- **LLM:** StubLLM (always-on) + Anthropic + Qwen (gated) ✓
- **Embedding:** StubEmbedder (always-on) + Voyage + Qwen (gated) ✓
- **Scheduler:** InProcessScheduler + CronScheduler (both hermetic) ✓

The conformance suite asserts the safety invariants (scope isolation, protected-record
survival, non-destructive eviction) on every registered backend; cloud/Postgres run the
SAME suite when `MNEMA_TEST_*` + Docker/creds are present.
