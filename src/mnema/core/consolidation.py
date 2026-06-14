"""MNEMA ConsolidationPipeline — offline extraction, entity resolution,
atomic supersession, and provisional reconciliation.

Architectural note: imports ONLY from mnema.ports.* and mnema.core.*.
No concrete adapter classes at runtime (TYPE_CHECKING only).
D-05/D-06: safety pinning via content rule (_is_safety_claim) — never LLM salience.
CONS-08: structural pre-check gates supersession for protected/FACT records.

Pipeline steps (per RESEARCH.md §System Architecture Diagram):
  1. Drain asyncio.Queue (Engine owns the queue; Pipeline drains on each run())
  2. LLM extraction — one complete() call per staged turn (sentinel: EXTRACT_RECORDS:)
  3. Safety pin pass — content rule overrides LLM salience (_is_safety_claim, D-05)
  4. Reconcile-by-t0_ref — upgrade provisional in place if t0_ref match (CONS-06/07)
  5. Entity resolution — embed new content; KNN over live records (ENTITY_MAX_DISTANCE)
  6. Contradiction judge — CONS-08 gate: protected/FACT → contradiction_pending edge only
  7. decay_pass — compute keep_score over all live records after batch (FORG-01)
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from mnema.core.schema import MemoryRecord, RecordType
from mnema.core.write_path import _is_safety_claim  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from mnema.ports.embedding import EmbeddingProvider
    from mnema.ports.llm import LLMProvider
    from mnema.ports.record_store import RecordStore
    from mnema.ports.vector_index import VectorIndex


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

ENTITY_MAX_DISTANCE: float = math.sqrt(2.0 - 2.0 * 0.85)
"""L2-distance threshold ≈ cosine similarity >= 0.85 for L2-normalized vectors.

Computed as math.sqrt(2.0 - 2.0 * 0.85) per RESEARCH.md Pitfall 4. Two unit
vectors with cosine similarity ≥ 0.85 have L2 distance ≤ 0.5477. Candidates at
or below this threshold are considered the same entity for contradiction judging.
"""

_EXTRACT_SENTINEL: str = "EXTRACT_RECORDS:"
"""Prompt sentinel that signals extraction mode to the LLM adapter.

The real QwenLLMProvider in Phase 4 must use this same sentinel — it is part of
the consolidation pipeline's prompt protocol, not an artifact of the stub.
"""

_JUDGE_SENTINEL: str = "JUDGE_CONTRADICTION:"
"""Prompt sentinel that signals contradiction-judge mode to the LLM adapter.

