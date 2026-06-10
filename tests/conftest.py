"""Shared test fixtures for the MNEMA test suite.

All fixtures use only local, hermetic adapters — no network calls, no real LLM.
The `engine` fixture constructs a MemoryEngine from four local adapters:
  - StubEmbedder (deterministic, in-process)
  - SqliteT1 (in-memory sqlite-vec)
  - LocalFS (temp-path T0 object store)
  - InProcessScheduler (in-process APScheduler-backed)

Imports are deferred into fixture bodies so that pytest can collect all test
functions even before the implementation exists (RED/Walking Skeleton phase).
"""

from __future__ import annotations

import pytest


@pytest.fixture
async def stub_embedder():  # type: ignore[return]
    """Returns a deterministic StubEmbedder with dim=128."""
    from mnema.adapters.embedding.stub import StubEmbedder  # noqa: PLC0415

    return StubEmbedder(dim=128)


@pytest.fixture
async def engine(tmp_path, stub_embedder):  # type: ignore[return]
    """Constructs a fully-local MemoryEngine for testing.

    Uses:
      - SqliteT1 with in-memory SQLite (":memory:")
      - LocalFS backed by tmp_path / "t0"
      - InProcessScheduler (started, shutdown on teardown)
      - StubEmbedder with dim=128
    """
    from mnema import MemoryEngine  # noqa: PLC0415
    from mnema.adapters.object_store.local_fs import LocalFS  # noqa: PLC0415
    from mnema.adapters.scheduler.in_process import InProcessScheduler  # noqa: PLC0415
    from mnema.adapters.vector_store.sqlite_t1 import SqliteT1  # noqa: PLC0415

    t1 = await SqliteT1.open(":memory:", dim=stub_embedder.dim)
    t0 = LocalFS(str(tmp_path / "t0"))
    scheduler = InProcessScheduler()
    await scheduler.start()

    eng = MemoryEngine(
        embedder=stub_embedder,
        t1=t1,
        t0=t0,
        scheduler=scheduler,
    )
    yield eng

    await scheduler.shutdown()
