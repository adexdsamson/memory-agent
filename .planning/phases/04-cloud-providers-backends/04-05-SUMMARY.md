---
phase: 04-cloud-providers-backends
plan: "05"
status: complete
completed: 2026-06-15
requirements: [STORE-02, STORE-06]
---

# Plan 04-05 Summary — PostgresT1 (psycopg3 + pgvector)

## What was built
`src/mnema/adapters/vector_store/postgres_t1.py` — a method-for-method port of SqliteT1 to
psycopg3 async + pgvector HNSW, satisfying RecordStore + VectorIndex by structural typing (D-08).
Plus the `t1_backend` postgres conformance fixture in `tests/conformance/conftest.py`.

**Executed inline by the orchestrator** — the background executor subagent failed twice with a
spurious "no Bash access" bail (a session-wide subagent permission regression mid-run); the
orchestrator has Bash and implemented + verified the plan directly.

## Key implementation points
- **Two-table design** mirroring SqliteT1's vec_t1: `t1_records` (typed columns; BOOLEAN/TIMESTAMPTZ/JSONB/DOUBLE PRECISION) + `t1_vectors(record_id PK FK ON DELETE CASCADE, embedding vector(dim))` with an HNSW `vector_l2_ops` index and the partial index `WHERE valid_until IS NULL`.
- **Pitfall 1:** `register_vector_async(conn)` immediately after `connect()`.
- **Pitfall 2:** `SET hnsw.iterative_scan='strict_order'` (+ `ef_search=100`) before every KNN query.
- **CVE-2026-3172:** `_check_pgvector_version()` raises if the installed pgvector extension < 0.8.2.
- Full Protocol surface matched to the REAL SqliteT1 (not the plan's draft names): `upsert`, `supersede` (atomic `async with conn.transaction()` + rowcount==1 guard), `get`, `find_by_t0_ref(t0_ref, user_id)` with `provisional = TRUE` fence, `update(**fields)` with `_ALLOWED_COLUMNS` whitelist, `live_records`, `upsert_with_vector`, `upsert_vector`, `vector_search` (L2 `<->`), `delete_vector` (vectors only — FORG-04), `get_latest`, `get_live_records`, `close`.
- `user_id` predicate on every SELECT/UPDATE (D-02/03 scope isolation).
- Conformance fixture uses `pgvector/pgvector:pg16` (CVE-safe image) via testcontainers when Docker present, else `MNEMA_TEST_PG_DSN`, else skips — DSN built from `container.username/password` (no hardcoded creds).

## Verification
- `uv run --extra dev --extra cloud python -c "import ...PostgresT1"` → import ok
- `uv run --extra dev --extra cloud pyright` → **0 errors** (the cloud SDKs must be present for type-checking; dynamic-SQL `str` args carry `# type: ignore[arg-type]`; boto3-untyped handled in oss_s3 separately)
- `uv run --extra dev ruff check` → clean
- `uv run --extra dev pytest -q` → **109 passed, 70 skipped** (postgres params skip without Docker; the 6 fails are test_reindex/test_factory RED stubs for 04-07)

## Note
Live Postgres conformance (scope isolation, protected survival, no-hard-delete on the pgvector backend) is **gated** — runs under `MNEMA_TEST_PG=1` with Docker/DSN. The adapter is type-checked and structurally matched to the shared contract; runtime parity is asserted by the same conformance suite when a Postgres is available.
