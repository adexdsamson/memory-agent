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
