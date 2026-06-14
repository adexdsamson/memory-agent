"""MNEMA recall path — dense KNN + buffer union + access-count update.

RecallPath orchestrates the hot online-recall path for Phase 1:
  1. Embed the query text (one embedding call).
  2. Dense KNN search over live T1 records scoped to user_id.
  3. Union with in-memory buffer turns for the same user (freshness guarantee).
  4. Fetch MemoryRecord objects for dense hits; synthesize inline records for
     buffer-only turns (turns without a T1 record yet).
  5. Increment access_count for all returned T1 records (reinforcement signal).
  6. Return combined list: T1 records first, buffer-synthesized records appended.

Phase 1 scope:
  - No BM25 / FTS (Phase 2)
  - No graph expansion / RRF fusion (Phase 2)
  - No salience/recency re-ranking (Phase 2)
  - No token-budget packing (Phase 2)

D-02 isolation rule (LOCKED):
  user_id is the hard isolation boundary — mandatory predicate on every read.
  session_id is stamped at write time, NEVER used in the recall WHERE-clause.
  agent_id is an optional narrowing filter inside the user boundary.

Architectural note: RecallPath imports ONLY from mnema.ports.* and mnema.core.*.
No concrete adapter classes are imported here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from mnema.core.buffer import RecentSessionBuffer
from mnema.core.packer import re_rank
from mnema.core.schema import MemoryRecord, RecordType, Turn

if TYPE_CHECKING:
    from mnema.ports.embedding import EmbeddingProvider
    from mnema.ports.object_store import ObjectStorePort
    from mnema.ports.record_store import RecordStore
    from mnema.ports.vector_index import VectorIndex

# re_rank is imported above and re-exported here for external callers
# who import it from mnema.core.recall (per test convention)
__all__ = ["RecallPath", "re_rank"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _turn_to_record(turn: Turn, user_id: str) -> MemoryRecord:
    """Synthesize a provisional MemoryRecord from a buffer-only Turn.

    Buffer turns that haven't been written to T1 yet are represented as
    provisional records with no embedding provenance and no t0_ref (the t0_ref
    is the Turn's own id in a degenerate sense — but we don't fabricate a t0://
    reference here since the turn hasn't been indexed).

    These synthetic records allow callers to treat all recall results uniformly
    as MemoryRecord objects.
    """
    return MemoryRecord(
        id=turn.id,  # reuse the turn id so deduplication works on id
        user_id=user_id,
        session_id=turn.session_id,
        record_type=RecordType.PREFERENCE,  # conservative default for buffer turns
        content=turn.content,
        summary=turn.content[:80].strip(),
        provisional=True,
        t0_ref=None,  # no persistent T1 record yet
        created_at=turn.created_at,
    )


class RecallPath:
    """Recall path: dense KNN + buffer union + access-count update.

    Pure logic (scoring/dedup) stays sync inside this class; I/O is async.
    """

    def __init__(
        self,
        *,
        embedder: "EmbeddingProvider",
        vector_index: "VectorIndex",
        record_store: "RecordStore",
        t0: "ObjectStorePort",
        buffer: RecentSessionBuffer,
    ) -> None:
        self._embedder = embedder
        self._vector_index = vector_index
        self._record_store = record_store
        self._t0 = t0
        self._buffer = buffer

    async def execute(
        self,
        query: str,
        *,
        user_id: str,
        agent_id: Optional[str] = None,
        k: int = 30,
    ) -> list[MemoryRecord]:
        """Execute the recall path for a user query.

        Args:
            query: The natural-language recall query.
            user_id: Mandatory user scope — non-defaulted (D-02).
            agent_id: Optional narrowing filter inside the user boundary.
            k: Number of dense KNN candidates to retrieve from the vector index.

        Returns:
            List of MemoryRecord objects, T1 records first (full provenance),
            buffer-synthesized records appended (buffer-wins on content dedup).
        """
        # Step 1: Embed the query text
        q_vec = (await self._embedder.embed([query]))[0]

        # Step 2: Dense KNN search over live T1 records (user-scoped by adapter)
        dense_hits: list[tuple[str, float]] = await self._vector_index.vector_search(
            q_vec, k, user_id=user_id, agent_id=agent_id
        )
        dense_ids: set[str] = {hit[0] for hit in dense_hits}

        # Step 3: Fetch MemoryRecord objects for dense hits
        t1_records: list[MemoryRecord] = []
        for record_id, _ in dense_hits:
            record = await self._record_store.get(record_id)
            if record is not None:
                t1_records.append(record)

        # Track T1 ids AND contents for deduplication. A just-written fact lives in
        # BOTH the buffer (a Turn, id "turn_*") and T1 (a MemoryRecord, id "mem_*")
        # with DIFFERENT ids, so id-only dedup misses it and the same content
        # surfaces twice. The T1 record carries full provenance + t0_ref + embedding,
        # so it always wins; a buffer turn is emitted only when its content is not
        # already represented in T1 (and not duplicated within the buffer itself).
        t1_ids: set[str] = {r.id for r in t1_records}
        t1_contents: set[str] = {r.content for r in t1_records}

        # Step 4: Union with buffer turns for this user
        buffer_turns: list[Turn] = self._buffer.as_candidates_for_user(user_id)

        buffer_records: list[MemoryRecord] = []
        seen_buffer_contents: set[str] = set()
        for turn in buffer_turns:
            if turn.id in t1_ids or turn.id in dense_ids:
                continue
            if turn.content in t1_contents or turn.content in seen_buffer_contents:
                continue
            seen_buffer_contents.add(turn.content)
            buffer_records.append(_turn_to_record(turn, user_id=user_id))

        # Step 5: Increment access_count for T1 records
        now = _utcnow()
        for record in t1_records:
            await self._record_store.update(
                record.id,
                access_count=record.access_count + 1,
                last_accessed=now,
            )
            # Update the in-memory object too so callers see the incremented count
            object.__setattr__(record, "access_count", record.access_count + 1)

        # Step 6: Return T1 records first, buffer-only records appended
        return t1_records + buffer_records
