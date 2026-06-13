"""MNEMA MemoryEngine — assembles the five async verbs from pure-logic modules.

MemoryEngine is the single entry point for all memory operations. It wires together:
  - WritePath (fast online write)
  - RecallPath (hybrid retrieval, Phase 1: dense + buffer)
  - RecentSessionBuffer (in-memory freshness layer)
  - T1 (RecordStore + VectorIndex combined adapter, e.g. SqliteT1)
  - T0 (ObjectStorePort, e.g. LocalFS)
  - Scheduler (consolidation trigger)

ARCHITECTURE CONTRACT:
  - This file imports ONLY from mnema.ports.*, mnema.core.schema, mnema.core.*
  - NO concrete adapter classes are imported here.
  - The `t1` parameter satisfies both RecordStore and VectorIndex Protocols by
    structural typing — SqliteT1 implements both.

STARTUP ASSERTION (PROV-06):
  If embedder.dim != t1._dim the constructor raises ValueError before any data
  is written. This catches misconfigured dim at construction time, not at write time.

D-01 SCOPE PASSING (LOCKED):
  - remember(content, *, user_id, session_id, ...) — user_id is non-defaulted
  - recall(query, *, user_id, ...) — user_id is non-defaulted
  - engine.scope(user_id) -> ScopedHandle (ergonomic front door, binds user_id)

D-02 ISOLATION (LOCKED):
  user_id is the hard isolation boundary on every read and write.
  session_id is stamped at write, NEVER used in the recall WHERE-clause.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

from mnema.core.buffer import RecentSessionBuffer
from mnema.core.recall import RecallPath
from mnema.core.schema import MemoryRecord, Turn
from mnema.core.write_path import WritePath

if TYPE_CHECKING:
    from mnema.ports.embedding import EmbeddingProvider
    from mnema.ports.llm import LLMProvider
    from mnema.ports.object_store import ObjectStorePort


class MemoryEngine:
    """Five-verb memory engine: remember, recall, forget, consolidate, expand.

    Construct with four adapters and obtain a ScopedHandle via engine.scope().

    Example usage::

        engine = MemoryEngine(embedder=e, t1=t1, t0=t0, scheduler=s)
        scope = engine.scope(user_id="u1")
        await scope.remember("I am allergic to peanuts", session_id="s1")
        results = await scope.recall("food allergies")
    """

    def __init__(
        self,
        *,
        embedder: "EmbeddingProvider",
        t1: Any,  # structurally satisfies both RecordStore and VectorIndex
        t0: "ObjectStorePort",
        scheduler: Any,  # async Scheduler (see mnema.ports.scheduler.Scheduler)
        llm: "LLMProvider | None" = None,
    ) -> None:
        """Construct MemoryEngine, asserting embedding dim consistency (PROV-06).

        Args:
            embedder: Embedding provider — dim must match t1's vector column width.
            t1: T1 working-memory adapter (must satisfy RecordStore + VectorIndex).
            t0: T0 object store adapter (ObjectStorePort — append/get verbatim turns).
            scheduler: Consolidation scheduler (async Scheduler — awaited trigger_now).
            llm: LLM provider for consolidation (extraction + contradiction judging).
                Defaults to StubLLM() if omitted — backward-compatible default for
                all existing tests that construct MemoryEngine without llm=.

        Raises:
            ValueError: If embedder.dim != t1._dim (PROV-06 startup assertion).
        """
        # PROV-06: startup dim assertion — fail fast before any data is written
        if hasattr(t1, "_dim") and embedder.dim != t1._dim:
            raise ValueError(
                f"Embedding dim mismatch: embedder.dim={embedder.dim} but "
                f"t1 was created with dim={t1._dim}. "
                f"Ensure the embedder and the T1 store use the same vector dimension."
            )

        # Lazy-default StubLLM when llm is omitted (backward-compatible).
        # Import is deferred to runtime only when llm is None — StubLLM is NEVER
        # imported at module level so core/engine.py stays vendor-free at import time.
        if llm is None:
            from mnema.adapters.llm.stub import StubLLM  # noqa: PLC0415
            llm = StubLLM()
        self._llm: "LLMProvider" = llm

        self._embedder: "EmbeddingProvider" = embedder
        self._t1: Any = t1
        self._t0: "ObjectStorePort" = t0
        self._scheduler: Any = scheduler

        # Internal plumbing
        self._buffer: RecentSessionBuffer = RecentSessionBuffer(k=20)
        self._staging: asyncio.Queue[Any] = asyncio.Queue()

        self._write_path: WritePath = WritePath(
            embedder=embedder,
            record_store=t1,
            vector_index=t1,
            t0=t0,
            staging_queue=self._staging,
            buffer=self._buffer,
        )
        self._recall_path: RecallPath = RecallPath(
            embedder=embedder,
            vector_index=t1,
            record_store=t1,
            t0=t0,
            buffer=self._buffer,
        )

        # ConsolidationPipeline — lazy import avoids circular/import-order issues;
        # core/consolidation.py is a peer core module loaded once here.
        from mnema.core.consolidation import ConsolidationPipeline  # noqa: PLC0415
        self._consolidation_pipeline = ConsolidationPipeline(
            llm=self._llm,
            embedder=embedder,
            record_store=t1,
            vector_index=t1,
            staging_queue=self._staging,
        )

    # -------------------------------------------------------------------------
    # Expose t1 for tests that need to verify schema columns directly
    # -------------------------------------------------------------------------

    @property
    def t1(self) -> Any:
        """Expose the T1 adapter for direct inspection in tests."""
        return self._t1

    # -------------------------------------------------------------------------
    # Five async verbs
    # -------------------------------------------------------------------------

    async def remember(
        self,
        content: str,
        *,
        user_id: str,
        session_id: str,
        agent_id: Optional[str] = None,
        type_hint: Optional[str] = None,
        durable: bool = False,
    ) -> str:
        """Store an utterance; optionally write a provisional T1 record.

        This is the fast path: only an embedding call is made (never an LLM call).
        The `user_id` parameter is non-defaulted by design — omitting it raises
        TypeError at the call site before any data is written (T-1-12 mitigation).

        Args:
            content: The utterance text to store.
            user_id: Mandatory user scope boundary (D-02, T-1-12).
            session_id: Session provenance stamped on T0 and T1 records.
            agent_id: Optional narrowing filter inside the user boundary.
            type_hint: Hint for record type ("fact", "preference", "event",
                       "procedure"). Forces a T1 write for known durable types.
            durable: Explicit override to force a provisional T1 write.

        Returns:
            The t0:// reference string for the stored turn.
        """
        t0_ref, _t1_id = await self._write_path.execute(
            content,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            type_hint=type_hint,
            durable=durable,
        )
        return t0_ref

    async def recall(
        self,
        query: str,
        *,
        user_id: str,
        agent_id: Optional[str] = None,
        k: int = 30,
    ) -> list[MemoryRecord]:
        """Retrieve relevant records for a query, scoped to user_id.

        Phase 1: dense KNN + buffer union. Returns MemoryRecord objects with
        access_count incremented for all T1 results.

        The `user_id` parameter is non-defaulted — omitting it raises TypeError
        before any DB access (T-1-12 mitigation).

        Args:
            query: Natural-language recall query.
            user_id: Mandatory user scope boundary (D-02, T-1-12).
            agent_id: Optional narrowing filter inside the user boundary.
            k: Dense KNN candidate count.

        Returns:
            List of MemoryRecord objects, most relevant first (T1 records precede
            buffer-synthesized records).
        """
        return await self._recall_path.execute(
            query, user_id=user_id, agent_id=agent_id, k=k
        )

    async def expand(self, record_id: str, *, user_id: str) -> Optional[Turn]:
        """Return the verbatim T0 turn that backs a T1 record.

        Scope check: if the record does not belong to user_id, returns None
        without fetching any T0 data (T-1-10 mitigation — no T0 data crosses
        user boundaries).

        Args:
            record_id: The MemoryRecord id whose T0 turn to retrieve.
            user_id: Must match the record's user_id (scope check).

        Returns:
            Turn if found and user matches; None otherwise.
        """
        record: Optional[MemoryRecord] = await self._t1.get(record_id)
        if record is None:
            return None
        # T-1-10: scope check — no T0 data crosses user boundaries
        if record.user_id != user_id:
            return None
        if record.t0_ref is None:
            return None
        return await self._t0.get(record.t0_ref)

    async def forget(
        self, record_id: str, *, user_id: str, reason: str = ""
    ) -> None:
        """Mark a record for eviction (stub — Phase 3 will implement decay/eviction).

        Phase 3 will: set valid_until, move to T0 cold storage, clear from vector
        index, add to eviction audit log. For Phase 1 this is a no-op.

        # TODO Phase 3: evict to cold storage — set valid_until, archive to T0/OSS
        """
        pass  # noqa: PIE790

    async def consolidate(self, *, force: bool = False) -> None:
        """Offline consolidation — drain staging queue, extract, resolve, decay.

        Drains the staging queue via ConsolidationPipeline.run(), which:
          1. Extracts typed records from each staged turn (StubLLM in Phase 2)
          2. Safety-pins any protected content via content rule (not LLM)
          3. Reconciles provisional records in place by t0_ref (CONS-06/07)
          4. Entity-resolves new records via cosine KNN (CONS-03)
          5. Applies contradiction/refine/distinct verdict with CONS-08 gate
          6. Runs decay_pass over all live records per user (FORG-01)

        Args:
            force: Reserved for future scheduler-bypass semantics; currently
                has no effect on the pipeline execution.
        """
        await self._consolidation_pipeline.run()
        await self._scheduler.trigger_now()

    # -------------------------------------------------------------------------
    # Ergonomic front door
    # -------------------------------------------------------------------------

    def scope(self, user_id: str, agent_id: Optional[str] = None) -> "ScopedHandle":
        """Return a ScopedHandle with user_id (and optionally agent_id) bound.

        ScopedHandle is the ergonomic API for single-user SDK consumers — it
        eliminates the need to pass user_id on every call.

        Args:
            user_id: The user to bind all operations to.
            agent_id: Optional agent narrowing filter.

        Returns:
            A ScopedHandle bound to this engine and the given user_id.
        """
        return ScopedHandle(engine=self, user_id=user_id, agent_id=agent_id)


class ScopedHandle:
    """Ergonomic front door for single-user SDK consumers (D-01).

    Binds user_id (and optionally agent_id) so callers don't repeat them on
    every call. All methods delegate to the parent MemoryEngine.

    Obtain via::

        scope = engine.scope(user_id="u1")
        await scope.remember("I love spicy food", session_id="s1")
        results = await scope.recall("spicy food")
    """

    def __init__(
        self,
        *,
        engine: MemoryEngine,
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> None:
        self._engine = engine
        self._user_id = user_id
        self._agent_id = agent_id

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def agent_id(self) -> Optional[str]:
        return self._agent_id

    async def remember(
        self,
        content: str,
        *,
        session_id: str,
        type_hint: Optional[str] = None,
        durable: bool = False,
    ) -> str:
        """Store an utterance with the bound user_id.

        Args:
            content: The utterance text to store.
            session_id: Session provenance.
            type_hint: Optional record type hint.
            durable: Explicit T1 write override.

        Returns:
            The t0:// reference string.
        """
        return await self._engine.remember(
            content,
            user_id=self._user_id,
            session_id=session_id,
            agent_id=self._agent_id,
            type_hint=type_hint,
            durable=durable,
        )

    async def recall(
        self,
        query: str,
        *,
        k: int = 30,
    ) -> list[MemoryRecord]:
        """Retrieve relevant records with the bound user_id.

        Args:
            query: Natural-language recall query.
            k: Dense KNN candidate count.

        Returns:
            List of MemoryRecord objects.
        """
        return await self._engine.recall(
            query, user_id=self._user_id, agent_id=self._agent_id, k=k
        )

    async def expand(self, record_id: str) -> Optional[Turn]:
        """Return the verbatim T0 turn for a record, with the bound user_id scope check.

        Args:
            record_id: The MemoryRecord id to expand.

        Returns:
            Turn if found and user matches; None otherwise.
        """
        return await self._engine.expand(record_id, user_id=self._user_id)
