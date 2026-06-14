"""Record store port — T1 typed-record CRUD (D-07 segregated role).

Separate from VectorIndex so implementations can satisfy one or both roles
structurally without forcing a combined interface on backends that only do one.

live_records() returns an async iterator of all live (valid_until IS NULL) records
for a user — used by Phase 3 forgetting/decay pass to iterate the full T1 working set.

No @runtime_checkable — static checking only (D-10).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from mnema.core.schema import MemoryRecord


class RecordStore(Protocol):
    """Contract for T1 typed-record persistence."""

    async def upsert(self, record: MemoryRecord) -> None:
        """Insert or replace a record (keyed by record.id)."""
        ...

    async def get(self, record_id: str) -> MemoryRecord | None:
        """Fetch a record by id; returns None if not found."""
        ...

    async def update(self, record_id: str, **fields: object) -> None:
        """Partial update — only the supplied fields are written."""
        ...

    async def live_records(self, user_id: str) -> AsyncIterator[MemoryRecord]:
        """Async generator of live records (valid_until IS NULL) for a user."""
        ...

    async def supersede(
        self,
        old_id: str,
        new_record: MemoryRecord,
        embedding: list[float],
    ) -> None:
        """Atomically retire old_id and insert new_record + embedding in one transaction.

        Sets valid_until + superseded_by on the old record and inserts the new record
        with its vector in a single SQLite transaction. Raises on failure after rollback.
        old_id must belong to user_id == new_record.user_id (enforced by AND user_id predicate).
        Used by ConsolidationPipeline for CONS-04 atomic contradiction resolution.
        """
        ...

    async def find_by_t0_ref(
        self,
        t0_ref: str,
        user_id: str,
    ) -> MemoryRecord | None:
        """Return the live provisional record with this t0_ref, scoped to user_id.

        Only live records (valid_until IS NULL) are returned.
        Returns None if no matching live record exists.
        Used by ConsolidationPipeline for CONS-06/07 provisional reconciliation
        (idempotency fence — prevents duplicate live records on rerun).
        """
        ...

    async def upsert_with_vector(
        self,
        record: MemoryRecord,
        embedding: list[float],
    ) -> None:
        """Atomically insert record + vector in one transaction (CR-04).

        Wraps the INSERT into t1_records and the INSERT OR REPLACE into vec_t1
        in a single BEGIN/COMMIT block so a crash between the two statements
        cannot leave an orphaned record with no searchable vector.

        Used by ConsolidationPipeline._insert_new_confirmed() and WritePath for
        the provisional fast-path write.
        """
        ...
