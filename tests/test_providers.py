"""Provider contract tests.

Verifies the startup-time dimension-mismatch assertion (PROV-06):
constructing MemoryEngine with a mismatched embedding_dim between the
EmbeddingProvider and the SqliteT1 store must raise ValueError before
any data is written.

This test exercises the independent LLM/embedding axes design: the vector column
dimension is fixed at table-create time, so a dim mismatch is a configuration
error that must be caught eagerly, not silently corrupt stored embeddings.
"""

from __future__ import annotations

import pytest


class TestProviders:
    async def test_dim_mismatch_raises_at_startup(self, tmp_path) -> None:
        """MemoryEngine must raise ValueError when embedder.dim != t1 vector column dim.

        Mismatch: StubEmbedder(dim=128) vs SqliteT1.open(":memory:", dim=64).
        This mirrors the PROV-06 requirement: startup dim assertion, not runtime corruption.
        """
        from mnema import MemoryEngine  # noqa: PLC0415
        from mnema.adapters.embedding.stub import StubEmbedder  # noqa: PLC0415
        from mnema.adapters.object_store.local_fs import LocalFS  # noqa: PLC0415
        from mnema.adapters.scheduler.in_process import InProcessScheduler  # noqa: PLC0415
        from mnema.adapters.vector_store.sqlite_t1 import SqliteT1  # noqa: PLC0415

        embedder_128 = StubEmbedder(dim=128)
        t1_64 = await SqliteT1.open(":memory:", dim=64)
        t0 = LocalFS(str(tmp_path / "t0"))
        scheduler = InProcessScheduler()

        with pytest.raises(ValueError, match="[Ee]mbedding.*dim|dim.*mismatch|dim.*64.*128|dim.*128.*64"):
            MemoryEngine(
                embedder=embedder_128,
                t1=t1_64,
                t0=t0,
                scheduler=scheduler,
            )
