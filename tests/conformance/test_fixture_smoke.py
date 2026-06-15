"""Smoke tests for conformance fixture registration.

Verifies that:
- All six fixture axes are parametrized and discoverable
- Local-always backends yield valid instances
- Cloud/gated backends skip cleanly (not error) when env vars absent
"""

from __future__ import annotations


class TestT1BackendFixture:
    """Verify t1_backend fixture yields a valid RecordStore+VectorIndex."""

    async def test_t1_backend_has_dim(self, t1_backend) -> None:  # type: ignore[no-untyped-def]
        assert hasattr(t1_backend, "dim")
        assert isinstance(t1_backend.dim, int)
        assert t1_backend.dim == 128


class TestEmbedderBackendFixture:
    """Verify embedder_backend fixture yields a valid EmbeddingProvider."""

    async def test_embedder_backend_has_dim(self, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        assert hasattr(embedder_backend, "dim")
        assert isinstance(embedder_backend.dim, int)
        assert embedder_backend.dim > 0

    async def test_embedder_backend_embed_returns_list(self, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        result = await embedder_backend.embed(["hello world"])
        assert isinstance(result, list)
        assert len(result) == 1
        assert len(result[0]) == embedder_backend.dim


class TestLLMBackendFixture:
    """Verify llm_backend fixture yields a valid LLMProvider."""

    async def test_llm_backend_complete_returns_string(self, llm_backend) -> None:  # type: ignore[no-untyped-def]
        result = await llm_backend.complete("EXTRACT_RECORDS: hello")
        assert isinstance(result, str)
        assert len(result) > 0


class TestObjectStoreBackendFixture:
    """Verify object_store_backend fixture yields a valid ObjectStorePort."""

    async def test_object_store_backend_is_not_none(self, object_store_backend) -> None:  # type: ignore[no-untyped-def]
        assert object_store_backend is not None


class TestVaultBackendFixture:
    """Verify vault_backend fixture yields a valid VaultStore."""

    async def test_vault_backend_is_not_none(self, vault_backend) -> None:  # type: ignore[no-untyped-def]
        assert vault_backend is not None


class TestSchedulerBackendFixture:
    """Verify scheduler_backend fixture yields a running Scheduler."""

    async def test_scheduler_backend_is_not_none(self, scheduler_backend) -> None:  # type: ignore[no-untyped-def]
        assert scheduler_backend is not None

    async def test_scheduler_backend_has_trigger_now(self, scheduler_backend) -> None:  # type: ignore[no-untyped-def]
        assert hasattr(scheduler_backend, "trigger_now")
        assert callable(scheduler_backend.trigger_now)
