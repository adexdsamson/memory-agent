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

All tests use deferred imports and will FAIL until Plan 03-03 implements
LocalFSVault and the vault promotion hook in ConsolidationPipeline.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# engine_with_vault fixture — placeholder (replaced by conftest in Plan 03-03)
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine_with_vault(tmp_path, stub_embedder):  # type: ignore[return]
    """Placeholder fixture: yields None in Wave 0.

    Plan 03-03 will replace this with a fully-wired MemoryEngine that includes
    a LocalFSVault adapter injected as the vault= kwarg.  Tests using this
    fixture will FAIL at assertion time in RED state.
    """
    yield None  # RED: replaced by Plan 03-03


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


async def test_vault_promotion_before_eviction(engine_with_vault) -> None:
    """Ordering test: vault promotion pass runs BEFORE eviction pass.

    Scenario: seed a record with salience=0.72 (above VAULT_SALIENCE_THRESHOLD=0.7)
    AND backdated created_at (180 days ago) plus access_count=0.  The record's
    keep_score is low enough to be below KEEP_THRESHOLD=0.3 — it should be evicted.

    After consolidate():
    (a) The record must appear in the vault markdown file (it was promoted first).
    (b) The record must have valid_until set (it was evicted after promotion).

    This proves the two-pass ordering: vault pass first, eviction pass second.
    GREEN implementation requires Plan 03-03.
    """
    # TODO Plan 03-03: seed salience=0.72 + backdated record; after consolidate()
    # assert vault contains it AND valid_until is set.
    assert False, (  # noqa: B011
        "TODO Plan 03-03: seed salience=0.72 + old record; after consolidate() "
        "assert vault contains it AND valid_until is set"
    )


# ---------------------------------------------------------------------------
# WARNING 7 isolation test — consolidate(user_id=u1) must not touch u2
# ---------------------------------------------------------------------------


async def test_consolidate_user_isolation(engine_with_vault) -> None:
    """Isolation test: consolidation for u1 must not process or touch u2's data.

    Stage a turn for u1 AND a turn for u2.  Call engine.consolidate(user_id='u1').
    Assert:
    - u2's staged turn was NOT consumed (still pending or u2's vault untouched).
    - u2's T1 records were NOT promoted or evicted.

    GREEN implementation requires Plan 03-03 user_id filter on
    ConsolidationPipeline.run().
    """
    # TODO Plan 03-03: stage u1 + u2 turns; consolidate(u1); verify u2 unaffected
    assert False, (  # noqa: B011
        "TODO Plan 03-03: stage turns for u1 and u2; consolidate u1; "
        "verify u2's vault and T1 are untouched"
    )


# ---------------------------------------------------------------------------
# CONS-09 integration test
# ---------------------------------------------------------------------------


async def test_promotion_on_consolidation(engine_with_vault) -> None:
    """CONS-09: Confirmed high-salience records are promoted to vault on consolidation.

    After engine.consolidate(), any confirmed (non-provisional), live record with
    salience >= VAULT_SALIENCE_THRESHOLD must appear in the vault user model.
    GREEN implementation requires Plan 03-03 vault promotion hook.
    """
    # TODO Plan 03-03: remember → consolidate → assert record appears in vault
    assert False, (  # noqa: B011
        "TODO Plan 03-03: remember high-salience fact; consolidate(); "
        "assert record appears in vault get_user_model() output"
    )
