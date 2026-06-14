"""Phase 3 recall re-rank and budget packer tests — RECALL-03, RECALL-04, RECALL-05.

RECALL-03  Results re-ranked by relevance × salience × recency (pure sync, D-12).
RECALL-04  Budget packer fits record summaries under a caller-supplied token budget.
RECALL-05  Two-pass packer reserves protected/active-constraint slots first.
           Adversarial: a large off-topic history cannot displace a critical fact.

All tests use deferred imports and will FAIL until Plan 03-02 implements
re_rank() and pack_records() in mnema.core.recall / mnema.core.packer.

packer tests are plain ``def`` (sync) — re_rank() and pack_records() are D-12
pure-sync functions, no async required.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# RECALL-03: Re-rank by relevance × salience × recency
# ---------------------------------------------------------------------------


class TestReRank:
    """Tests for re_rank() — D3-05, RECALL-03."""

    def test_rerank_order_by_composite_score(self) -> None:
        """RECALL-03: re_rank returns records sorted by relevance*salience*recency.

        Records with higher relevance, higher salience, and fresher creation_at
        must rank above stale/low-salience records.
        """
        from mnema.core.recall import re_rank  # noqa: PLC0415
        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

        now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)
        old = now - timedelta(days=90)

        # Fresh record with high salience — should rank first
        rec_fresh = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.FACT,
            content="fresh important fact",
            summary="fresh important fact",
            salience=0.9,
            created_at=now,
        )
        # Stale record with low salience — should rank last
        rec_stale = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.PREFERENCE,
            content="old minor preference",
            summary="old minor preference",
            salience=0.2,
            created_at=old,
        )

        similarity_scores = {rec_fresh.id: 0.95, rec_stale.id: 0.85}
        # Pass stale first to verify re_rank re-orders
        ranked = re_rank([rec_stale, rec_fresh], similarity_scores, now=now)

        assert len(ranked) == 2, f"re_rank must return same number of records; got {len(ranked)}"
        assert ranked[0].id == rec_fresh.id, (
            f"Fresh/high-salience record should rank first; got {ranked[0].id}"
        )
        assert ranked[-1].id == rec_stale.id, (
            f"Stale/low-salience record should rank last; got {ranked[-1].id}"
        )


# ---------------------------------------------------------------------------
# RECALL-04: Budget packer
# ---------------------------------------------------------------------------


class TestPacker:
    """Tests for pack_records() — D3-06/D3-07, RECALL-04."""

    def test_pack_under_budget(self) -> None:
        """RECALL-04: pack_records returns records whose summaries fit under budget."""
        from mnema.core.packer import ByteLengthCounter, pack_records  # noqa: PLC0415
        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

        records = [
            MemoryRecord(
                user_id="u1",
                session_id="s1",
                record_type=RecordType.FACT,
                content=f"fact {i}",
                summary=f"fact {i}",
                salience=0.8,
            )
            for i in range(10)
        ]

        packed = pack_records(records, budget=50, counter=ByteLengthCounter())
        # All packed summaries must fit under budget
        counter = ByteLengthCounter()
        total = sum(counter.count(r.summary or r.content[:80]) for r in packed)
        assert total <= 50, f"Packed output exceeds budget: {total} > 50"
        assert len(packed) > 0, "Packer returned empty list for non-zero budget"

    def test_pack_respects_budget_limit(self) -> None:
        """RECALL-04: pack_records does not include records that would exceed budget."""
        from mnema.core.packer import ByteLengthCounter, pack_records  # noqa: PLC0415
        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

        # One record whose summary is exactly 1 token over budget
        big_summary = "a" * 40  # 40 bytes / 4 ≈ 10 tokens via ByteLengthCounter
        rec = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.PREFERENCE,
            content=big_summary,
            summary=big_summary,
            salience=0.5,
        )

        # Budget of 5 — should not fit this record (10 tokens estimated)
        packed = pack_records([rec], budget=5, counter=ByteLengthCounter())
        assert rec.id not in {r.id for r in packed}, (
            "Record exceeding budget should not be included in packed output"
        )


# ---------------------------------------------------------------------------
# RECALL-05: Adversarial two-pass packer
# ---------------------------------------------------------------------------


def test_critical_fact_survives_large_off_topic_history() -> None:
    """RECALL-05: A protected/critical fact always appears in packed output
    even when the bulk of the history is large off-topic records.

    Adversarial scenario: 100 non-protected records with high relevance scores
    and large summaries flood the budget.  The two-pass packer must reserve a
    slot for the protected allergy fact in Pass 1 regardless of sort order.
    """
    from mnema.core.packer import ByteLengthCounter, pack_records  # noqa: PLC0415
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    # One critical record: protected allergy fact (short summary)
    allergy = MemoryRecord(
        user_id="u1",
        session_id="s1",
        record_type=RecordType.FACT,
        content="allergy: peanuts",
        summary="allergy: peanuts",
        protected=True,
        salience=1.0,
    )
    # 100 large off-topic records that would push allergy out in a naive packer
    filler = [
        MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.PREFERENCE,
            content=f"filler record {i}",
            summary=f"filler record {i} " * 10,  # large summary
            salience=0.9,  # high salience but NOT protected
        )
        for i in range(100)
    ]
    # ranked: filler first (they would win on raw relevance in naive ranker)
    ranked = filler + [allergy]

    packed = pack_records(ranked, budget=200, counter=ByteLengthCounter())
    packed_ids = {r.id for r in packed}
    assert allergy.id in packed_ids, (
        "RECALL-05 VIOLATION: protected allergy fact was pushed out of budget "
        "by off-topic filler history"
    )
