"""SqliteT1 — local T1 working-memory adapter.

Satisfies both RecordStore and VectorIndex Protocols by structural typing
(no inheritance from the Protocol classes — D-08).

Single aiosqlite connection; sqlite-vec loaded once per connection (Pitfall 1).
PRAGMA journal_mode=WAL enables concurrent reads with the single-writer model.

IMPORTANT (Phase 4 note): vec_t1's k= parameter is a GLOBAL pre-filter, not
user-scoped. In a multi-user index, pass k_fetch >> k_desired (e.g. k * 4) so
the JOIN filter can find k results for the target user after vec0 returns k
global candidates. Phase 1 is single-user in tests — k=30 is sufficient.
See Pitfall 2 in 01-RESEARCH.md.

Thread-safety: aiosqlite pins the connection to one OS thread. All methods are
async and may only be called from the event loop — do NOT share across threads.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import numpy as np
import sqlite_vec  # type: ignore[import-untyped]

from mnema.core.schema import MemoryRecord

# ---------------------------------------------------------------------------
# Allowed field names for the parameterized UPDATE whitelist (T-1-05 mitigation)
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

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
_DDL_T1_RECORDS = """
CREATE TABLE IF NOT EXISTS t1_records (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    agent_id        TEXT,
    record_type     TEXT NOT NULL,
    content         TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    keywords        TEXT NOT NULL DEFAULT '[]',
    embedding_model TEXT,
    embedding_dim   INTEGER,
    embedding_version TEXT,
    protected       INTEGER NOT NULL DEFAULT 0,
    salience        REAL NOT NULL DEFAULT 0.5,
    confidence      REAL NOT NULL DEFAULT 0.9,
    provisional     INTEGER NOT NULL DEFAULT 1,
    valid_from      TEXT NOT NULL,
    valid_until     TEXT,
    superseded_by   TEXT,
    t0_ref          TEXT,
    source_refs     TEXT NOT NULL DEFAULT '[]',
    access_count    INTEGER NOT NULL DEFAULT 0,
    last_accessed   TEXT,
    created_at      TEXT NOT NULL,
    graph_edges     TEXT NOT NULL DEFAULT '[]'
)
"""

_DDL_IDX_LIVE_USER = """
CREATE INDEX IF NOT EXISTS idx_t1_live_user
    ON t1_records(user_id, agent_id)
    WHERE valid_until IS NULL
"""

# ---------------------------------------------------------------------------
# Shared INSERT SQL and parameter builder (used by upsert() and supersede())
# ---------------------------------------------------------------------------
_INSERT_SQL = """
INSERT OR REPLACE INTO t1_records (
    id, user_id, session_id, agent_id, record_type, content, summary,
    keywords, embedding_model, embedding_dim, embedding_version,
    protected, salience, confidence, provisional,
    valid_from, valid_until, superseded_by, t0_ref, source_refs,
    access_count, last_accessed, created_at, graph_edges
) VALUES (
    :id, :user_id, :session_id, :agent_id, :record_type, :content, :summary,
    :keywords, :embedding_model, :embedding_dim, :embedding_version,
    :protected, :salience, :confidence, :provisional,
    :valid_from, :valid_until, :superseded_by, :t0_ref, :source_refs,
    :access_count, :last_accessed, :created_at, :graph_edges
)
"""


# ---------------------------------------------------------------------------
# Row factory
# ---------------------------------------------------------------------------
def _make_record(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> MemoryRecord:
    """Convert a sqlite3 row to a MemoryRecord via Pydantic model_validate.

    JSON columns are deserialized; SQLite integer booleans are cast to Python bool.
    """
    cols = [d[0] for d in cursor.description]
    row_dict: dict[str, Any] = dict(zip(cols, row))

    # Deserialize JSON-stored list columns
    for col in ("keywords", "source_refs", "graph_edges"):
        val = row_dict.get(col)
        if isinstance(val, str):
            row_dict[col] = json.loads(val)

    # Cast INTEGER → bool (T-1-07 mitigation: explicit cast, never trust raw int)
    row_dict["protected"] = bool(row_dict.get("protected", 0))
    row_dict["provisional"] = bool(row_dict.get("provisional", 1))

    return MemoryRecord.model_validate(row_dict)


def _dt_to_str(dt: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601 string for SQLite storage."""
    if dt is None:
        return None
    return dt.isoformat()


