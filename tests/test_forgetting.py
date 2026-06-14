"""Phase 3 forgetting / eviction tests — FORG-02, FORG-03, FORG-04.

FORG-02  Records below keep threshold and not protected are evicted (valid_until
         set, vector deleted, archived to cold store).
FORG-03  Protected records are *never* evicted — proven as a Hypothesis property
         invariant (not an example test).
FORG-04  Eviction is auditable — append-only JSONL audit written on eviction.

The Hypothesis property test is a *sync* function that wraps async helpers with
asyncio.run() — required because @given does not support async def (RESEARCH.md
Pitfall 1, established pattern in test_decay.py).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

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
    from mnema.core.engine import KEEP_THRESHOLD  # noqa: PLC0415

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
# Helpers for seeding an evictable (old + low-salience) record
# ---------------------------------------------------------------------------


async def _seed_evictable_record(engine, *, user_id: str = "u1") -> str:
    """Remember a record, then backdating its timestamps to make keep_score < KEEP_THRESHOLD.

    Returns the record_id of the seeded evictable record.
    """
    # Remember a new record
    await engine.remember(
        "temporary preference that should be forgotten",
        user_id=user_id,
        session_id="s1",
        type_hint="preference",
        durable=True,
    )
    # Get the latest record so we can backdating it
    record = await engine._t1.get_latest(user_id)
    assert record is not None, "Expected a seeded record"

    # Backdate to 180 days ago with zero access count and low salience
    # so keep_score is well below KEEP_THRESHOLD (0.3)
    old_date = datetime.now(timezone.utc) - timedelta(days=180)
    await engine._t1.update(
        record.id,
        created_at=old_date,
        last_accessed=old_date,
        salience=0.1,
        access_count=0,
        provisional=False,  # confirm so it shows as live
    )
    return record.id


# ---------------------------------------------------------------------------
# FORG-02 / FORG-04 integration tests
# ---------------------------------------------------------------------------


class TestEviction:
    """Integration tests for the eviction pipeline (FORG-02/FORG-04)."""

    async def test_eviction_sets_valid_until(self, engine) -> None:
        """FORG-02: After eviction, the evicted record has valid_until set (not None)."""
        record_id = await _seed_evictable_record(engine)

        count = await engine.evict(user_id="u1")

        assert count >= 1, f"Expected at least 1 eviction, got {count}"
        record = await engine._t1.get(record_id)
        assert record is not None, "Record should still exist in T1 (valid_until set, not deleted)"
        assert record.valid_until is not None, (
            "FORG-02: evicted record must have valid_until set"
        )

    async def test_eviction_archives_to_cold_store(self, engine, tmp_path) -> None:
        """FORG-02: After eviction, the evicted record appears in the T0 cold store."""
        record_id = await _seed_evictable_record(engine)

        await engine.evict(user_id="u1")

        # Check that archived.jsonl was written
        archived_path = tmp_path / "t0" / "archived.jsonl"
        assert archived_path.exists(), "archived.jsonl should exist after eviction"

        lines = archived_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1, "Expected at least one archived record"

        # Verify the evicted record appears in the archive
        archived_ids = [json.loads(line).get("id") for line in lines]
        assert record_id in archived_ids, (
            f"FORG-02: evicted record {record_id!r} not found in archived.jsonl"
        )

    async def test_eviction_audit_jsonl(self, engine, tmp_path) -> None:
        """FORG-04: After eviction, an audit JSONL entry is written with correct fields.

        Expected fields: record_id, user_id, keep_score, evicted_at, reason.
        """
        record_id = await _seed_evictable_record(engine)

        await engine.evict(user_id="u1")

        audit_path = tmp_path / "t0" / "eviction_audit.jsonl"
        assert audit_path.exists(), "eviction_audit.jsonl should exist after eviction"

        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1, "Expected at least one audit entry"

        # Find the entry for our evicted record
        entries = [json.loads(line) for line in lines]
        matching = [e for e in entries if e.get("record_id") == record_id]
        assert len(matching) >= 1, (
            f"FORG-04: no audit entry found for record_id={record_id!r}"
        )

        entry = matching[0]
        # Verify required fields (D3-04)
        assert "record_id" in entry, "audit entry missing record_id"
        assert "user_id" in entry, "audit entry missing user_id"
        assert "keep_score" in entry, "audit entry missing keep_score"
        assert "evicted_at" in entry, "audit entry missing evicted_at"
        assert "reason" in entry, "audit entry missing reason"
        assert entry["user_id"] == "u1"
        assert entry["keep_score"] is not None
        assert float(entry["keep_score"]) < 0.3  # was below KEEP_THRESHOLD

    async def test_eviction_skips_protected(self, engine) -> None:
        """FORG-03 (integration supplement): evict() never touches protected records.

        This is an example-based complement to the Hypothesis invariant test.
        """
        # Remember a durable fact — content-driven protection rule fires on "allergy"
        await engine.remember(
            "I am allergic to shellfish",
            user_id="u1",
            session_id="s1",
            type_hint="fact",
            durable=True,
        )
        record = await engine._t1.get_latest("u1")
        assert record is not None

        # Force-set protected=True and backdate to make it score below threshold
        old_date = datetime.now(timezone.utc) - timedelta(days=180)
        await engine._t1.update(
            record.id,
            protected=True,
            created_at=old_date,
            last_accessed=old_date,
            salience=0.1,
            access_count=0,
        )

        # Evict — the protected record must survive
        count = await engine.evict(user_id="u1")

        # Protected record must still be live
        after = await engine._t1.get(record.id)
        assert after is not None
        assert after.valid_until is None, (
            "FORG-03: protected record must not be evicted"
        )
        assert count == 0, (
            f"FORG-03: evict() returned count={count} but only a protected record was live"
        )


# ---------------------------------------------------------------------------
# FORG-02 vector-index eviction test (standalone)
# ---------------------------------------------------------------------------


async def test_eviction_removes_from_vector_index(engine) -> None:
    """FORG-02: After eviction, the evicted record's id is NOT in vector_search results.

    A ghost record in the vec index would re-surface in recall even after eviction.
    This test seeds one evictable record, confirms it exists in T1 before eviction
    (via get(), which does NOT update access_count), calls engine.evict(user_id=...),
    then calls engine.recall(query=..., user_id=...) and asserts the evicted
    record's id is NOT in any returned result.

    Note: recall() increments access_count and updates last_accessed, which would
    defeat the backdating that makes the record evictable.  We therefore use
    engine._t1.get() for the precondition check — it does not touch access signals.
    """
    record_id = await _seed_evictable_record(engine)

    # Confirm the record EXISTS before eviction (via get(), not recall())
    before_record = await engine._t1.get(record_id)
    assert before_record is not None, (
        "Precondition failed: evictable record should exist in T1 before eviction"
    )
    assert before_record.valid_until is None, (
        "Precondition failed: evictable record should be live before eviction"
    )

    # Evict
    count = await engine.evict(user_id="u1")
    assert count >= 1, f"Expected at least 1 eviction, got {count}"

    # The evicted record must NOT appear in subsequent recall (ghost-record check)
    after = await engine.recall("temporary preference", user_id="u1")
    after_ids = [r.id for r in after]
    assert record_id not in after_ids, (
        f"FORG-02: evicted record {record_id!r} is still appearing in vector_search "
        f"results — ghost-record in vec index"
    )
