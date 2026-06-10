"""SDK public surface tests.

Verifies that the importable mnema package exposes the expected public names
at the top-level namespace (IFACE-01).

These are structural contracts — if a name is missing, every downstream consumer
that imports it will break. Failing here is earlier and clearer than failing in a
functional test.
"""

from __future__ import annotations


class TestSDKInterface:
    def test_public_surface_importable(self) -> None:
        """MemoryEngine and ScopedHandle must be importable from the mnema namespace.

        Both are the primary SDK entry points consumed by the nutrition-coach demo
        and any downstream SDK user.
        """
        from mnema import MemoryEngine, ScopedHandle  # noqa: F401, PLC0415

        assert MemoryEngine is not None
        assert ScopedHandle is not None

    async def test_engine_scope_returns_scoped_handle(self, engine) -> None:
        """engine.scope() must return a ScopedHandle bound to user_id and agent_id.

        ScopedHandle is the ergonomic front door for SDK users (D-01); this test
        confirms the factory method exists and returns the right type.
        """
        from mnema import ScopedHandle  # noqa: PLC0415

        handle = engine.scope(user_id="u1")
        assert isinstance(handle, ScopedHandle)
