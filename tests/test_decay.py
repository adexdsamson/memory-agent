"""Phase 2 decay / keep_score tests — FORG-01 and FORG-03 (partial).

All tests in this module verify ``mnema.core.decay.keep_score``, a pure
synchronous function that computes a retention score for a MemoryRecord.

  FORG-01  keep_score returns a float in [0, 1] with the correct weighted formula
  FORG-03  (partial) decay_pass must skip protected records before invoking
           keep_score -- the guard lives in the caller, not inside the pure
           scoring function

``keep_score`` is a D-12 sans-I/O function -- tests are plain ``def`` (no async
required) and need no engine fixture.  The deferred import style keeps the test
collectable before the implementation exists.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone


class TestDecay:
    def test_keep_score_values(self) -> None:
        """FORG-01: keep_score returns float in [0,1]; correct formula for known inputs."""
        from mnema.core.decay import keep_score  # noqa: PLC0415
        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

        now = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)

        # Fresh record: age=0 days, access_count=0, salience=0.5
        # Expected: 0.4*exp(-0.05*0) + 0.3*log(1+0) + 0.3*0.5 = 0.4*1 + 0 + 0.15 = 0.55
        record_fresh = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.PREFERENCE,
            content="test fresh",
            created_at=now,
            access_count=0,
            salience=0.5,
        )
        score_fresh = keep_score(record_fresh, now=now)
        assert abs(score_fresh - 0.55) < 1e-6, f"Expected 0.55 for fresh record, got {score_fresh}"
        assert 0.0 <= score_fresh <= 1.0, f"Score out of [0,1]: {score_fresh}"

        # 14-day-old record: age=14 days, access_count=0, salience=0.5
        # Expected: 0.4*exp(-0.05*14) + 0.0 + 0.3*0.5
        old_created = now - timedelta(days=14)
        record_old = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.PREFERENCE,
            content="test old",
            created_at=old_created,
            access_count=0,
            salience=0.5,
        )
        score_old = keep_score(record_old, now=now)
        expected_old = 0.4 * math.exp(-0.05 * 14) + 0.0 + 0.3 * 0.5
        assert abs(score_old - expected_old) < 1e-6, (
            f"Expected {expected_old} for 14-day-old record, got {score_old}"
        )
        assert 0.0 <= score_old <= 1.0, f"Score out of [0,1]: {score_old}"

        # Verify measurable decay: old record scores lower than fresh
        assert score_old < score_fresh, (
            f"Expected old record ({score_old}) to score lower than fresh ({score_fresh})"
        )

        # High access_count record: access_count=10, salience=0.5, age=0
        # reinforce = log(11) ≈ 2.397 → 0.3 * 2.397 ≈ 0.719 → score > 1.0 → clamped to 1.0
        record_busy = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.PREFERENCE,
            content="test busy",
            created_at=now,
            access_count=10,
            salience=0.5,
        )
        score_busy = keep_score(record_busy, now=now)
        assert score_busy == 1.0, f"Expected 1.0 (clamped) for access_count=10, got {score_busy}"

    def test_protected_skipped_before_score_math(self) -> None:
        """FORG-03 (partial): decay_pass must not yield protected records at all.

        This test verifies two things:
        1. keep_score itself does NOT raise when called on a protected record --
           the guard is in the caller (decay_pass), not inside keep_score.
        2. decay_pass does NOT yield any (record, score) pair for a protected record --
           the iterator is empty when only a protected record is present.
        """
        from mnema.core.decay import decay_pass, keep_score  # noqa: PLC0415
        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

        now = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)

        protected_record = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.FACT,
            content="allergy: peanuts",
            protected=True,
            salience=1.0,
            created_at=now,
        )

        # Part 1: keep_score must not raise on a protected record
        score = keep_score(protected_record, now=now)
        assert isinstance(score, float), (
            f"keep_score must return float even for protected record; got {type(score)}"
        )
        assert 0.0 <= score <= 1.0, f"Score out of [0,1]: {score}"

        # Part 2: decay_pass must NOT yield the protected record at all (FORG-03)
        # Use a static method to avoid the implicit `self` argument that would
        # be injected if a bare function were assigned as a class attribute.
        class _MockStore:
            @staticmethod
            async def live_records(user_id: str):  # type: ignore[return]
                yield protected_record

        async def _collect() -> list:  # type: ignore[return]
            results = []
            async for item in decay_pass(_MockStore(), "u1", now=now):
                results.append(item)
            return results

        yielded = asyncio.run(_collect())
        assert yielded == [], (
            "FORG-03 VIOLATION: decay_pass must NOT yield protected records; "
            f"got {yielded}"
        )
