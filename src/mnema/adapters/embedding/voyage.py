"""VoyageEmbedder — Voyage AI embedding adapter.

Satisfies EmbeddingProvider Protocol by structural typing. Claude-compatible
embedder (PROV-05, D4-06) — direct voyageai SDK, no LiteLLM (D4-05).
L2-normalized at adapter (D4-07). Sync Client wrapped in asyncio.to_thread
(D-13); switch to AsyncClient if event-loop contention occurs.

Security: API key is stored only inside the voyageai.Client instance — never
on self directly. __repr__ excludes the key (ASVS V2, T-04-03-01).
"""

from __future__ import annotations

import asyncio
import math


def _l2_normalize(v: list[float]) -> list[float]:
    """Return a L2-normalized copy of vector v.

    If the vector has zero norm (all zeros), returns v unchanged to avoid
    division by zero (norm clamped to 1.0).
    """
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class VoyageEmbedder:
    """Voyage AI embedding adapter (voyage-3.5).

    Satisfies EmbeddingProvider Protocol via structural subtyping:
      - dim: int property (returns configured output_dimension)
      - async embed(texts: list[str]) -> list[list[float]]

    Normalization contract: embed() always returns L2-normalized unit vectors.
    Independent-axis design: pairs with any LLMProvider (e.g. AnthropicLLM)
    in a single MemoryEngine config without coupling (D4-06, PROV-05).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "voyage-3.5",
        output_dimension: int = 1024,
    ) -> None:
        import voyageai  # noqa: PLC0415

        self._client = voyageai.Client(api_key=api_key)  # type: ignore[attr-defined]
        self._model = model
        self._output_dimension = output_dimension
        self._dim = output_dimension

    @property
    def dim(self) -> int:
        """Vector dimension — fixed at table-create time. Must not change post-open."""
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts; returns L2-normalized float vectors of length dim."""

        def _call() -> list[list[float]]:
            result = self._client.embed(
                texts,
                model=self._model,
                output_dimension=self._output_dimension,
            )
            return result.embeddings  # type: ignore[no-any-return]

        raw = await asyncio.to_thread(_call)
        return [_l2_normalize(v) for v in raw]

    def __repr__(self) -> str:
        return f"VoyageEmbedder(model={self._model!r}, dim={self._dim})"
