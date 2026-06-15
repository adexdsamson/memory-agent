"""PostgresT1 — Postgres + pgvector T1 working-memory adapter.

Satisfies both RecordStore and VectorIndex Protocols by structural typing
(no inheritance from the Protocol classes — D-08). A method-for-method port of
SqliteT1 to psycopg3 async + pgvector HNSW (D4-09).

Pitfall 1 (mitigated): `register_vector_async(conn)` is called IMMEDIATELY after
`psycopg.AsyncConnection.connect()`, before any query — otherwise vector columns
round-trip as raw bytes.

Pitfall 2 (mitigated): `SET hnsw.iterative_scan = 'strict_order'` is issued before
every KNN query so the `valid_until IS NULL` JOIN filter can still return k rows.

Security: the `user_id` predicate is on every SELECT/UPDATE (scope isolation,
D-02/D-03); `update()` validates field names against `_ALLOWED_COLUMNS` before any
column-name interpolation (T-04-05-01).

CVE-2026-3172: `open()` raises RuntimeError if the installed pgvector extension is
below 0.8.2 (parallel-HNSW-build buffer overflow). Use the `pgvector/pgvector:pg16`
image for tests — it ships >= 0.8.2.

Two-table design mirrors SqliteT1's vec_t1 virtual table:
  t1_records  — typed record columns (no embedding column)
  t1_vectors  — (record_id PK FK -> t1_records.id ON DELETE CASCADE, embedding vector(dim))

Cloud dependency: psycopg + pgvector live in the optional `cloud` extra; imports are
module-level here (the module is only imported when the Postgres backend is selected /
conformance-gated), so the hermetic dev suite never imports it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import psycopg
from pgvector.psycopg import register_vector_async  # type: ignore[import-untyped]
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from mnema.core.schema import MemoryRecord

# ---------------------------------------------------------------------------
# Allowed field names for the parameterized UPDATE whitelist (T-04-05-01)
# Copied verbatim from sqlite_t1.py — the two adapters share the column contract.
# ---------------------------------------------------------------------------
_ALLOWED_COLUMNS: frozenset[str] = frozenset(
    {
        "user_id",
        "session_id",
        "agent_id",
        "record_type",
        "content",
        "summary",
        "keywords",
        "embedding_model",
        "embedding_dim",
        "embedding_version",
        "protected",
        "salience",
        "confidence",
        "provisional",
        "valid_from",
        "valid_until",
        "superseded_by",
        "t0_ref",
        "source_refs",
        "access_count",
        "last_accessed",
        "created_at",
        "graph_edges",
    }
)

# JSONB list columns — wrapped in Jsonb() on write, returned as Python objects on read.
_JSON_COLUMNS: frozenset[str] = frozenset({"keywords", "source_refs", "graph_edges"})

_MIN_PGVECTOR_VERSION: tuple[int, int, int] = (0, 8, 2)  # CVE-2026-3172 floor

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
_DDL_RECORDS = """
CREATE TABLE IF NOT EXISTS t1_records (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    agent_id        TEXT,
    record_type     TEXT NOT NULL,
    content         TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    keywords        JSONB NOT NULL DEFAULT '[]'::jsonb,
    embedding_model TEXT,
    embedding_dim   INTEGER,
    embedding_version TEXT,
    protected       BOOLEAN NOT NULL DEFAULT FALSE,
    salience        DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    confidence      DOUBLE PRECISION NOT NULL DEFAULT 0.9,
    provisional     BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from      TIMESTAMPTZ NOT NULL,
    valid_until     TIMESTAMPTZ,
    superseded_by   TEXT,
    t0_ref          TEXT,
    source_refs     JSONB NOT NULL DEFAULT '[]'::jsonb,
    access_count    INTEGER NOT NULL DEFAULT 0,
    last_accessed   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL,
    graph_edges     JSONB NOT NULL DEFAULT '[]'::jsonb
)
"""

_DDL_IDX_LIVE_USER = """
CREATE INDEX IF NOT EXISTS idx_t1_live_user
    ON t1_records (user_id, agent_id)
    WHERE valid_until IS NULL
"""

_DDL_HNSW = """
CREATE INDEX IF NOT EXISTS idx_t1_vectors_hnsw
    ON t1_vectors USING hnsw (embedding vector_l2_ops)
