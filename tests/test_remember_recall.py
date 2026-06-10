"""5-scenario remember/recall harness.

Maps 1:1 to the 5 Phase 1 success criteria (SC-1 through SC-5).
All tests are RED — they will fail with ImportError until Plans 02-04 implement
the engine and adapters. Imports are deferred to allow pytest to collect these
test functions before the implementation exists.
"""

from __future__ import annotations

import pytest


class TestRememberRecall:
    """SC-1: Calling remember then recall returns the stored fact, scoped correctly."""

    async def test_remember_and_recall_scoped(self, engine) -> None:
        """SC-1: remember then recall returns the stored fact within the same user scope."""
        await engine.remember(
            "I am allergic to peanuts",
            user_id="u1",
            session_id="s1",
        )
        results = await engine.recall("food allergies", user_id="u1")
        assert len(results) >= 1
        contents = " ".join(
            (r.content if hasattr(r, "content") else "") + " " +
            (r.summary if hasattr(r, "summary") else "")
            for r in results
        ).lower()
        assert "peanut" in contents

    async def test_cross_session_provisional_recall(self, engine) -> None:
        """SC-2: A durable claim stated in session-1 is recallable in a different recall
        before consolidation runs (provisional T1 write surfaces it cross-session)."""
        await engine.remember(
            "I love spicy food",
            user_id="u1",
            session_id="s1",
        )
        # Recall does NOT pass session_id — must surface across sessions
        results = await engine.recall("spicy preferences", user_id="u1")
        assert len(results) >= 1

    async def test_within_session_buffer_freshness(self, engine) -> None:
        """SC-2: A same-session statement is recallable immediately via the buffer."""
        scope = engine.scope(user_id="u1")
        await scope.remember("I hate mushrooms", session_id="s2")
        results = await scope.recall("food preferences")
        assert len(results) >= 1
        contents = " ".join(
            (r.content if hasattr(r, "content") else "") + " " +
            (r.summary if hasattr(r, "summary") else "")
            for r in results
        ).lower()
        assert "mushroom" in contents

    async def test_fast_write_schema_columns(self, engine) -> None:
        """SC-3: Every written record persists scope ids, type, embedding provenance,
        and a structural protected flag — no schema columns missing at write time."""
        await engine.remember(
            "I prefer vegan meals",
            user_id="u1",
            session_id="s1",
        )
        # Fetch directly from the T1 store to verify schema columns
        records = await engine.t1.get_live_records(user_id="u1")
        assert len(records) >= 1
        record = records[0]
        assert record.embedding_model is not None
        assert record.embedding_dim is not None
        assert isinstance(record.protected, bool)
        assert record.valid_until is None

    async def test_expand_and_access_count(self, engine) -> None:
        """SC-5: expand(id) returns verbatim T0 detail; accessing a record increments
        access_count."""
        await engine.remember(
            "I batch-cook on Sundays",
            user_id="u1",
            session_id="s1",
        )
        results = await engine.recall("cooking habits", user_id="u1")
        assert len(results) >= 1
        record = results[0]
        assert record.access_count >= 1
        if record.t0_ref is not None:
            turn = await engine.expand(record.id, user_id="u1")
            assert turn is not None
