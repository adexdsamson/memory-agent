"""QwenEmbedder — DashScope Qwen embedding adapter (text-embedding-v4).

Satisfies EmbeddingProvider Protocol by structural typing. Direct dashscope
SDK — no LiteLLM (D4-05). L2-normalized at adapter (D4-07). Sync SDK wrapped
in asyncio.to_thread (D-13).

Warning: dashscope uses module-level global api_key state. QwenLLM and
QwenEmbedder MUST share the same api_key in a single-engine config
(T-04-03-02). The global is set once in __init__; with one engine per process
this is safe. Document this constraint if multi-tenant use is ever required.
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


class QwenEmbedder:
    """DashScope Qwen embedding adapter (text-embedding-v4).

    Satisfies EmbeddingProvider Protocol via structural subtyping:
      - dim: int property (returns configured output_dimension)
      - async embed(texts: list[str]) -> list[list[float]]

    Normalization contract: embed() always returns L2-normalized unit vectors.
    text-embedding-v4 supports Matryoshka dimensions 64–2048; 1024 is default.
    """

    def __init__(self, api_key: str, output_dimension: int = 1024) -> None:
        import dashscope  # type: ignore[import-untyped]  # noqa: PLC0415
        from dashscope import TextEmbedding  # type: ignore[import-untyped]  # noqa: PLC0415

        dashscope.api_key = api_key
        self._dim = output_dimension
        self._TextEmbedding = TextEmbedding  # hold reference for embed()
        # Capture api_key in a closure so per-call passthrough is possible without
        # storing it as a plain str attribute on self (WR-03 parity with QwenLLM).
        _key = api_key
        self._api_key_getter = lambda: _key  # noqa: E731

    @property
    def dim(self) -> int:
        """Vector dimension — fixed at table-create time. Must not change post-open."""
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts; returns L2-normalized float vectors of length dim."""
        TextEmbedding = self._TextEmbedding
        dim = self._dim
        api_key = self._api_key_getter()

        def _call() -> list[list[float]]:
            # Assumption A7: model constant may be enum attribute or string literal
            try:
                model: str = TextEmbedding.Models.text_embedding_v4  # type: ignore[union-attr]
            except AttributeError:
                model = "text-embedding-v4"

            resp = TextEmbedding.call(  # type: ignore[union-attr]
                model=model, input=texts, dimension=dim, api_key=api_key
            )
            output = getattr(resp, "output", None)
            if output is None:
                raise ValueError(
                    f"QwenEmbedder: null response from DashScope (dim={dim})"
                )
            return [item["embedding"] for item in output["embeddings"]]  # type: ignore[index]

        raw = await asyncio.to_thread(_call)
        return [_l2_normalize(v) for v in raw]

    def __repr__(self) -> str:
        return f"QwenEmbedder(model='text-embedding-v4', dim={self._dim})"