"""

# Column order for INSERT (matches t1_records); shared by upsert + supersede.
_COLUMNS: tuple[str, ...] = (
    "id", "user_id", "session_id", "agent_id", "record_type", "content", "summary",
    "keywords", "embedding_model", "embedding_dim", "embedding_version",
    "protected", "salience", "confidence", "provisional",
    "valid_from", "valid_until", "superseded_by", "t0_ref", "source_refs",
    "access_count", "last_accessed", "created_at", "graph_edges",
)

_INSERT_SQL = (
    "INSERT INTO t1_records ("
    + ", ".join(_COLUMNS)
    + ") VALUES ("
    + ", ".join(f"%({c})s" for c in _COLUMNS)
    + ") ON CONFLICT (id) DO UPDATE SET "
    + ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "id")
)


def _record_params(record: MemoryRecord) -> dict[str, Any]:
    """Build the parameter dict for _INSERT_SQL from a MemoryRecord.

    psycopg3 adapts Python types natively: bool -> BOOLEAN, datetime -> TIMESTAMPTZ.
    JSON list columns are wrapped in Jsonb(); record_type uses the StrEnum value.
    """
    return {
        "id": record.id,
        "user_id": record.user_id,
        "session_id": record.session_id,
        "agent_id": record.agent_id,
        "record_type": str(record.record_type.value),
        "content": record.content,
        "summary": record.summary,
        "keywords": Jsonb(record.keywords),
        "embedding_model": record.embedding_model,
        "embedding_dim": record.embedding_dim,
        "embedding_version": record.embedding_version,
        "protected": record.protected,
        "salience": record.salience,
        "confidence": record.confidence,
        "provisional": record.provisional,
        "valid_from": record.valid_from,
        "valid_until": record.valid_until,
        "superseded_by": record.superseded_by,
        "t0_ref": record.t0_ref,
        "source_refs": Jsonb(record.source_refs),
        "access_count": record.access_count,
        "last_accessed": record.last_accessed,
        "created_at": record.created_at,
        "graph_edges": Jsonb(record.graph_edges),
    }


def _make_record(row: dict[str, Any]) -> MemoryRecord:
    """Convert a dict_row from t1_records into a MemoryRecord.

    JSONB columns arrive as Python list/dict, BOOLEAN as bool, TIMESTAMPTZ as
    timezone-aware datetime — no manual casting needed. Pydantic coerces the
    record_type string into the RecordType StrEnum.
    """
    return MemoryRecord.model_validate(row)


class PostgresT1:
    """T1 working-memory adapter over psycopg3 async + pgvector.

    Satisfies RecordStore + VectorIndex Protocols by structural typing (D-08).
    """

    def __init__(self, conn: psycopg.AsyncConnection[Any], dim: int) -> None:
        self._conn = conn
        self._dim = dim

    @property
    def dim(self) -> int:
        """Vector column dimension this adapter was opened with."""
        return self._dim

    @classmethod
    async def open(cls, dsn: str, dim: int) -> "PostgresT1":
        """Connect, register pgvector, create schema, enforce the CVE version floor."""
        conn = await psycopg.AsyncConnection.connect(dsn, autocommit=False)
        await register_vector_async(conn)  # Pitfall 1 — MUST precede any vector use
        await cls._create_schema(conn, dim)
        await cls._check_pgvector_version(conn)  # CVE-2026-3172 guard
        return cls(conn, dim)

    @classmethod
    async def _create_schema(cls, conn: psycopg.AsyncConnection[Any], dim: int) -> None:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(_DDL_RECORDS)  # type: ignore[arg-type]
        ddl_vectors = (
            f"CREATE TABLE IF NOT EXISTS t1_vectors ("
            f"record_id TEXT PRIMARY KEY REFERENCES t1_records(id) ON DELETE CASCADE, "
            f"embedding vector({int(dim)}))"  # noqa: S608 — dim is an int, not user input
        )
        await conn.execute(ddl_vectors)  # type: ignore[arg-type]
        await conn.execute(_DDL_IDX_LIVE_USER)  # type: ignore[arg-type]
        await conn.execute(_DDL_HNSW)  # type: ignore[arg-type]
        await conn.commit()

    @classmethod
    async def _check_pgvector_version(cls, conn: psycopg.AsyncConnection[Any]) -> None:
        cursor = await conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError(
                "pgvector extension is not installed. Run: CREATE EXTENSION vector;"
            )
        ver_str = str(row[0])
        try:
            ver_tuple = tuple(int(x) for x in ver_str.split(".")[:3])
        except ValueError as exc:
            raise RuntimeError(f"Unparseable pgvector version {ver_str!r}") from exc
        if ver_tuple < _MIN_PGVECTOR_VERSION:
            min_str = ".".join(str(x) for x in _MIN_PGVECTOR_VERSION)
            raise RuntimeError(
                f"pgvector extension version {ver_str} < {min_str} "
                f"(CVE-2026-3172). Upgrade pgvector."
            )

    async def close(self) -> None:
        """Close the underlying connection (fixture teardown)."""
        await self._conn.close()

    # -----------------------------------------------------------------------
    # RecordStore Protocol methods
    # -----------------------------------------------------------------------

    async def upsert(self, record: MemoryRecord) -> None:
        """Insert or replace a record (keyed by record.id)."""
        await self._conn.execute(_INSERT_SQL, _record_params(record))
        await self._conn.commit()

    async def supersede(
        self,
        old_id: str,
        new_record: MemoryRecord,
        embedding: list[float],
    ) -> None:
        """Atomically retire old_id and insert new_record + embedding (one transaction).

        UPDATE old (valid_until + superseded_by, user_id-scoped) → INSERT new record →
        INSERT new vector. rowcount==1 guard prevents cross-user/missing-id tampering;
        the transaction context manager rolls back atomically on any exception.
        """
        async with self._conn.transaction():
            cursor = await self._conn.execute(
                "UPDATE t1_records SET valid_until = %s, superseded_by = %s "
                "WHERE id = %s AND user_id = %s",
                (datetime.now(timezone.utc), new_record.id, old_id, new_record.user_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    f"supersede(): old_id={old_id!r} not found or user_id mismatch; "
                    f"expected user_id={new_record.user_id!r}"
                )
            await self._conn.execute(_INSERT_SQL, _record_params(new_record))
            await self._conn.execute(
                "INSERT INTO t1_vectors (record_id, embedding) VALUES (%s, %s) "
                "ON CONFLICT (record_id) DO UPDATE SET embedding = EXCLUDED.embedding",
                (new_record.id, embedding),
            )

    async def get(self, record_id: str) -> MemoryRecord | None:
        """Fetch a record by id; returns None if not found."""
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT * FROM t1_records WHERE id = %s", (record_id,))
            row = await cur.fetchone()
        return _make_record(row) if row is not None else None

    async def find_by_t0_ref(self, t0_ref: str, user_id: str) -> MemoryRecord | None:
        """Live PROVISIONAL record with this t0_ref, scoped to user_id (CONS-06/07 fence).

        provisional = TRUE keeps a confirmed record from being re-reconciled on rerun;
        user_id predicate is mandatory (no cross-user lookup — D-02/D-03).
        """
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM t1_records "
                "WHERE t0_ref = %s AND user_id = %s "
                "AND valid_until IS NULL AND provisional = TRUE",
                (t0_ref, user_id),
            )
            row = await cur.fetchone()
        return _make_record(row) if row is not None else None

    async def update(self, record_id: str, **fields: object) -> None:
        """Partial update using the column whitelist (T-04-05-01: no SQL injection via names)."""
        if not fields:
            return
        invalid = set(fields.keys()) - _ALLOWED_COLUMNS
        if invalid:
            raise ValueError(f"update() received disallowed field names: {invalid}")

        params: dict[str, object] = {}
        for k, v in fields.items():
            if isinstance(v, (list, dict)):
                params[k] = Jsonb(v) if k in _JSON_COLUMNS else v
            else:
                params[k] = v
        set_clause = ", ".join(f"{col} = %({col})s" for col in fields)
        params["_record_id"] = record_id
        update_sql = f"UPDATE t1_records SET {set_clause} WHERE id = %(_record_id)s"  # noqa: S608
        await self._conn.execute(update_sql, params)  # type: ignore[arg-type]
        await self._conn.commit()

    async def live_records(self, user_id: str) -> AsyncIterator[MemoryRecord]:  # type: ignore[misc]
        """Async generator of live records (valid_until IS NULL) for a user."""
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM t1_records WHERE user_id = %s AND valid_until IS NULL",
                (user_id,),
            )
            async for row in cur:
                yield _make_record(row)

    # -----------------------------------------------------------------------
    # VectorIndex Protocol methods
    # -----------------------------------------------------------------------

    async def upsert_with_vector(self, record: MemoryRecord, embedding: list[float]) -> None:
        """Atomically insert record + vector in one transaction (CR-04 parity)."""
        async with self._conn.transaction():
            await self._conn.execute(_INSERT_SQL, _record_params(record))
            await self._conn.execute(
                "INSERT INTO t1_vectors (record_id, embedding) VALUES (%s, %s) "
                "ON CONFLICT (record_id) DO UPDATE SET embedding = EXCLUDED.embedding",
                (record.id, embedding),
            )

    async def upsert_vector(self, record_id: str, embedding: list[float]) -> None:
        """Insert or replace a vector for record_id."""
        await self._conn.execute(
            "INSERT INTO t1_vectors (record_id, embedding) VALUES (%s, %s) "
            "ON CONFLICT (record_id) DO UPDATE SET embedding = EXCLUDED.embedding",
            (record_id, embedding),
        )
        await self._conn.commit()

    async def vector_search(
        self,
        query_vec: list[float],
        k: int,
        *,
        user_id: str,
        agent_id: str | None = None,
    ) -> list[tuple[str, float]]:
        """KNN (L2) over live records scoped to user_id.

        Pitfall 2: SET hnsw.iterative_scan='strict_order' so the valid_until/user_id
        JOIN filter still returns k rows. Returns (record_id, distance) pairs.
        """
        await self._conn.execute("SET hnsw.iterative_scan = 'strict_order'")
        await self._conn.execute("SET hnsw.ef_search = 100")
        agent_clause = "AND r.agent_id = %(agent_id)s" if agent_id is not None else ""
        sql = f"""
            SELECT v.record_id, (v.embedding <-> %(q)s) AS distance
            FROM t1_vectors v
            JOIN t1_records r ON r.id = v.record_id
            WHERE r.user_id = %(user_id)s
              AND r.valid_until IS NULL
              {agent_clause}
            ORDER BY distance
            LIMIT %(k)s
        """  # noqa: S608 — agent_clause is a constant fragment, values are bound
        params: dict[str, object] = {"q": query_vec, "user_id": user_id, "k": k}
        if agent_id is not None:
            params["agent_id"] = agent_id
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        # WR-02: commit to close the implicit read transaction opened by the SET
        # statements above. Without this, the connection remains "idle in transaction",
        # blocking VACUUM and consuming a max_connections slot unnecessarily.
        await self._conn.commit()
        return [(str(row[0]), float(row[1])) for row in rows]

    async def delete_vector(self, record_id: str) -> None:
        """Remove a vector from the index (record row preserved — FORG-04)."""
        await self._conn.execute(
            "DELETE FROM t1_vectors WHERE record_id = %s", (record_id,)
        )
        await self._conn.commit()

    async def recreate_vector_store(self, new_dim: int) -> None:
        """Drop+recreate the embedding column + HNSW index at new_dim (PROV-07 migration step).

        All existing vector rows are cleared. Call before migrate_embedder()/reindex_all()
        when switching embedder dimension. t1_records — and therefore every protected
        record — is NEVER touched; only the vector column/index is recreated.
        """
        drop_col = "ALTER TABLE t1_vectors DROP COLUMN IF EXISTS embedding"
        add_col = f"ALTER TABLE t1_vectors ADD COLUMN embedding vector({int(new_dim)})"
        async with self._conn.transaction():
            await self._conn.execute("DROP INDEX IF EXISTS idx_t1_vectors_hnsw")
            await self._conn.execute(drop_col)  # type: ignore[arg-type]
            await self._conn.execute(add_col)  # type: ignore[arg-type]
            await self._conn.execute(_DDL_HNSW)  # type: ignore[arg-type]
        self._dim = new_dim

    # -----------------------------------------------------------------------
    # Convenience methods (not Protocol members) — parity with SqliteT1
    # -----------------------------------------------------------------------

    async def get_latest(self, user_id: str) -> MemoryRecord | None:
        """Most recently created live record for user_id (WR-01: valid_until IS NULL)."""
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM t1_records WHERE user_id = %s AND valid_until IS NULL "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            )
            row = await cur.fetchone()
        return _make_record(row) if row is not None else None

    async def get_live_records(self, user_id: str) -> list[MemoryRecord]:
        """All live (valid_until IS NULL) records for user_id as a list."""
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM t1_records WHERE user_id = %s AND valid_until IS NULL",
                (user_id,),
            )
            rows = await cur.fetchall()
        return [_make_record(r) for r in rows]
