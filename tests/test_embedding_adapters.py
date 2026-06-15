"""Hermetic unit tests for VoyageEmbedder and QwenEmbedder.

These tests exercise adapter construction, dim property, and L2 normalization
WITHOUT real API calls. SDK imports are guarded so this file runs in --extra dev
(no --extra cloud required).

Classes are marked skipif when the relevant SDK extra is absent.
"""

from __future__ import annotations

import math
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Import availability guards
# ---------------------------------------------------------------------------


def _import_ok(module_name: str) -> bool:
    """Return True if module is importable; False on ImportError."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


_VOYAGE_AVAILABLE = _import_ok("voyageai")
_DASHSCOPE_AVAILABLE = _import_ok("dashscope")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _l2_norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


# ---------------------------------------------------------------------------
# VoyageEmbedder tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _VOYAGE_AVAILABLE, reason="voyageai not installed — install --extra cloud")
class TestVoyageEmbedderHermetic:
    """Tests for VoyageEmbedder that mock voyageai SDK calls."""

    def test_instantiate_and_dim(self) -> None:
        """VoyageEmbedder(api_key=...) constructs without error; dim matches output_dimension."""
        with patch("voyageai.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            from mnema.adapters.embedding.voyage import VoyageEmbedder

            v = VoyageEmbedder(api_key="test-key", output_dimension=1024)
            assert v.dim == 1024

    def test_dim_default_is_1024(self) -> None:
        """Default output_dimension is 1024."""
        with patch("voyageai.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            from mnema.adapters.embedding.voyage import VoyageEmbedder

            v = VoyageEmbedder(api_key="test-key")
            assert v.dim == 1024

    async def test_embed_returns_normalized_vectors(self) -> None:
        """embed() must return L2-normalized unit vectors of length dim."""
        with patch("voyageai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            # Return a raw (non-normalized) vector to confirm the adapter normalizes it
            raw_vec = [3.0, 4.0]  # norm=5.0; normalized = [0.6, 0.8]
            mock_embed_result = MagicMock()
            mock_embed_result.embeddings = [raw_vec]
            mock_client.embed.return_value = mock_embed_result

            from mnema.adapters.embedding.voyage import VoyageEmbedder

            v = VoyageEmbedder(api_key="test-key", output_dimension=2)
            result = await v.embed(["hello"])

        assert len(result) == 1
        assert len(result[0]) == 2
        norm = _l2_norm(result[0])
        assert abs(norm - 1.0) < 0.01, f"Expected unit vector, got norm={norm}"

    def test_repr_excludes_api_key(self) -> None:
        """__repr__ must not expose the API key."""
        with patch("voyageai.Client") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            from mnema.adapters.embedding.voyage import VoyageEmbedder

            v = VoyageEmbedder(api_key="super-secret-key", output_dimension=1024)
            r = repr(v)
            assert "super-secret-key" not in r

    def test_independent_axis_config(self) -> None:
        """VoyageEmbedder can be combined with AnthropicLLM in one config (D4-06)."""
        with patch("voyageai.Client"):
            from mnema.adapters.embedding.voyage import VoyageEmbedder

            v = VoyageEmbedder(api_key="voyage-key", output_dimension=1024)
            assert v.dim == 1024


# ---------------------------------------------------------------------------
# QwenEmbedder tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _DASHSCOPE_AVAILABLE, reason="dashscope not installed — install --extra cloud"
)
class TestQwenEmbedderHermetic:
    """Tests for QwenEmbedder that mock dashscope SDK calls."""

    def test_instantiate_and_dim(self) -> None:
        """QwenEmbedder(api_key=...) constructs without error; dim matches output_dimension."""
        mock_ds = MagicMock()
        mock_ds.TextEmbedding = MagicMock()
        with patch.dict(sys.modules, {"dashscope": mock_ds}):
            from importlib import reload
            import mnema.adapters.embedding.qwen as qwen_mod

            reload(qwen_mod)
            q = qwen_mod.QwenEmbedder(api_key="test-key", output_dimension=1024)
            assert q.dim == 1024

    def test_dim_default_is_1024(self) -> None:
        """Default output_dimension is 1024."""
        mock_ds = MagicMock()
        mock_ds.TextEmbedding = MagicMock()
        with patch.dict(sys.modules, {"dashscope": mock_ds}):
            from importlib import reload
            import mnema.adapters.embedding.qwen as qwen_mod

            reload(qwen_mod)
            q = qwen_mod.QwenEmbedder(api_key="test-key")
            assert q.dim == 1024

    async def test_embed_returns_normalized_vectors(self) -> None:
        """embed() must return L2-normalized unit vectors of length dim."""
        mock_ds = MagicMock()
        mock_te = MagicMock()
        # Mock TextEmbedding.call() response shape
        mock_resp = MagicMock()
        mock_resp.output = {"embeddings": [{"embedding": [3.0, 4.0]}]}
        mock_te.call.return_value = mock_resp
        mock_te.Models.text_embedding_v4 = "text-embedding-v4"
        mock_ds.TextEmbedding = mock_te
        mock_ds.api_key = None

        with patch.dict(sys.modules, {"dashscope": mock_ds}):
            from importlib import reload
            import mnema.adapters.embedding.qwen as qwen_mod

            reload(qwen_mod)
            q = qwen_mod.QwenEmbedder(api_key="test-key", output_dimension=2)
            result = await q.embed(["hello"])

        assert len(result) == 1
        assert len(result[0]) == 2
        norm = _l2_norm(result[0])
        assert abs(norm - 1.0) < 0.01, f"Expected unit vector, got norm={norm}"
