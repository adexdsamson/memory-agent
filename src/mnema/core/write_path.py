"""MNEMA fast write path — T0 append + buffer push + optional provisional T1 write.

WritePath orchestrates the hot online-write path:
  1. Append raw turn verbatim to T0 (object store).
  2. Push turn to the in-memory session buffer (no await).
  3. If the classifier identifies a durable claim: embed + write provisional T1 record.
  4. Enqueue {turn, t0_ref} to the staging queue for the offline consolidation consumer.

This is the "cheap and fast" path per the cost model:
  - ONLY `embedder.embed()` is called — never `llm.complete()` (WRITE-03 invariant).
  - LLMProvider is NOT injected into WritePath at all; there is no code path that
    reaches an LLM from here.
  - If no LLM call is ever needed on the write path, the fast path stays cheap.

Architectural note: WritePath imports ONLY from mnema.ports.* and mnema.core.*.
No concrete adapter classes are imported here; this enforces the "core has no
vendor imports" rule from the Architectural Responsibility Map.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

from mnema.core.buffer import RecentSessionBuffer
from mnema.core.classifier import looks_like_durable_claim
from mnema.core.schema import MemoryRecord, RecordType, Turn

if TYPE_CHECKING:
    from mnema.ports.embedding import EmbeddingProvider
    from mnema.ports.object_store import ObjectStorePort
    from mnema.ports.record_store import RecordStore
    from mnema.ports.vector_index import VectorIndex


# Map caller type_hint strings to RecordType enum values
_TYPE_HINT_MAP: dict[str, RecordType] = {
    "fact": RecordType.FACT,
    "preference": RecordType.PREFERENCE,
    "event": RecordType.EVENT,
    "procedure": RecordType.PROCEDURE,
}

# Keywords whose presence sets the protected flag AND forces a durable T1 write
# (D-05 bias / CORE-04). Safety detection is content-driven and independent of
# type_hint — see _is_safety_claim.
_SAFETY_KEYWORDS = frozenset(
    {"allerg", "intolerant", "intolerance", "diabeti", "celiac", "coeliac",
     "anaphyl", "medication", "allergy", "epilep", "seizure"}
)


def _resolve_record_type(type_hint: Optional[str]) -> RecordType:
    """Map a type_hint string to a RecordType enum value.

    Falls back to RecordType.PREFERENCE — the conservative default for any durable
    claim without an explicit type. Consolidation (Phase 2) will re-classify.
    """
    if type_hint is not None:
        mapped = _TYPE_HINT_MAP.get(type_hint.lower())
        if mapped is not None:
            return mapped
    return RecordType.PREFERENCE


def _is_safety_claim(content: str) -> bool:
    """Return True if the content appears to be a safety-relevant claim.

    Safety detection is CONTENT-driven and independent of type_hint. The primary
    use case — `engine.remember("I am allergic to peanuts")` with NO type_hint —
    MUST set protected=True so the fact survives every decay pass by construction
    (core value / D-05 / CORE-04 structural flag). A non-"fact" type_hint does not
    suppress a safety keyword match; the safety axis overrides type classification.
    """
    content_lower = content.lower()
    return any(kw in content_lower for kw in _SAFETY_KEYWORDS)


class WritePath:
    """Fast write path: T0 append → buffer push → optional provisional T1.

    All routing logic lives here; adapters handle I/O only. No LLM is called.
    """

    def __init__(
        self,
        *,
        embedder: "EmbeddingProvider",
        record_store: "RecordStore",
        vector_index: "VectorIndex",
        t0: "ObjectStorePort",
        staging_queue: asyncio.Queue[Any],
        buffer: RecentSessionBuffer,
    ) -> None:
        self._embedder = embedder
        self._record_store = record_store
        self._vector_index = vector_index
        self._t0 = t0
        self._staging_queue = staging_queue
        self._buffer = buffer

    async def execute(
        self,
        content: str,
        *,
        user_id: str,
        session_id: str,
        agent_id: Optional[str] = None,
        type_hint: Optional[str] = None,
        durable: bool = False,
    ) -> tuple[str, Optional[str]]:
        """Execute the fast write path.

        Steps:
          1. Build Turn and append to T0 → t0_ref
          2. Push Turn to in-memory buffer (sync)
          3. If looks_like_durable_claim: embed + write provisional T1
          4. Enqueue {turn, t0_ref} to staging_queue
          5. Return (t0_ref, t1_id | None)

        Args:
            content: The utterance text to store.
            user_id: Mandatory user scope — non-defaulted to prevent accidental omission.
            session_id: Session provenance (stamped on record; NOT used as recall filter).
            agent_id: Optional narrowing filter inside the user boundary.
            type_hint: Caller-supplied type string ("fact", "preference", "event",
                       "procedure"). Forces provisional T1 write for known durable types.
            durable: Explicit override to force a provisional T1 write.

        Returns:
            (t0_ref, t1_id) where t1_id is the provisional record id or None if no
            T1 record was written.
        """
        # Step 1: Build Turn and append to T0 object store
        turn = Turn(session_id=session_id, content=content, role="user")
        t0_ref: str = await self._t0.append(session_id, turn)

        # Step 2: Push to in-memory buffer (no await — purely in-memory)
        self._buffer.push(turn, session_id=session_id, user_id=user_id)

        # Step 3: Conditionally write provisional T1 record.
        # A safety claim ALWAYS forces a durable write, independent of the classifier
        # and type_hint — the core value forbids ever dropping an allergy, so it must
        # never depend on the classifier happening to flag the phrasing as durable.
        t1_id: Optional[str] = None
        is_safety = _is_safety_claim(content)
        if is_safety or looks_like_durable_claim(content, type_hint, durable):
            # ONE embedding call — never an LLM call (WRITE-03)
            embeddings = await self._embedder.embed([content])
            embedding = embeddings[0]

            resolved_type = _resolve_record_type(type_hint)
            protected = is_safety

            record = MemoryRecord(
                user_id=user_id,
                session_id=session_id,
                agent_id=agent_id,
                record_type=resolved_type,
                content=content,
                summary=content[:80].strip(),
                provisional=True,
                protected=protected,
                t0_ref=t0_ref,
                embedding_model=self._embedder.__class__.__name__,
                embedding_dim=self._embedder.dim,
                embedding_version=getattr(self._embedder, "version", None),
            )

            # CR-04: upsert_with_vector atomically writes record + vector in one
            # transaction — a crash between the two cannot leave an orphaned
            # provisional record with no searchable vector.
            await self._record_store.upsert_with_vector(record, embedding)
            t1_id = record.id

        # Step 4: Enqueue to staging queue for offline consolidation consumer.
        # user_id is included so ConsolidationPipeline can scope all T1 operations
        # to the correct user (D-02/D-03 isolation — T-02-13 cross-user guard).
        await self._staging_queue.put({"turn": turn, "t0_ref": t0_ref, "user_id": user_id})

        return (t0_ref, t1_id)
