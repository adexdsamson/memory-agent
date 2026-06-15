"""build_engine() factory standalone RED stubs — STORE-04/05.

These tests are RED until plan 04-07 ships src/mnema/config.py with
build_engine() and LocalConfig.

Purpose: Prove the config factory wire-up pattern:
  LocalConfig() -> build_engine() -> MemoryEngine -> scope().remember() + recall()
"""

from __future__ import annotations


class TestBuildEngine:
    """Standalone RED stubs for the build_engine() factory (STORE-04/05).

    All tests FAIL until src/mnema/config.py ships in plan 04-07.
    """

    def test_build_engine_imports(self) -> None:
        """build_engine and LocalConfig must be importable from mnema.config.

        RED until plan 04-07. Fails with ImportError until the module exists.
        """
        from mnema.config import LocalConfig, build_engine  # noqa: PLC0415

        assert build_engine is not None
        assert LocalConfig is not None

    async def test_local_config_builds_engine(self) -> None:
        """build_engine(LocalConfig()) must return a MemoryEngine.

        RED until plan 04-07 implements build_engine() factory.
        """
        from mnema import MemoryEngine  # noqa: PLC0415
        from mnema.config import LocalConfig, build_engine  # noqa: PLC0415

        engine = build_engine(LocalConfig())
        assert isinstance(engine, MemoryEngine), (
            f"build_engine(LocalConfig()) must return MemoryEngine; "
            f"got {type(engine).__name__!r}"
        )

    async def test_local_config_end_to_end(self) -> None:
        """build_engine(LocalConfig()) must support remember() + recall() end-to-end.

        RED until plan 04-07 implements both the factory and wires up all adapters.
        """
        from mnema.config import LocalConfig, build_engine  # noqa: PLC0415

        engine = build_engine(LocalConfig())
        await engine.remember("test memory content", user_id="u1", session_id="s1")
        results = await engine.recall("test memory content", user_id="u1")
        assert len(results) > 0, (
            "recall() after remember() must return at least one result; "
            f"got {results!r}"
        )
