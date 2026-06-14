"""Phase 3 vault promotion tests — CONS-09, TIER-03.

CONS-09  Stable records are promoted into the T2 canonical vault during
         consolidation.
TIER-03  T2 canonical vault holds merged, deduped, human-readable, git-versioned
         user model files.

TestLocalFSVault — unit tests for the LocalFSVault adapter.
test_vault_promotion_before_eviction — ordering test: vault pass BEFORE eviction.
test_consolidate_user_isolation — isolation test: consolidate(user_id=u1) must
    not touch u2's vault or T1 records.
test_promotion_on_consolidation — integration: confirmed high-salience records
    promoted to vault during consolidation.

GREEN after Plan 03-03 implementation of LocalFSVault and ConsolidationPipeline
vault+eviction wiring. engine_with_vault fixture is provided by conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# TIER-03: LocalFSVault unit tests
# ---------------------------------------------------------------------------


class TestLocalFSVault:
    """Unit tests for the LocalFSVault adapter (TIER-03).

    Tests import LocalFSVault using deferred imports.  They will FAIL until
    Plan 03-03 implements src/mnema/adapters/vault/local_fs_vault.py.
    """

    async def test_promote_writes_markdown(self, tmp_path) -> None:
        """TIER-03: promote() writes a markdown file for the user."""
        from mnema.adapters.vault.local_fs_vault import LocalFSVault  # noqa: PLC0415

        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

        vault = LocalFSVault(str(tmp_path / "vault"))
        record = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.FACT,
            content="allergy: peanuts",
            summary="allergy: peanuts",
            salience=0.9,
        )
        await vault.promote(record)

        vault_file = tmp_path / "vault" / "u1.md"
        assert vault_file.exists(), "promote() must create {user_id}.md in base_dir"
        content = vault_file.read_text(encoding="utf-8")
        assert "allergy: peanuts" in content, (
            f"Promoted record summary must appear in vault file; got: {content!r}"
        )

    async def test_promote_deduplication(self, tmp_path) -> None:
        """TIER-03: Promoting the same record twice does not duplicate it (D3-12)."""
        from mnema.adapters.vault.local_fs_vault import LocalFSVault  # noqa: PLC0415

        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

        vault = LocalFSVault(str(tmp_path / "vault"))
        record = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.PREFERENCE,
            content="prefers vegetarian food",
            summary="prefers vegetarian food",
            salience=0.8,
        )
        await vault.promote(record)
        await vault.promote(record)  # promote again — should be idempotent

        vault_file = tmp_path / "vault" / "u1.md"
        content = vault_file.read_text(encoding="utf-8")
        count = content.count("prefers vegetarian food")
        assert count == 1, (
            f"Duplicate promotion must be deduped; found {count} occurrences"
        )

    async def test_promote_sectioned_by_type(self, tmp_path) -> None:
        """TIER-03: Vault file sections records by record_type."""
        from mnema.adapters.vault.local_fs_vault import LocalFSVault  # noqa: PLC0415

        from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

        vault = LocalFSVault(str(tmp_path / "vault"))
        fact_rec = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.FACT,
            content="fact: has diabetes",
            summary="has diabetes",
            salience=0.9,
        )
        pref_rec = MemoryRecord(
            user_id="u1",
            session_id="s1",
            record_type=RecordType.PREFERENCE,
            content="preference: vegan diet",
            summary="vegan diet",
            salience=0.7,
        )
        await vault.promote(fact_rec)
        await vault.promote(pref_rec)

        vault_file = tmp_path / "vault" / "u1.md"
        content = vault_file.read_text(encoding="utf-8")
        # Both section headers should exist
        assert "## Facts" in content or "## Fact" in content, (
            f"Vault file must have a Facts section; got: {content!r}"
        )
        assert "## Preferences" in content or "## Preference" in content, (
            f"Vault file must have a Preferences section; got: {content!r}"
        )


# ---------------------------------------------------------------------------
# BLOCKER 2 ordering test — vault pass before eviction (RESEARCH.md Pitfall 8)
# ---------------------------------------------------------------------------


async def test_vault_promotion_before_eviction(engine_with_vault, tmp_path) -> None:
    """Ordering test: vault promotion pass runs BEFORE eviction pass.

    Scenario: seed a record with salience=0.72 (above VAULT_SALIENCE_THRESHOLD=0.7)
    AND backdated created_at (180 days ago) plus access_count=0.  The record's
    keep_score is low enough to be below KEEP_THRESHOLD=0.3 — it should be evicted.

    After consolidate():
    (a) The record must appear in the vault markdown file (it was promoted first).
    (b) The record must have valid_until set (it was evicted after promotion).

    This proves the two-pass ordering: vault pass first, eviction pass second.
    If eviction ran first, valid_until would be set BEFORE promote(), but promote()
    only promotes records with valid_until IS NULL — so the vault would be empty.
    """
    from mnema.adapters.vault.local_fs_vault import LocalFSVault  # noqa: PLC0415
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    engine = engine_with_vault
    vault: LocalFSVault = engine._vault  # type: ignore[attr-defined]

    # Seed a record directly into T1 (bypass write_path to control salience/date precisely)
    # salience=0.72 (above VAULT_SALIENCE_THRESHOLD=0.7)
    # created_at backdated 180 days (keep_score will be very low, well below 0.3)
    # access_count=0 (no access reinforcement)
    # provisional=False (confirmed — eligible for vault)
    # valid_until=None (live)
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=180)

    record = MemoryRecord(
        user_id="u1",
        session_id="s1",
        record_type=RecordType.FACT,
        content="borderline high-salience old fact",
        summary="borderline high-salience old fact",
        salience=0.72,
        provisional=False,
        created_at=old_date,
        access_count=0,
    )

    # Insert into T1 with a zero embedding (128-dim stub)
    embedding = [0.0] * engine._embedder.dim  # type: ignore[attr-defined]
    await engine._t1.upsert_with_vector(record, embedding)  # type: ignore[attr-defined]

    # Run consolidation with no staged items — vault+eviction pass still runs on
    # the live records for any user_id if processed_user_ids is non-empty.
    # We stage a dummy turn for u1 so processed_user_ids includes "u1".
    await engine.remember(
        "dummy turn to trigger consolidation for u1",
        user_id="u1",
        session_id="s1",
    )
    await engine.consolidate()

    # (a) Vault must contain the record's summary (promoted before eviction)
    vault_content = await vault.get_user_model("u1")
    assert "borderline high-salience old fact" in vault_content, (
        f"Vault must contain promoted record; got vault content: {vault_content!r}"
    )

    # (b) T1 record must have valid_until set (evicted after vault promotion)
    updated_record = await engine._t1.get(record.id)  # type: ignore[attr-defined]
    assert updated_record is not None, "Record must still exist in T1 (not hard-deleted)"
    assert updated_record.valid_until is not None, (
        "Record must have valid_until set (evicted) after consolidation — "
        "vault promotion must have run first (Pitfall 8 ordering guarantee)"
    )


# ---------------------------------------------------------------------------
# WARNING 7 isolation test — consolidate(user_id=u1) must not touch u2
# ---------------------------------------------------------------------------


async def test_consolidate_user_isolation(engine_with_vault) -> None:
    """Isolation test: consolidation for u1 must not process or touch u2's data.

    Stage a turn for u1 AND a turn for u2.  Call engine.consolidate(user_id='u1').
    Assert:
    - u2's staged turn was NOT consumed (verified by checking u2's vault is empty).
    - u2's T1 records were NOT promoted or evicted.
    """
    from mnema.adapters.vault.local_fs_vault import LocalFSVault  # noqa: PLC0415
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    engine = engine_with_vault
    vault: LocalFSVault = engine._vault  # type: ignore[attr-defined]

    # Stage a turn for u1 and a turn for u2
    await engine.remember(
        "u1 preference: gluten free",
        user_id="u1",
        session_id="s1",
    )
    await engine.remember(
        "u2 preference: dairy free",
        user_id="u2",
        session_id="s2",
    )

    # Seed a high-salience confirmed record for u2 to see if it gets promoted
    now_ref = datetime.now(timezone.utc)
    u2_record = MemoryRecord(
        user_id="u2",
        session_id="s2",
        record_type=RecordType.FACT,
        content="u2 critical fact",
        summary="u2 critical fact",
        salience=0.9,
        provisional=False,
        created_at=now_ref,
    )
    embedding = [0.0] * engine._embedder.dim  # type: ignore[attr-defined]
    await engine._t1.upsert_with_vector(u2_record, embedding)  # type: ignore[attr-defined]

    # Consolidate ONLY for u1 — u2's staged turn and records must be untouched
    await engine.consolidate(user_id="u1")

    # u2's vault must be empty (no promotion ran for u2)
    u2_vault_content = await vault.get_user_model("u2")
    assert "u2 critical fact" not in u2_vault_content, (
        "consolidate(user_id='u1') must NOT promote u2's records to vault — "
        f"got u2 vault content: {u2_vault_content!r}"
    )

    # u2's high-salience record must still be live (valid_until is None)
    u2_rec_after = await engine._t1.get(u2_record.id)  # type: ignore[attr-defined]
    assert u2_rec_after is not None, "u2 record must still exist in T1"
    assert u2_rec_after.valid_until is None, (
        "consolidate(user_id='u1') must NOT evict u2's records"
    )


# ---------------------------------------------------------------------------
# CONS-09 integration test
# ---------------------------------------------------------------------------


async def test_promotion_on_consolidation(engine_with_vault) -> None:
    """CONS-09: Confirmed high-salience records are promoted to vault on consolidation.

    After engine.consolidate(), any confirmed (non-provisional), live record with
    salience >= VAULT_SALIENCE_THRESHOLD must appear in the vault user model.
    """
    from mnema.adapters.vault.local_fs_vault import LocalFSVault  # noqa: PLC0415
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    engine = engine_with_vault
    vault: LocalFSVault = engine._vault  # type: ignore[attr-defined]

    # Seed a confirmed, high-salience, live fact record directly into T1
    record = MemoryRecord(
        user_id="u1",
        session_id="s1",
        record_type=RecordType.FACT,
        content="allergy: tree nuts",
        summary="allergy: tree nuts",
        salience=0.95,
        provisional=False,
    )
    embedding = [0.0] * engine._embedder.dim  # type: ignore[attr-defined]
    await engine._t1.upsert_with_vector(record, embedding)  # type: ignore[attr-defined]

    # Stage a dummy turn so consolidation runs the vault pass for u1
    await engine.remember(
        "trigger consolidation for u1",
        user_id="u1",
        session_id="s1",
    )
    await engine.consolidate()

    # The high-salience confirmed record must appear in the vault
    vault_content = await vault.get_user_model("u1")
    assert "allergy: tree nuts" in vault_content, (
        "CONS-09: confirmed high-salience record must appear in vault after consolidate(); "
        f"got vault content: {vault_content!r}"
    )
