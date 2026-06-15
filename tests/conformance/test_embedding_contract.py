"""EmbeddingProvider conformance contract tests.

Parametrized over all registered embedder_backend fixture backends.
Local-always backends (stub) run unconditionally.
Cloud-gated backends (voyage, qwen_embed) skip when MNEMA_TEST_* env vars are absent.

Key assertions:
  - dim property is a positive integer
  - embed() returns correct output shape: len(result) == len(texts), len(result[0]) == dim
  - embed() returns L2-normalized vectors (unit vectors, norm ~= 1.0)
"""

from __future__ import annotations

import math


def _make_record(user_id: str, summary: str):  # type: ignore[return]
    """Helper to construct a minimal MemoryRecord for use in contract tests."""
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    return MemoryRecord(
        user_id=user_id,
        session_id="s_embed_contract",
        record_type=RecordType.FACT,
        content=summary,
        summary=summary,
    )


class TestEmbeddingContract:
    """EmbeddingProvider Protocol contract assertions.

    All assertions must hold for every registered embedder_backend.
    """

    async def test_dim_property_is_positive_int(self, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        """EmbeddingProvider.dim must be a positive integer."""
        assert isinstance(embedder_backend.dim, int), (
            f"dim must be int, got {type(embedder_backend.dim).__name__!r}"
        )
        assert embedder_backend.dim > 0, (
            f"dim must be positive, got {embedder_backend.dim}"
        )

    async def test_embed_returns_correct_shape(self, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        """embed() must return a list of dim-length vectors, one per input text."""
        result = await embedder_backend.embed(["hello", "world"])
        assert len(result) == 2, (
            f"embed(['hello','world']) must return 2 vectors, got {len(result)}"
        )
        assert len(result[0]) == embedder_backend.dim, (
            f"each vector must have length == dim ({embedder_backend.dim}), "
            f"got {len(result[0])}"
        )
        assert len(result[1]) == embedder_backend.dim, (
            f"each vector must have length == dim ({embedder_backend.dim}), "
            f"got {len(result[1])}"
        )

    async def test_embed_returns_l2_normalized(self, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        """embed() must return L2-normalized unit vectors (norm ~= 1.0)."""
        result = await embedder_backend.embed(["test"])
        assert len(result) == 1
        vec = result[0]
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 0.01, (
            f"embed() must return L2-normalized vectors (norm ~= 1.0), "
            f"got norm={norm:.6f}"
        )

    async def test_embed_single_text(self, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        """embed() with a single text must return a list of one dim-length vector."""
        result = await embedder_backend.embed(["one item"])
        assert len(result) == 1, (
            f"embed(['one item']) must return 1 vector, got {len(result)}"
        )
        assert len(result[0]) == embedder_backend.dim, (
            f"vector must have length == dim ({embedder_backend.dim}), "
            f"got {len(result[0])}"
        )
