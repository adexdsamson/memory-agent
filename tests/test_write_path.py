"""Fast write path tests.

Verifies:
  - A durable-looking claim (first-person stative fact) produces a provisional T1 record.
  - A non-durable claim (interrogative / transient) does NOT produce a T1 record.

These tests verify SC-3: the fast write path appends T0 + buffer + provisional T1
without blocking on a reasoning LLM, using only the heuristic trigger (D-04).
"""

from __future__ import annotations


class TestWritePath:
    async def test_durable_claim_produces_t1_record(self, engine) -> None:
        """A first-person stative fact triggers the provisional T1 write.

        The heuristic (D-04) identifies "I am diabetic" as a durable claim and
        writes a provisional record into T1 immediately on the fast write path.
        """
        await engine.remember(
            "I am diabetic",
            user_id="u1",
            session_id="s1",
        )
        records = await engine.t1.get_live_records(user_id="u1")
        assert len(records) >= 1
        # The record must be marked provisional (not yet confirmed by consolidation)
        assert any(r.provisional for r in records)

    async def test_non_durable_claim_skips_t1(self, engine) -> None:
        """An interrogative / transient statement does NOT produce a T1 record.

        "What is the weather today?" is a question — the heuristic suppresses
        the provisional write so T1 stays clean of non-durable content.
        """
        await engine.remember(
            "What is the weather today?",
            user_id="u_ephemeral",
            session_id="s1",
        )
        records = await engine.t1.get_live_records(user_id="u_ephemeral")
        assert len(records) == 0
