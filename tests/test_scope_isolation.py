"""Scope isolation assertions.

Verifies that user_id forms a hard isolation boundary — a record written under
user u1 must never surface when recalled as user u2.

Also verifies the T-1-01 threat mitigation: user_id is a non-defaulted kwarg;
omitting it raises TypeError before any DB access.
"""

from __future__ import annotations

import pytest


class TestScopeIsolation:
    async def test_recall_does_not_leak_across_users(self, engine) -> None:
        """A record stored under user_id='u1' must not appear when recalled as user_id='u2'."""
        await engine.remember(
            "My secret dietary restriction is no gluten",
            user_id="u1",
            session_id="s1",
        )
        results = await engine.recall("dietary restrictions", user_id="u2")
        assert len(results) == 0

    async def test_user_id_required_kwarg(self, engine) -> None:
        """Calling engine.recall() without user_id must raise TypeError.

        user_id is a non-defaulted keyword-only argument at the Protocol level;
        omitting it is a programming error, not a runtime failure (T-1-01 mitigation).
        """
        with pytest.raises(TypeError):
            await engine.recall("query")  # type: ignore[call-arg]
