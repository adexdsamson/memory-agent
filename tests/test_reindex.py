"""reindex_all() / migrate_embedder() standalone RED stubs — PROV-07.

These tests are RED until plan 04-07 ships src/mnema/migrate.py with
reindex_all() and migrate_embedder().

Purpose:
  test_reindex_all_re_embeds_live_records: re-embedding all live records for a user
  test_dim_switch_requires_explicit_reindex: D4-14 behavioral proof — switching embedder
    dims raises ValueError at engine construction until migrate_embedder() is called first.
"""

from __future__ import annotations


def _make_record(user_id: str, summary: str):  # type: ignore[return]
    """Helper to construct a minimal MemoryRecord for reindex tests."""
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    return MemoryRecord(
        user_id=user_id,
        session_id="s_reindex",
        record_type=RecordType.FACT,
        content=summary,
        summary=summary,
    )


class TestReindex:
    """Standalone RED stubs for the reindex_all() migration path (PROV-07).

    All tests FAIL until src/mnema/migrate.py ships in plan 04-07.
    """

    def test_reindex_all_imports(self) -> None:
        """reindex_all and migrate_embedder must be importable from mnema.migrate.

        RED until plan 04-07. Fails with ImportError until the module exists.
        """
        from mnema.migrate import migrate_embedder, reindex_all  # noqa: PLC0415

        assert reindex_all is not None
        assert migrate_embedder is not None

    async def test_reindex_all_re_embeds_live_records(self) -> None:
        """reindex_all() must re-embed all live records for a given user.

        Seeds 3 live records with old embeddings (dim=128 StubEmbedder),
        then calls reindex_all() with a new StubEmbedder(dim=128).
        Asserts that reindex_all() returns the count of re-embedded records (3).

        RED until plan 04-07 implements reindex_all().
        """
        from mnema.migrate import reindex_all  # noqa: PLC0415

        from mnema.adapters.embedding.stub import StubEmbedder  # noqa: PLC0415
        from mnema.adapters.vector_store.sqlite_t1 import SqliteT1  # noqa: PLC0415

        embedder = StubEmbedder(dim=128)
        t1 = await SqliteT1.open(":memory:", dim=128)

        # Seed 3 live records with embeddings from the old embedder
        user_id = "u_reindex"
        records = [
            _make_record(user_id, "fact one for reindex test"),
            _make_record(user_id, "fact two for reindex test"),
            _make_record(user_id, "fact three for reindex test"),
        ]
        for rec in records:
            emb = (await embedder.embed([rec.content]))[0]
            await t1.upsert_with_vector(rec, emb)

        # Re-index with the same embedder (or a new one — same dim for simplicity)
        new_embedder = StubEmbedder(dim=128)
        count = await reindex_all(t1, new_embedder, user_id)
        assert count == 3, (
            f"reindex_all() must re-embed all 3 live records; got count={count}"
        )

    async def test_dim_switch_requires_explicit_reindex(self) -> None:
        """D4-14 behavioral proof: switching embedder dims must raise ValueError.

        Sequence:
          1. Create SqliteT1 at dim=64
          2. Assert MemoryEngine(embedder=StubEmbedder(dim=128), t1=...) raises ValueError
          3. Call migrate_embedder(t1, StubEmbedder(dim=128), user_id=...) to migrate
          4. Assert MemoryEngine now constructs without error
          5. Assert a protected record (seeded before migration) still exists and is protected

        RED until plan 04-07 implements migrate_embedder() and dim-switch logic.
        """
        import pytest  # noqa: PLC0415
        from mnema.migrate import migrate_embedder  # noqa: PLC0415

        from mnema import MemoryEngine  # noqa: PLC0415
        from mnema.adapters.embedding.stub import StubEmbedder  # noqa: PLC0415
        from mnema.adapters.object_store.local_fs import LocalFS  # noqa: PLC0415
        from mnema.adapters.scheduler.in_process import InProcessScheduler  # noqa: PLC0415
        from mnema.adapters.vector_store.sqlite_t1 import SqliteT1  # noqa: PLC0415

        # Step 1: Create T1 at dim=64
        t1_64 = await SqliteT1.open(":memory:", dim=64)
        embedder_64 = StubEmbedder(dim=64)

        user_id = "u_dimswitch"

        # Seed a protected record with dim=64 embeddings
        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

        protected_rec = MemoryRecord(
            user_id=user_id,
            session_id="s_reindex",
            record_type=RecordType.FACT,
            content="critical allergy: shellfish",
            summary="critical allergy: shellfish",
            protected=True,
            salience=1.0,
        )
        emb_64 = (await embedder_64.embed([protected_rec.content]))[0]
        await t1_64.upsert_with_vector(protected_rec, emb_64)

        # Step 2: Assert that constructing MemoryEngine with mismatched dim raises ValueError
        embedder_128 = StubEmbedder(dim=128)
        with pytest.raises(ValueError, match=r"[Ee]mbedding.*dim|dim.*mismatch|dim"):
            import tempfile  # noqa: PLC0415

            with tempfile.TemporaryDirectory() as tmp:
                t0 = LocalFS(tmp)
                scheduler = InProcessScheduler()
                MemoryEngine(
                    embedder=embedder_128,
                    t1=t1_64,
                    t0=t0,
                    scheduler=scheduler,
                )

        # Step 3: Call migrate_embedder() to upgrade dim=64 -> dim=128
        await migrate_embedder(t1_64, embedder_128, user_id=user_id)

        # Step 4: Assert MemoryEngine now constructs without error
        import tempfile  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            t0 = LocalFS(tmp)
            scheduler = InProcessScheduler()
            await scheduler.start()
            engine = MemoryEngine(
                embedder=embedder_128,
                t1=t1_64,
                t0=t0,
                scheduler=scheduler,
            )
            assert engine is not None, "MemoryEngine must construct after migrate_embedder()"

            # Step 5: Assert the protected record survived migration
            survived = await t1_64.get(protected_rec.id)
            assert survived is not None, (
                "Protected record must survive migrate_embedder() — it was hard-deleted"
            )
            assert survived.protected is True, (
                "Protected record must still be protected after migrate_embedder()"
            )

            await scheduler.shutdown()

    async def test_migrate_embedder_all_users_no_data_loss(self) -> None:
        """CR-01: migrate_embedder() with no user_id must re-embed ALL users' live records.

        Seeds two users (u_alice, u_bob) each with 2 live records at dim=64.
        Calls migrate_embedder(t1, new_embedder) with NO user_id (default=None).
        Asserts count == 4 (both users' records re-indexed) and that vectors are
        searchable for both users after migration.
        """
        from mnema.migrate import migrate_embedder  # noqa: PLC0415

        from mnema.adapters.embedding.stub import StubEmbedder  # noqa: PLC0415
        from mnema.adapters.vector_store.sqlite_t1 import SqliteT1  # noqa: PLC0415

        t1 = await SqliteT1.open(":memory:", dim=64)
        embedder_64 = StubEmbedder(dim=64)

        # Seed 2 records for each of 2 users
        alice_records = [
            _make_record("u_alice", "alice fact one"),
            _make_record("u_alice", "alice fact two"),
        ]
        bob_records = [
            _make_record("u_bob", "bob fact one"),
            _make_record("u_bob", "bob fact two"),
        ]
        for rec in alice_records + bob_records:
            emb = (await embedder_64.embed([rec.content]))[0]
            await t1.upsert_with_vector(rec, emb)

        # Migrate to dim=128 without specifying user_id — must cover BOTH users
        embedder_128 = StubEmbedder(dim=128)
        count = await migrate_embedder(t1, embedder_128)  # user_id=None (default)

        assert count == 4, (
            f"migrate_embedder() with user_id=None must re-embed all 4 records "
            f"(2 users × 2 records each); got count={count}"
        )

        # Verify both users' records are searchable after migration
        query = (await embedder_128.embed(["test query"]))[0]
        alice_results = await t1.vector_search(query, k=4, user_id="u_alice")
        bob_results = await t1.vector_search(query, k=4, user_id="u_bob")
        assert len(alice_results) == 2, (
            f"u_alice must have 2 searchable records after migration; got {len(alice_results)}"
        )
        assert len(bob_results) == 2, (
            f"u_bob must have 2 searchable records after migration; got {len(bob_results)}"
        )