def _v32(vec: list[float]) -> bytes:
    """Serialize a float list to float32 bytes for sqlite-vec. Never pass a Python list."""
    return np.array(vec, dtype=np.float32).tobytes()


def _record_params(record: MemoryRecord) -> dict[str, object]:
    """Build the full parameter dict for _INSERT_SQL from a MemoryRecord.

    Serialization rules:
    - bool columns: int() cast (T-1-07 mitigation for SQLite integer storage)
    - list columns: json.dumps()
    - datetime columns: _dt_to_str()
    - record_type enum: str(record.record_type.value)
    """
    return {
        "id": record.id,
        "user_id": record.user_id,
        "session_id": record.session_id,
        "agent_id": record.agent_id,
        "record_type": str(record.record_type.value),
        "content": record.content,
        "summary": record.summary,
        "keywords": json.dumps(record.keywords),
        "embedding_model": record.embedding_model,
        "embedding_dim": record.embedding_dim,
        "embedding_version": record.embedding_version,
        "protected": int(record.protected),  # T-1-07: explicit cast
        "salience": record.salience,
        "confidence": record.confidence,
        "provisional": int(record.provisional),
        "valid_from": _dt_to_str(record.valid_from),
        "valid_until": _dt_to_str(record.valid_until),
        "superseded_by": record.superseded_by,
        "t0_ref": record.t0_ref,
        "source_refs": json.dumps(record.source_refs),
        "access_count": record.access_count,
        "last_accessed": _dt_to_str(record.last_accessed),
        "created_at": _dt_to_str(record.created_at),
        "graph_edges": json.dumps(record.graph_edges),
    }


