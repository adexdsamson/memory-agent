"""Vector index port — T1 dense retrieval (D-07 segregated role).

Separate from RecordStore so backends that don't need vector search (e.g. a
test double or a future audit log) don't have to implement KNN methods.

user_id is non-defaulted after `*` — omitting it raises TypeError (T-1-01 mitigation,
D-03). The adapter's WHERE clause always includes AND r.user_id = :user_id so there
is no code path that returns vectors without scope filtering.

NOTE: k= in sqlite-vec is a global pre-filter, not user-scoped. In a multi-user
index, use k_fetch >> k_desired (Phase 4 concern — see SqliteT1 docstring).

No @runtime_checkable — static checking only (D-10).
"""

from __future__ import annotations

from typing import Protocol


class VectorIndex(Protocol):
    """Contract for T1 dense vector retrieval."""

    async def upsert_vector(self, record_id: str, embedding: list[float]) -> None:
        """Insert or replace a vector for record_id."""
        ...

    async def vector_search(
        self,
        query_vec: list[float],
        k: int,
        *,
        user_id: str,
        agent_id: str | None = None,
    ) -> list[tuple[str, float]]:
        """KNN search over live records scoped to user_id.

        Returns [(record_id, distance), ...] ordered by ascending distance.
        user_id is keyword-only and non-defaulted (D-03).
        """
        ...

    async def delete_vector(self, record_id: str) -> None:
        """Remove a vector from the index."""
        ...
