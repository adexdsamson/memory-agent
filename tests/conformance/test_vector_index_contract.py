"""VectorIndex conformance contract tests.

Parametrized over all registered t1_backend fixture backends.
Local-always backends (sqlite) run unconditionally.
Cloud/Postgres backends skip when MNEMA_TEST_PG is absent.

Key assertions:
  - vector_search returns the closest record (semantic nearest-neighbor)
  - vector_search filters live-only records (valid_until IS NULL — CORE-05 partial index)
  - vector_search enforces scope isolation via user_id predicate
"""

from __future__ import annotations

from datetime import datetime, timezone


def _make_record(user_id: str, summary: str):  # type: ignore[return]
    """Helper to construct a minimal MemoryRecord for vector index contract tests."""
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    return MemoryRecord(
        user_id=user_id,
        session_id="s_vi_contract",
        record_type=RecordType.FACT,
        content=summary,
        summary=summary,
    )


class TestVectorIndexContract:
    """VectorIndex Protocol contract assertions.

    All assertions must hold for every registered t1_backend.
    Requires embedder_backend to generate real embeddings for meaningful search.
    """

    async def test_vector_search_returns_closest(self, t1_backend, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        """vector_search() must return the closest record by embedding distance.

        Upsert two records with distinct embeddings. Search with the first record's
        embedding — the top result must be that record's id.
        """
        if embedder_backend.dim != t1_backend.dim:
            import pytest  # noqa: PLC0415
            pytest.skip("dim mismatch between t1 and embedder fixture params")

        user_id = "u_vi_closest"
        record_a = _make_record(user_id, "apple juice drink")
        record_b = _make_record(user_id, "quantum physics relativity")

        embs = await embedder_backend.embed([record_a.content, record_b.content])
        emb_a, emb_b = embs[0], embs[1]

        await t1_backend.upsert_with_vector(record_a, emb_a)
        await t1_backend.upsert_with_vector(record_b, emb_b)

        # Search with record_a's exact embedding — record_a should be top result
        results = await t1_backend.vector_search(emb_a, k=2, user_id=user_id)
        assert len(results) >= 1, (
            f"vector_search() must return at least 1 result; got {results!r}"
        )
        top_id, _ = results[0]
        assert top_id == record_a.id, (
            f"vector_search with record_a's embedding must return record_a as top result; "
            f"got {top_id!r}"
        )

    async def test_vector_search_filters_live_only(self, t1_backend, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        """vector_search() must not return records with valid_until set (CORE-05).

        Upsert two records; retire one by setting valid_until. The search must return
        only the live record.
        """
        if embedder_backend.dim != t1_backend.dim:
            import pytest  # noqa: PLC0415
            pytest.skip("dim mismatch between t1 and embedder fixture params")

        user_id = "u_vi_live"
        live_record = _make_record(user_id, "live record that should be found")
        retired_record = _make_record(user_id, "retired record that should be invisible")

        embs = await embedder_backend.embed([live_record.content, retired_record.content])
        emb_live, emb_retired = embs[0], embs[1]

        await t1_backend.upsert_with_vector(live_record, emb_live)
        await t1_backend.upsert_with_vector(retired_record, emb_retired)

        # Retire the second record
        now = datetime.now(timezone.utc)
        await t1_backend.update(retired_record.id, valid_until=now)

        # Search — retired record must not appear
        results = await t1_backend.vector_search(emb_retired, k=5, user_id=user_id)
        result_ids = [rid for rid, _ in results]
        assert retired_record.id not in result_ids, (
            f"CORE-05 VIOLATION: retired record {retired_record.id!r} "
            "appeared in vector_search() — live-only partial index not enforced"
        )

    async def test_vector_search_scope_isolation(self, t1_backend, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        """vector_search() must enforce user_id predicate — cross-user results are forbidden.

        Upsert records for user_a and user_b with the same embedding. Search with user_b's
        user_id — only user_b's record must be returned.
        """
        if embedder_backend.dim != t1_backend.dim:
            import pytest  # noqa: PLC0415
            pytest.skip("dim mismatch between t1 and embedder fixture params")

        user_a_record = _make_record("u_vi_scope_a", "shared content text for scope test")
        user_b_record = _make_record("u_vi_scope_b", "shared content text for scope test")

        # Use the same embedding text so vectors are identical
        shared_text = "shared content text for scope test"
        embs = await embedder_backend.embed([shared_text])
        shared_emb = embs[0]

        await t1_backend.upsert_with_vector(user_a_record, shared_emb)
        await t1_backend.upsert_with_vector(user_b_record, shared_emb)

        # Search scoped to user_b — user_a's record must not appear
        results = await t1_backend.vector_search(shared_emb, k=5, user_id="u_vi_scope_b")
        result_ids = [rid for rid, _ in results]

        assert user_a_record.id not in result_ids, (
            f"SCOPE ISOLATION VIOLATION: user_a's record {user_a_record.id!r} "
            "appeared in vector_search(user_id='u_vi_scope_b') — user_id predicate not enforced"
        )
        assert user_b_record.id in result_ids, (
            f"user_b's record {user_b_record.id!r} must appear in "
            "vector_search(user_id='u_vi_scope_b')"
        )