Verdict contract: LLM must return exactly one of "contradict", "refine", or
"distinct" (case-insensitive). Any other response is treated as "distinct".
"""


# ---------------------------------------------------------------------------
# ConsolidationPipeline
# ---------------------------------------------------------------------------


class ConsolidationPipeline:
    """Offline pipeline that turns staged turns into clean, typed, deduped records.

    Orchestrates steps 2-7 of the consolidation architecture. Designed to be
    constructed once (inside MemoryEngine.__init__) and called repeatedly via
    run() for each consolidation pass.

    The staging queue is shared with WritePath — ConsolidationPipeline drains
    it non-destructively via get_nowait() and processes each item atomically.
    """

    def __init__(
        self,
        *,
        llm: "LLMProvider",
        embedder: "EmbeddingProvider",
        record_store: "RecordStore",
        vector_index: "VectorIndex",
        staging_queue: asyncio.Queue[Any],
    ) -> None:
        """Construct the pipeline with all five injected collaborators.

        All parameters are keyword-only to prevent positional-order bugs.
        No concrete adapter classes are imported here — structural typing only
        (D-07/D-08/D-10).

        Args:
            llm: LLM provider for extraction and contradiction judging.
            embedder: Embedding provider for new-record entity resolution.
            record_store: RecordStore (upsert/get/update/supersede/find_by_t0_ref).
            vector_index: VectorIndex (vector_search/upsert_vector).
            staging_queue: asyncio.Queue drained on each run().
        """
        self._llm = llm
        self._embedder = embedder
        self._record_store = record_store
        self._vector_index = vector_index
        self._staging_queue = staging_queue

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    async def run(self) -> None:
        """Drain the staging queue and process all staged turns (steps 1-7).

        Idempotent: re-running on an empty queue is a no-op. If a t0_ref was
        already reconciled in a prior run, find_by_t0_ref returns the upgraded
        record and no duplicate is inserted (CONS-07).
        """
        # Step 1: Drain the staging queue
        items = self._drain_queue()

        # Steps 2-6: Process each staged turn
        for item in items:
            turn = item["turn"]
            t0_ref = item["t0_ref"]
            # user_id is propagated from WritePath.execute() into the staging item
            # (Task 2 adds this key). An empty string is the safe fallback for any
            # item written by a pre-Task-2 WritePath; all T1 queries will return
            # empty results for "" so no cross-user data leak is possible.
            user_id: str = item.get("user_id", "")
            session_id: str = turn.session_id
            await self._process_turn(turn.content, t0_ref, user_id, session_id)

        # Step 7: decay_pass over all live records, per unique user_id processed.
        # In Phase 2 we collect unique user_ids from the drained items and run one
        # pass per user. Phase 3 will consume the yielded scores for eviction
        # decisions; Phase 2 simply runs the pass (FORG-01 requirement).
        from mnema.core.decay import decay_pass  # noqa: PLC0415

        processed_user_ids: set[str] = {
            item.get("user_id", "")
            for item in items
            if item.get("user_id")
        }
        for uid in processed_user_ids:
            async for _record, _score in decay_pass(self._record_store, uid):
                pass  # Phase 3 will act on scores; Phase 2 exercises the code path

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _drain_queue(self) -> list[dict[str, Any]]:
        """Drain the asyncio.Queue using get_nowait() until QueueEmpty.

        Returns all items that were in the queue at call time as a plain list.
        This is a synchronous snapshot — any items enqueued AFTER this call
        will be picked up on the next run().
        """
        items: list[dict[str, Any]] = []
        while True:
            try:
                items.append(self._staging_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return items

    async def _process_turn(
        self,
        content: str,
        t0_ref: str,
        user_id: str,
        session_id: str,
    ) -> None:
        """Extract records from one staged turn and reconcile/resolve each.

        Steps 2-6 of the pipeline per turn. Multiple records may be extracted
        from a single turn (Phase 4 real LLM); StubLLM produces exactly 1 per
        content in Phase 2. A malformed LLM response (non-JSON) is silently
        skipped — the turn remains in T0 and can be reprocessed.
        """
        # Step 2: LLM extraction (sentinel: EXTRACT_RECORDS:)
        extraction_prompt = f"{_EXTRACT_SENTINEL} {content}"
        raw_response = await self._llm.complete(extraction_prompt)
        try:
            parsed: Any = json.loads(raw_response)
        except (json.JSONDecodeError, ValueError):
            # T-02-09: malformed JSON — skip this turn (LLM cannot inject SQL)
            return

        if not isinstance(parsed, list):
            return  # Defensive: LLM returned valid JSON but wrong shape

        # Cast: json.loads returns Any; we've confirmed it is a list above.
        # Filter to dicts only (defensive) and cast to the expected element type.
        extracted_list: list[dict[str, Any]] = []
        for item in parsed:  # type: ignore[union-attr]
            if isinstance(item, dict):
                extracted_list.append(item)  # type: ignore[arg-type]
        for ext in extracted_list:

            extracted_content = str(ext.get("content", content))

            # Step 3: Safety pin pass — content rule OVERRIDES LLM salience (D-05/D2-03)
            # _is_safety_claim is imported from write_path; never duplicated.
            if _is_safety_claim(extracted_content):
                ext["protected"] = True
                ext["salience"] = 1.0
                ext["record_type"] = "fact"
            else:
                # Only set defaults where the LLM omitted a field
                ext.setdefault("protected", False)
                ext.setdefault("salience", 0.5)
                ext.setdefault("record_type", "preference")

            # Step 4: Reconcile-by-t0_ref (CONS-06/07 idempotency fence)
            # If a provisional record for this t0_ref already exists in T1, upgrade
            # it in place. Never delete-and-reinsert (D2-12).
            existing_provisional = await self._record_store.find_by_t0_ref(
                t0_ref, user_id
            )
            if existing_provisional is not None:
                # Upgrade in place: clear provisional flag and update extracted fields.
                # T-02-11: protected flag is monotonic upward — consolidation can SET
                # but NEVER CLEAR it. Recompute protected_final after safety gate.
                protected_final = (
                    bool(ext.get("protected", False)) or existing_provisional.protected
                )

                await self._record_store.update(
                    existing_provisional.id,
                    provisional=False,
                    record_type=str(ext.get("record_type", "preference")),
                    salience=float(ext.get("salience", 0.5)),
                    summary=str(ext.get("summary", extracted_content[:60])).strip(),
                    keywords=list(ext.get("keywords", [])),
                    protected=protected_final,
                )
                # No entity resolution needed for reconciled provisionals (D2-04:
                # reuse existing embedding; no new embed call).
                continue

            # Step 5: Entity resolution — embed new content (one embed call per new record)
            embeddings = await self._embedder.embed([extracted_content])
            embedding = embeddings[0]

            # Map extracted record_type string to RecordType enum (default: PREFERENCE)
            try:
                record_type_enum = RecordType(ext.get("record_type", "preference"))
            except ValueError:
                record_type_enum = RecordType.PREFERENCE

            # KNN over live records scoped to user_id; type-narrow to same record_type
            candidates = await self._vector_index.vector_search(
                embedding, k=5, user_id=user_id
            )
            near_match: Optional[MemoryRecord] = None
            for cand_id, dist in candidates:
                if dist <= ENTITY_MAX_DISTANCE:
                    cand = await self._record_store.get(cand_id)
                    if cand is not None and cand.record_type == record_type_enum:
                        near_match = cand
                        break

            if near_match is None:
                # No similar entity found → insert as new confirmed record
                await self._insert_new_confirmed(
                    ext, extracted_content, embedding, user_id, session_id, t0_ref
                )
            else:
                # Step 6: Contradiction judge — ask LLM to classify the match
                judge_prompt = (
                    f"{_JUDGE_SENTINEL} {near_match.content}\n{extracted_content}"
                )
                verdict = (await self._llm.complete(judge_prompt)).strip().lower()
                await self._apply_verdict(
                    verdict,
                    near_match,
                    ext,
                    extracted_content,
                    embedding,
                    user_id,
                    session_id,
                    t0_ref,
                )

    async def _apply_verdict(
        self,
        verdict: str,
        existing: MemoryRecord,
        ext: dict[str, Any],
        new_content: str,
        embedding: list[float],
        user_id: str,
        session_id: str,
        t0_ref: str,
    ) -> None:
        """Apply a contradiction/refine/distinct verdict with the CONS-08 gate.

        CONS-08 (load-bearing safety invariant):
          If the existing record is protected OR record_type == FACT, the LLM's
          "contradict" verdict NEVER triggers supersession. Instead a
          contradiction_pending graph edge is appended to the existing record as
          an audit trail, and the record stays live.

        The two-branch early return is at the TOP of the contradict block — not
        nested inside the supersession path — so there is no code path that can
        accidentally fall through to supersession for a protected/FACT record.
        """
        if verdict == "refine":
            # CONS-05: non-contradicting refinement — merge into existing record in place.
            # Merge: overwrite content + summary, update salience and keywords.
            await self._record_store.update(
                existing.id,
                content=new_content,
                summary=new_content[:60].strip(),
                salience=float(ext.get("salience", existing.salience)),
                keywords=list(ext.get("keywords", existing.keywords)),
            )
            return

        if verdict == "contradict":
            # CONS-08: structural gate — ALWAYS check protected/FACT FIRST.
            # This two-branch structure means there is NO code path from
            # "contradict + protected/FACT" to the supersession branch below.
            if existing.protected or existing.record_type == RecordType.FACT:
                # T-02-10: record contradiction_pending edge on existing record.
                # Pitfall 5: new list — never mutate existing.graph_edges in place.
                new_edge: dict[str, Any] = {
                    "rel": "contradiction_pending",
                    "target": f"unresolved_{t0_ref}",
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                new_edges = list(existing.graph_edges) + [new_edge]
                await self._record_store.update(existing.id, graph_edges=new_edges)
                return  # Existing record remains live — NO supersession

            # Not protected/FACT → atomic supersession (CONS-04).
            # The supersedes edge is part of the new record's graph_edges — committed
            # atomically with the record insert inside SqliteT1.supersede().
            supersedes_edge: dict[str, Any] = {
                "rel": "supersedes",
                "target": existing.id,
            }
            new_record = MemoryRecord(
                user_id=user_id,
                session_id=session_id,
                record_type=RecordType(ext.get("record_type", "preference")),
                content=new_content,
                summary=new_content[:60].strip(),
                keywords=list(ext.get("keywords", [])),
                salience=float(ext.get("salience", 0.5)),
                protected=bool(ext.get("protected", False)),
                provisional=False,
                t0_ref=t0_ref,
                graph_edges=[supersedes_edge],  # Pitfall 5: fresh list
                embedding_model=self._embedder.__class__.__name__,
                embedding_dim=self._embedder.dim,
                embedding_version=getattr(self._embedder, "version", None),
            )
            # T-02-12: atomicity delegated to SqliteT1.supersede() — wraps all three
            # SQL statements in try/except rollback. Never call the three statements
            # separately from here.
            await self._record_store.supersede(existing.id, new_record, embedding)
            return

        # verdict == "distinct" (or unrecognized) → insert as new confirmed record.
        # "distinct" means the new content is a different entity, not a refinement or
        # contradiction of the near-match, so both records live side-by-side.
        await self._insert_new_confirmed(
            ext, new_content, embedding, user_id, session_id, t0_ref
        )

    async def _insert_new_confirmed(
        self,
        ext: dict[str, Any],
        content: str,
        embedding: list[float],
        user_id: str,
        session_id: str,
        t0_ref: str,
    ) -> None:
        """Insert a new confirmed (non-provisional) record into T1.

        Used for:
          - New records with no near match (entity resolution found nothing)
          - Records with "distinct" verdict (near match is a different entity)
        """
        record = MemoryRecord(
            user_id=user_id,
            session_id=session_id,
            record_type=RecordType(ext.get("record_type", "preference")),
            content=content,
            summary=str(ext.get("summary", content[:60])).strip(),
            keywords=list(ext.get("keywords", [])),
            salience=float(ext.get("salience", 0.5)),
            protected=bool(ext.get("protected", False)),
            provisional=False,
            t0_ref=t0_ref,
            embedding_model=self._embedder.__class__.__name__,
            embedding_dim=self._embedder.dim,
            embedding_version=getattr(self._embedder, "version", None),
        )
        # CR-04: upsert_with_vector atomically writes record + vector in one
        # transaction — a crash between the two operations cannot leave an orphaned
        # T1 record that is invisible to KNN but visible to live_records/decay_pass.
        await self._record_store.upsert_with_vector(record, embedding)