# ---------------------------------------------------------------------------
# SqliteT1
# ---------------------------------------------------------------------------
class SqliteT1:
    """T1 working-memory adapter over aiosqlite + sqlite-vec.

    Satisfies RecordStore + VectorIndex Protocols by structural typing.
    """

    def __init__(self, db: aiosqlite.Connection, dim: int) -> None:
        self._db = db
        self._dim = dim

    @property
    def dim(self) -> int:
        """Vector column dimension this adapter was opened with."""
        return self._dim

    @classmethod
    async def open(cls, db_path: str, dim: int) -> "SqliteT1":
        """Open (or create) a T1 database.

        Loads sqlite-vec, creates t1_records + partial index + vec_t1 virtual table.
        """
        db = await aiosqlite.connect(db_path)
        # Load sqlite-vec extension (must happen on every new connection — Pitfall 1)
        await db.enable_load_extension(True)
        await db.load_extension(sqlite_vec.loadable_path())  # aiosqlite-compatible pattern
        await db.enable_load_extension(False)

        # WAL mode for better concurrent-read performance
        await db.execute("PRAGMA journal_mode=WAL")

        # Create tables
        await db.execute(_DDL_T1_RECORDS)
        await db.execute(_DDL_IDX_LIVE_USER)
        await db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_t1 USING vec0("
            f"record_id TEXT PRIMARY KEY, embedding float[{dim}])"
        )
        await db.commit()

        # Set row factory so SELECT queries return MemoryRecord objects
        db.row_factory = _make_record  # type: ignore[assignment]

        return cls(db, dim)

    # -----------------------------------------------------------------------
    # RecordStore Protocol methods
    # -----------------------------------------------------------------------

    async def upsert(self, record: MemoryRecord) -> None:
        """Insert or replace a record (keyed by record.id)."""
        await self._db.execute(_INSERT_SQL, _record_params(record))
        await self._db.commit()

    async def supersede(
        self,
        old_id: str,
        new_record: MemoryRecord,
        embedding: list[float],
    ) -> None:
        """Atomically retire old_id and insert new_record + embedding in one transaction.

        Transaction wraps three statements:
        1. UPDATE t1_records SET valid_until=?, superseded_by=? WHERE id=? AND user_id=?
           (user_id predicate prevents cross-user tampering — T-02-05)
        2. INSERT OR REPLACE new_record via _INSERT_SQL + _record_params()
           (new_record.graph_edges must already carry the supersedes edge)
        3. INSERT OR REPLACE vec_t1(record_id, embedding) for the new vector

        On any exception: rollback and re-raise (T-02-06 atomicity guarantee).
        """
        now_str = _dt_to_str(datetime.now(timezone.utc))
        try:
            await self._db.execute("BEGIN")  # CR-02: explicit BEGIN required — aiosqlite is autocommit by default
            cursor = await self._db.execute(
                "UPDATE t1_records SET valid_until=?, superseded_by=? WHERE id=? AND user_id=?",
                (now_str, new_record.id, old_id, new_record.user_id),
            )
            # WR-04: assert rowcount==1; rollback + raise on cross-user or missing old_id
            if cursor.rowcount != 1:
                await self._db.rollback()
                raise ValueError(
                    f"supersede(): old_id={old_id!r} not found or user_id mismatch; "
                    f"expected user_id={new_record.user_id!r}"
                )
            await self._db.execute(_INSERT_SQL, _record_params(new_record))
            await self._db.execute(
                "INSERT OR REPLACE INTO vec_t1(record_id, embedding) VALUES (?, ?)",
                (new_record.id, _v32(embedding)),
            )
            await self._db.commit()
        except Exception:
            await self._db.rollback()
            raise

    async def get(self, record_id: str) -> MemoryRecord | None:
        """Fetch a record by id; returns None if not found."""
        cursor = await self._db.execute(
            "SELECT * FROM t1_records WHERE id = ?", (record_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        # row_factory already converted it to MemoryRecord
        return row  # type: ignore[return-value]

    async def find_by_t0_ref(self, t0_ref: str, user_id: str) -> MemoryRecord | None:
        """Return the live provisional record with this t0_ref, scoped to user_id.

        Idempotency fence for provisional record reconciliation (CONS-06/07).
        Returns the live provisional record with this t0_ref, or None if no such record exists.
        Only live records (valid_until IS NULL) are returned — superseded provisionals are excluded.

        user_id predicate is mandatory — no cross-user lookup (D-02/D-03, T-02-07).
        """
        cursor = await self._db.execute(
            # CR-03: AND provisional = 1 is the CONS-06/07 idempotency fence —
            # a confirmed (provisional=0) record must NOT be re-reconciled on rerun.
            "SELECT * FROM t1_records "
            "WHERE t0_ref = ? AND user_id = ? AND valid_until IS NULL AND provisional = 1",
            (t0_ref, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return row  # type: ignore[return-value]

    async def update(self, record_id: str, **fields: object) -> None:
        """Partial update using a column whitelist (T-1-05: no SQL injection via field names).

        Only field names present in _ALLOWED_COLUMNS are accepted.
        Field values are bound as parameters (never interpolated).
        """
        if not fields:
            return

        # Validate column names against whitelist
        invalid = set(fields.keys()) - _ALLOWED_COLUMNS
        if invalid:
            raise ValueError(f"update() received disallowed field names: {invalid}")

        # Serialize special types
        serialized: dict[str, object] = {}
        for k, v in fields.items():
            if isinstance(v, datetime):
                serialized[k] = _dt_to_str(v)
            elif isinstance(v, (list, dict)):
                serialized[k] = json.dumps(v)
            elif isinstance(v, bool):
                # WR-05: generalize to ALL bool columns, not just named ones —
                # prevents any future bool field from being stored as True/False strings.
                serialized[k] = int(v)
            else:
                serialized[k] = v

        set_clause = ", ".join(f"{col} = :{col}" for col in serialized)
        serialized["_record_id"] = record_id

        await self._db.execute(
            f"UPDATE t1_records SET {set_clause} WHERE id = :_record_id",  # noqa: S608
            serialized,
        )
        await self._db.commit()

    async def live_records(self, user_id: str) -> AsyncIterator[MemoryRecord]:  # type: ignore[misc]
        """Async generator of live records (valid_until IS NULL) for a user."""
        cursor = await self._db.execute(
            "SELECT * FROM t1_records WHERE user_id = ? AND valid_until IS NULL",
            (user_id,),
        )
        async for row in cursor:
            yield row  # type: ignore[misc]

    # -----------------------------------------------------------------------
    # VectorIndex Protocol methods
    # -----------------------------------------------------------------------

    async def upsert_vector(self, record_id: str, embedding: list[float]) -> None:
        """Insert or replace a vector for record_id.

        CRITICAL: serialize as float32 bytes — never pass a Python list directly.
        """
        await self._db.execute(
            "INSERT OR REPLACE INTO vec_t1(record_id, embedding) VALUES (?, ?)",
            (record_id, _v32(embedding)),
        )
        await self._db.commit()

    async def vector_search(
        self,
        query_vec: list[float],
        k: int,
        *,
        user_id: str,
        agent_id: str | None = None,
    ) -> list[tuple[str, float]]:
        """KNN search over live records scoped to user_id.

        NOTE: k= is a global pre-filter; in a multi-user index use k_fetch >> k_desired
        (Phase 4 concern — see module docstring).
        """
        q_bytes = _v32(query_vec)
        agent_clause = "AND r.agent_id = :agent_id" if agent_id is not None else ""

        sql = f"""
            SELECT v.record_id, v.distance
            FROM vec_t1 v
            JOIN t1_records r ON r.id = v.record_id
            WHERE v.embedding MATCH :q
              AND v.k = :k
              AND r.user_id = :user_id
              AND r.valid_until IS NULL
              {agent_clause}
            ORDER BY v.distance
        """  # noqa: S608

        params: dict[str, object] = {"q": q_bytes, "k": k, "user_id": user_id}
        if agent_id is not None:
            params["agent_id"] = agent_id

        # Use a raw cursor with the default row factory so the _make_record
        # row factory (set on the connection) is not applied to the 2-column
        # (record_id, distance) result from vec_t1.
        cursor = await self._db.execute(sql, params)
        cursor.row_factory = None  # type: ignore[assignment]
        rows = await cursor.fetchall()
        return [(str(row[0]), float(row[1])) for row in rows]

    async def delete_vector(self, record_id: str) -> None:
        """Remove a vector from the index."""
        await self._db.execute(
            "DELETE FROM vec_t1 WHERE record_id = ?", (record_id,)
        )
        await self._db.commit()

    # -----------------------------------------------------------------------
    # Convenience methods (not Protocol members)
    # -----------------------------------------------------------------------

    async def get_latest(self, user_id: str) -> MemoryRecord | None:
        """Return the most recently created live record for user_id.

        Used by test_fast_write_schema_columns to verify schema columns.
        WR-01 fix: filters valid_until IS NULL so superseded records are excluded.
        """
        cursor = await self._db.execute(
            "SELECT * FROM t1_records WHERE user_id = ? AND valid_until IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return row  # type: ignore[return-value]

    async def get_live_records(self, user_id: str) -> list[MemoryRecord]:
        """Return all live (valid_until IS NULL) records for user_id as a list.

        Convenience method for tests; returns a materialised list rather than
        an async iterator.
        """
        cursor = await self._db.execute(
            "SELECT * FROM t1_records WHERE user_id = ? AND valid_until IS NULL",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return list(rows)  # type: ignore[arg-type]
