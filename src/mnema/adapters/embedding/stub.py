"""StubEmbedder — deterministic, hash-based embedding provider for hermetic CI tests.

Produces consistent, distinguishable L2-normalized unit vectors using SHA-256
without any API calls. Satisfies the EmbeddingProvider Protocol structurally.

No numpy dependency — uses only stdlib hashlib and math.
"""

from __future__ import annotations

import hashlib
import math


class StubEmbedder:
    """Deterministic embedding provider for testing.

    Uses SHA-256 to derive a fixed-length vector from text. Identical inputs
    always produce identical vectors. Distinct inputs produce distinct vectors
    at dim=128 for any realistic test inputs.

    Satisfies EmbeddingProvider Protocol via structural subtyping:
      - dim: int property
      - async embed(texts: list[str]) -> list[list[float]]
      - Contract: all returned vectors are L2-normalized (unit vectors)
    """

    version: str = "stub-v1"

    def __init__(self, dim: int = 128) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalized unit vector per text, deterministically.

        Algorithm:
          1. SHA-256 digest of UTF-8 encoded text (32 bytes)
          2. Build dim-length raw vector: raw[i] = digest[i % 32] / 255.0
          3. L2-normalize: divide each element by sqrt(sum of squares)
        """
        results: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw = [digest[i % 32] / 255.0 for i in range(self._dim)]
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            normalized = [x / norm for x in raw]
            results.append(normalized)
        return results
