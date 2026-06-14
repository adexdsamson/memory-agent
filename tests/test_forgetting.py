"""Phase 3 forgetting / eviction tests — FORG-02, FORG-03, FORG-04.

FORG-02  Records below keep threshold and not protected are evicted (valid_until
         set, vector deleted, archived to cold store).
FORG-03  Protected records are *never* evicted — proven as a Hypothesis property
         invariant (not an example test).
FORG-04  Eviction is auditable — append-only JSONL audit written on eviction.

All integration tests (TestEviction class) use deferred imports so pytest
collects them in RED state before engine.evict() is implemented.

The Hypothesis property test is a *sync* function that wraps async helpers with
asyncio.run() — required because @given does not support async def (RESEARCH.md
Pitfall 1, established pattern in test_decay.py).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import given, settings

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def record_set_strategy(draw):  # type: ignore[return]
    """Generate a list of MemoryRecord objects with arbitrary fields.

    Uses characters excluding surrogates to avoid codec errors in content.
    """
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    n = draw(st.integers(min_value=0, max_value=30))
    records = []
    for _ in range(n):
        records.append(
            MemoryRecord(
                user_id="u1",
                session_id="s1",
                record_type=draw(st.sampled_from(list(RecordType))),
                content=draw(
                    st.text(
                        min_size=1,
                        max_size=100,
                        alphabet=st.characters(blacklist_categories=("Cs",)),
                    )
                ),
                protected=draw(st.booleans()),
                salience=draw(
                    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
                ),
            )
        )
    return records


# ---------------------------------------------------------------------------
# FORG-03 Hypothesis property test (sync wrapper — RESEARCH.md Pattern 2)
# ---------------------------------------------------------------------------


@given(record_set_strategy())
@settings(max_examples=100)
def test_protected_records_never_evicted(records) -> None:  # type: ignore[return]
    """FORG-03: For *any* set of records, no protected record is ever evicted.

    This is an invariant test, not an example test.  The eviction pass consumes
    decay_pass, which structurally never yields protected records — so no
    protected record can ever appear in eviction output.

    Sync function with asyncio.run() per established MNEMA pattern (test_decay.py
    line 129).  @given does not support async def (RESEARCH.md Pitfall 1).
    """
    from mnema.core.decay import decay_pass  # noqa: PLC0415

    # KEEP_THRESHOLD will move to mnema.core.engine in Plan 03-01.
    # For Wave 0, define locally so the invariant test works against existing decay_pass.
    KEEP_THRESHOLD: float = 0.3

    class _MockStore:
        def __init__(self, recs):  # type: ignore[return]
            self._recs = recs

        @staticmethod
        async def live_records(user_id: str):  # type: ignore[return]
            pass  # replaced in instance method below

        # Instance method so we can capture self._recs
        async def live_records(self, user_id: str):  # type: ignore[misc]  # noqa: F811
            for r in self._recs:
                yield r

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    async def _collect_eviction_candidates():  # type: ignore[return]
        eviction_candidates = []
        async for record, score in decay_pass(_MockStore(records), "u1", now=now):
            if score < KEEP_THRESHOLD:
                eviction_candidates.append(record)
        return eviction_candidates

    eviction_candidates = asyncio.run(_collect_eviction_candidates())

    protected_evicted = [r for r in eviction_candidates if r.protected]
    assert protected_evicted == [], (
        f"FORG-03 VIOLATION: protected records appeared in eviction candidates: "
        f"{[r.id for r in protected_evicted]}"
    )


# ---------------------------------------------------------------------------
# FORG-02 / FORG-04 integration stubs (engine.evict() — Plan 03-01 GREEN)
# ---------------------------------------------------------------------------


class TestEviction:
    """Integration tests for the eviction pipeline (FORG-02/FORG-04).

    Tests import from mnema.core.engine using deferred imports so pytest
    collects them in RED state.  All tests in this class will FAIL at the
    deferred import / missing method step until Plan 03-01 implements evict().
    """

    async def test_eviction_sets_valid_until(self, engine) -> None:
        """FORG-02: After eviction, the evicted record has valid_until set (not None)."""

        # TODO Plan 03-01: seed a backdated record, call engine.evict(user_id="u1"),
        # retrieve it from T1, and assert record.valid_until is not None.
        # old_date = datetime.now(timezone.utc) - timedelta(days=180)
        # record_id = await engine.remember(...)
        # await engine.evict(user_id="u1")
        # record = await engine._t1.get(record_id)
        # assert record.valid_until is not None
        assert False, "TODO Plan 03-01: implement engine.evict() to set valid_until"  # noqa: B011

    async def test_eviction_archives_to_cold_store(self, engine, tmp_path) -> None:
        """FORG-02: After eviction, the evicted record appears in the T0 cold store."""
        # TODO Plan 03-01: seed record, evict, check LocalFS archived.jsonl
        assert False, "TODO Plan 03-01: verify evicted record written to T0 cold store"  # noqa: B011

    async def test_eviction_audit_jsonl(self, engine, tmp_path) -> None:
        """FORG-04: After eviction, an audit JSONL entry is written with correct fields.

        Expected fields: record_id, user_id, keep_score, evicted_at, reason.
        """
        # TODO Plan 03-01: seed record, evict, check eviction_audit.jsonl
        assert False, "TODO Plan 03-01: verify eviction audit JSONL written"  # noqa: B011

    async def test_eviction_skips_protected(self, engine) -> None:
        """FORG-03 (integration supplement): evict() never touches protected records.

        This is an example-based complement to the Hypothesis invariant test.
        """

        # TODO Plan 03-01: seed protected record, run evict(), assert still live
        assert False, "TODO Plan 03-01: verify protected records survive evict()"  # noqa: B011


# ---------------------------------------------------------------------------
# FORG-02 vector-index eviction stub (standalone)
# ---------------------------------------------------------------------------


async def test_eviction_removes_from_vector_index(engine) -> None:
    """FORG-02: After eviction, the evicted record's id is NOT in vector_search results.

    A ghost record in the vec index would re-surface in recall even after eviction.
    This test seeds one evictable record, calls engine.evict(user_id=...),
    then calls engine.recall(query=..., user_id=...) and asserts the evicted
    record's id is NOT in any returned result.

    GREEN implementation requires Plan 03-01.
    """
    # TODO Plan 03-01: verify evicted record_id absent from vector_search results
    assert False, "TODO Plan 03-01: verify evicted record_id absent from vector_search results"  # noqa: B011
