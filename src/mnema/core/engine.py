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

# ---------------------------------------------------------------------------
# Module-level tunable constants
# ---------------------------------------------------------------------------

KEEP_THRESHOLD: float = 0.3
"""Records with keep_score < KEEP_THRESHOLD are evicted to cold storage (D3-01).

Tune against Phase 5 demo evaluation. 0.3 is the starting point per D3-01.
Half of the keep_score range [0, 1]; a record with no access, average salience (0.5),
and 14+ days of age will typically fall below this threshold.
"""


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
        vault: Any = None,  # VaultStore | None — 6th adapter axis (Phase 3)
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
            vault: Optional T2 canonical vault adapter (VaultStore Protocol — Phase 3).

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
        self._vault: Any = vault

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
        budget: int | None = None,
    ) -> list[MemoryRecord]:
        """Retrieve relevant records for a query, scoped to user_id.

        Phase 3: dense KNN + buffer union + re-rank + optional budget packing.
        Returns MemoryRecord objects re-ranked by relevance × salience × recency_decay.
        If budget is set, applies the two-pass budget packer (RECALL-04/05) to fit
        results under the token limit, always reserving slots for critical facts.

        The `user_id` parameter is non-defaulted — omitting it raises TypeError
        before any DB access (T-1-12 mitigation).

        Args:
            query: Natural-language recall query.
            user_id: Mandatory user scope boundary (D-02, T-1-12).
            agent_id: Optional narrowing filter inside the user boundary.
            k: Dense KNN candidate count.
            budget: Optional token budget. If set, applies the two-pass budget
                packer. If None, returns all re-ranked results (RECALL-03).

        Returns:
            Re-ranked list of MemoryRecord objects. If budget is set, fitted
            to the budget with critical facts (protected/FACT-type) always present.
        """
        return await self._recall_path.execute(
            query, user_id=user_id, agent_id=agent_id, k=k, budget=budget
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
        """Explicitly evict a single record (forced, no keep_score check).

        Performs the 4-step eviction sequence:
          1. set valid_until = now (retire from live index)
          2. delete_vector (remove from KNN index — prevents ghost-record recall)
          3. archive to T0 cold store (recoverable — NEVER hard-delete)
          4. append JSONL audit entry (FORG-04)

        Scope and protection checks:
          - If record does not exist: silently returns (no-op).
          - If record.user_id != user_id: raises ValueError (T-03-01-01).
          - If record.protected: raises ValueError (T-03-01-02).

        Args:
            record_id: The id of the record to evict.
            user_id: Must match record.user_id (scope check).
            reason: Optional reason string appended to the audit entry.
        """
        from datetime import datetime, timezone  # noqa: PLC0415

        now = datetime.now(timezone.utc)

        record: Optional[MemoryRecord] = await self._t1.get(record_id)
        if record is None:
            return  # no-op for nonexistent records

        # T-03-01-01: cross-user scope check
        if record.user_id != user_id:
            raise ValueError(
                f"record {record_id!r} does not belong to user {user_id!r}"
            )

        # T-03-01-02: protected records may never be explicitly forgotten
        if record.protected:
            raise ValueError(
                f"Cannot explicitly forget protected record {record_id!r}"
            )

        # Step 1: retire from live index
        await self._t1.update(record_id, valid_until=now)
        # Step 2: remove from KNN index (ghost-record prevention)
        await self._t1.delete_vector(record_id)
        # Step 3: archive to cold store (recoverable, not a hard-delete)
        await self._t0.archive(record)
        # Step 4: append audit entry (FORG-04)
        entry = {
            "record_id": record_id,
            "user_id": user_id,
            "keep_score": None,
            "evicted_at": now.isoformat(),
            "reason": reason or "explicit_forget",
        }
        await self._t0.append_audit(entry)

    async def evict(self, *, user_id: str) -> int:
        """Run a batch decay-based eviction pass for user_id.

        Consumes decay_pass(self._t1, user_id) and evicts all records whose
        keep_score < KEEP_THRESHOLD using the 4-step eviction sequence:
          1. update valid_until (retire from live index)
          2. delete_vector (remove from KNN index — ghost-record prevention)
          3. archive to T0 cold store (recoverable, never hard-delete — D3-02)
          4. append JSONL audit entry (FORG-04)

        FORG-03: No `not record.protected` guard here — decay_pass structural
        guarantee ensures protected records never reach this point. This is
        intentional: the code comment is the proof, the Hypothesis property test
        (test_protected_records_never_evicted) is the verification.

        Args:
            user_id: The user whose live records to decay-score and evict.

        Returns:
            The count of records evicted in this pass.
        """
        from datetime import datetime, timezone  # noqa: PLC0415

        from mnema.core.decay import decay_pass  # noqa: PLC0415

        now = datetime.now(timezone.utc)
        evicted = 0

        async for record, score in decay_pass(self._t1, user_id, now=now):
            if score >= KEEP_THRESHOLD:
                continue
            # No not-protected guard — decay_pass structural guarantee (FORG-03).
            # Protected records cannot reach this point; proven by Hypothesis test.

            # Step 1: retire from live index
            await self._t1.update(record.id, valid_until=now)
            # Step 2: remove from KNN index (ghost-record prevention)
            await self._t1.delete_vector(record.id)
            # Step 3: archive to cold store (recoverable, not a hard-delete)
            await self._t0.archive(record)
            # Step 4: append audit entry (FORG-04)
            entry = {
                "record_id": record.id,
                "user_id": record.user_id,
                "keep_score": score,
                "evicted_at": now.isoformat(),
                "reason": f"keep_score={score:.4f} < KEEP_THRESHOLD={KEEP_THRESHOLD}",
            }
            await self._t0.append_audit(entry)
            evicted += 1

        return evicted

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
        budget: int | None = None,
    ) -> list[MemoryRecord]:
        """Retrieve relevant records with the bound user_id.

        Args:
            query: Natural-language recall query.
            k: Dense KNN candidate count.
            budget: Optional token budget. If set, applies the two-pass budget
                packer (RECALL-04/05). If None, returns all re-ranked results.

        Returns:
            Re-ranked list of MemoryRecord objects. If budget is set, fitted
            to the budget with critical facts always present (RECALL-05).
        """
        return await self._engine.recall(
            query, user_id=self._user_id, agent_id=self._agent_id, k=k, budget=budget
        )

    async def expand(self, record_id: str) -> Optional[Turn]:
        """Return the verbatim T0 turn for a record, with the bound user_id scope check.

        Args:
            record_id: The MemoryRecord id to expand.

        Returns:
            Turn if found and user matches; None otherwise.
        """
        return await self._engine.expand(record_id, user_id=self._user_id)
