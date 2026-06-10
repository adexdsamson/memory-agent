"""Embedding provider port — PROV-02.

Independent axis from LLMProvider (Claude ships no embedder; this is the explicit
seam that forces LLM and embedding to be configured separately).

The `dim` property is a first-class Protocol member. SqliteT1.open() reads
`embedder.dim` and creates the vec_t1 table with that column width. If a
MemoryEngine is later constructed with a mismatched dim, the startup assertion
raises ValueError before any data is written (PROV-06).

Normalization contract: `embed()` ALWAYS returns L2-normalized (unit) vectors.
Adapters must normalize before returning; callers may assume normalized output.

No @runtime_checkable — static checking only (D-10).
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Contract for a text embedding backend."""

    @property
    def dim(self) -> int:
        """Vector dimension — fixed at table-create time. Must not change post-open."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts; returns L2-normalized float vectors of length `dim`."""
        ...
