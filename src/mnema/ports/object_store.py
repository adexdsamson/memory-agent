"""Object store port — TIER-01.

Covers T0 raw episodic log (append-only turns) and T1 record archiving (eviction).

append() -> t0://session_id/offset  (used by WritePath, backs expand(id))
get(ref) -> Turn                    (backs RECALL-06 expand)
archive(record) -> ref              (Phase 3 eviction path)

No @runtime_checkable — static checking only (D-10).
"""

from __future__ import annotations

from typing import Protocol

from mnema.core.schema import MemoryRecord, Turn


class ObjectStorePort(Protocol):
    """Contract for a T0 object store backend."""

    async def append(self, session_id: str, turn: Turn) -> str:
        """Append a turn to the session log; returns a t0://session_id/offset ref."""
        ...

    async def get(self, ref: str) -> Turn:
        """Retrieve the turn at the given t0:// ref (backs expand(id))."""
        ...

    async def archive(self, record: MemoryRecord) -> str:
        """Archive a T1 record to cold storage; returns an archive ref."""
        ...
