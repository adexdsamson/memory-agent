"""RecordStore conformance contract tests.

Parametrized over all registered t1_backend fixture backends.
Local-always backends (sqlite) run unconditionally.
Cloud/Postgres backends (postgres) skip when MNEMA_TEST_PG is absent.

Safety invariant assertions (MUST hold on every backend):
  - D-02 Scope isolation: user A cannot read user B's records
  - FORG-03 Protected record survival: protected records are never yielded by decay_pass
  - FORG-04 Non-destructive eviction: evicted records survive with valid_until set

Behavioral assertions:
  - upsert_with_vector + get_record roundtrip
  - live_records excludes superseded records
  - update_fields changes the targeted attribute
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _make_record(user_id: str, summary: str, *, protected: bool = False, salience: float = 0.5):  # type: ignore[return]
    """Helper to construct a minimal MemoryRecord for record store contract tests."""
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    return MemoryRecord(
        user_id=user_id,
        session_id="s_rs_contract",
        record_type=RecordType.FACT,
        content=summary,
        summary=summary,
        protected=protected,
        salience=salience,
    )


class TestRecordStoreContract:
    """RecordStore Protocol contract assertions.

    All assertions must hold for every registered t1_backend.
    """

    async def test_upsert_and_get_roundtrip(self, t1_backend, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        """upsert_with_vector() + get() must retrieve a record with matching content."""
        if embedder_backend.dim != t1_backend.dim:
            import pytest  # noqa: PLC0415
            pytest.skip("dim mismatch between t1 and embedder fixture params")

        record = _make_record("u_rs_roundtrip", "test fact for roundtrip")
        embedding = (await embedder_backend.embed([record.content]))[0]
        await t1_backend.upsert_with_vector(record, embedding)

        retrieved = await t1_backend.get(record.id)
        assert retrieved is not None, (
            f"get({record.id!r}) must return the upserted record, got None"
        )
        assert retrieved.content == record.content, (
            f"Retrieved content {retrieved.content!r} != inserted {record.content!r}"
        )
        assert retrieved.user_id == record.user_id, (
            f"Retrieved user_id {retrieved.user_id!r} != inserted {record.user_id!r}"
        )

    async def test_live_records_excludes_superseded(self, t1_backend, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        """live_records() must not yield records that have valid_until set."""
        if embedder_backend.dim != t1_backend.dim:
            import pytest  # noqa: PLC0415
            pytest.skip("dim mismatch between t1 and embedder fixture params")

        user_id = "u_rs_live"
        old_record = _make_record(user_id, "old record to be superseded")
        new_record = _make_record(user_id, "new record replacing old one")

        old_emb = (await embedder_backend.embed([old_record.content]))[0]
        new_emb = (await embedder_backend.embed([new_record.content]))[0]

        await t1_backend.upsert_with_vector(old_record, old_emb)
        # Supersede old_record with new_record
        await t1_backend.supersede(old_record.id, new_record, new_emb)

        # Collect all live records for user_id
        live_ids: list[str] = []
        async for rec in t1_backend.live_records(user_id):
            live_ids.append(rec.id)

        assert old_record.id not in live_ids, (
            f"Superseded record {old_record.id!r} must NOT appear in live_records()"
        )
        assert new_record.id in live_ids, (
            f"New record {new_record.id!r} must appear in live_records() after supersede()"
        )

    async def test_update_fields_changes_attribute(self, t1_backend, embedder_backend) -> None:  # type: ignore[no-untyped-def]
        """update() must change the specified field on the stored record."""
        if embedder_backend.dim != t1_backend.dim:
            import pytest  # noqa: PLC0415
            pytest.skip("dim mismatch between t1 and embedder fixture params")

        record = _make_record("u_rs_update", "record to update salience")
        embedding = (await embedder_backend.embed([record.content]))[0]
        await t1_backend.upsert_with_vector(record, embedding)

        await t1_backend.update(record.id, salience=0.9)
        retrieved = await t1_backend.get(record.id)

        assert retrieved is not None, "Record must still exist after update()"
        assert abs(retrieved.salience - 0.9) < 0.001, (
            f"update(salience=0.9) must change salience to 0.9, got {retrieved.salience}"
        )

    async def test_scope_isolation_user_a_cannot_read_user_b(
        self, t1_backend, embedder_backend
    ) -> None:  # type: ignore[no-untyped-def]
        """SECURITY INVARIANT (D4-02): user A's records must not appear in user B's live_records.

        This asserts the hard isolation boundary — the user_id predicate must be
        enforced on every SELECT query in the backend.
        """
        if embedder_backend.dim != t1_backend.dim:
            import pytest  # noqa: PLC0415
            pytest.skip("dim mismatch between t1 and embedder fixture params")

        # Upsert a record for user_a
        user_a_record = _make_record("u_scope_a", "user A secret fact")
        emb_a = (await embedder_backend.embed([user_a_record.content]))[0]
        await t1_backend.upsert_with_vector(user_a_record, emb_a)

        # Query live_records for user_b — must be empty
        user_b_ids: list[str] = []
        async for rec in t1_backend.live_records("u_scope_b"):
            user_b_ids.append(rec.id)

        assert user_a_record.id not in user_b_ids, (
            f"SCOPE ISOLATION VIOLATION: user_a's record {user_a_record.id!r} "
            "appeared in user_b's live_records() — user_id predicate not enforced"
        )
        assert len(user_b_ids) == 0, (
            f"user_b has no records but live_records() returned {user_b_ids!r}"
        )

    async def test_protected_record_survives_decay(
        self, t1_backend, embedder_backend
    ) -> None:  # type: ignore[no-untyped-def]
        """SAFETY INVARIANT (FORG-03): protected records must NEVER be yielded by decay_pass.

        Seed a protected record with salience=0.0, access_count=0, created_at backdated
        365 days — its keep_score would be extremely low. Verify decay_pass never yields it.
        """
        from mnema.core.decay import decay_pass  # noqa: PLC0415

        if embedder_backend.dim != t1_backend.dim:
            import pytest  # noqa: PLC0415
            pytest.skip("dim mismatch between t1 and embedder fixture params")

        user_id = "u_forg03"
        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=365)

        # Create a record that would have a near-zero keep_score if it weren't protected
        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415
        protected_record = MemoryRecord(
            user_id=user_id,
            session_id="s_rs_contract",
            record_type=RecordType.FACT,
            content="critical allergy: peanuts",
            summary="critical allergy: peanuts",
            protected=True,
            salience=0.0,   # lowest possible salience
            access_count=0,
            created_at=old_date,
        )

        embedding = (await embedder_backend.embed([protected_record.content]))[0]
        await t1_backend.upsert_with_vector(protected_record, embedding)

        # Run decay_pass over the backend — collect all yielded record IDs
        decayed_ids: list[str] = []
        async for rec, _score in decay_pass(t1_backend, user_id, now=now):
            decayed_ids.append(rec.id)

        assert protected_record.id not in decayed_ids, (
            f"FORG-03 VIOLATION: protected record {protected_record.id!r} "
            "was yielded by decay_pass — protected records must NEVER be eviction candidates"
        )

    async def test_eviction_does_not_hard_delete(
        self, t1_backend, embedder_backend
    ) -> None:  # type: ignore[no-untyped-def]
        """SAFETY INVARIANT (FORG-04): eviction must set valid_until, not hard-delete the row.

        Simulate eviction: set valid_until + delete the vector. The record row must
        still be retrievable via get(), proving it was NOT hard-deleted.
        """
        if embedder_backend.dim != t1_backend.dim:
            import pytest  # noqa: PLC0415
            pytest.skip("dim mismatch between t1 and embedder fixture params")

        record = _make_record("u_forg04", "record to be evicted non-destructively")
        embedding = (await embedder_backend.embed([record.content]))[0]
        await t1_backend.upsert_with_vector(record, embedding)

        # Simulate eviction: set valid_until (retire) + delete vector
        now = datetime.now(timezone.utc)
        await t1_backend.update(record.id, valid_until=now)
        await t1_backend.delete_vector(record.id)

        # The record row must still exist with valid_until set
        retrieved = await t1_backend.get(record.id)
        assert retrieved is not None, (
            f"FORG-04 VIOLATION: get({record.id!r}) returned None after eviction — "
            "record was hard-deleted; eviction must only set valid_until"
        )
        assert retrieved.valid_until is not None, (
            f"FORG-04: evicted record must have valid_until set, got None"
        )
