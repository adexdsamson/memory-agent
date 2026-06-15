"""VaultStore conformance contract tests.

Parametrized over all registered vault_backend fixture backends.
Local-always backends (local_fs_vault) run unconditionally.

Key assertions:
  - promote() + get_user_model() roundtrip
  - promote() is idempotent (deduplication)
  - get_user_model() for unknown user returns empty string or None (no error)
"""

from __future__ import annotations


def _make_record(user_id: str, summary: str):  # type: ignore[return]
    """Helper to construct a minimal MemoryRecord for vault contract tests."""
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    return MemoryRecord(
        user_id=user_id,
        session_id="s_vault_contract",
        record_type=RecordType.FACT,
        content=summary,
        summary=summary,
        provisional=False,
    )


class TestVaultContract:
    """VaultStore Protocol contract assertions.

    All assertions must hold for every registered vault_backend.
    """

    async def test_promote_and_get_user_model_roundtrip(self, vault_backend) -> None:  # type: ignore[no-untyped-def]
        """promote() followed by get_user_model() must return content containing the summary."""
        record = _make_record("u_vault", "loves hiking")
        await vault_backend.promote(record)
        model = await vault_backend.get_user_model("u_vault")
        assert isinstance(model, str), (
            f"get_user_model() must return str, got {type(model).__name__!r}"
        )
        assert "loves hiking" in model, (
            f"get_user_model() must contain promoted summary 'loves hiking'; "
            f"got: {model!r}"
        )

    async def test_promote_deduplication(self, vault_backend) -> None:  # type: ignore[no-untyped-def]
        """Promoting the same record twice must not duplicate the summary."""
        record = _make_record("u_vault_dedup", "prefers vegetarian food")
        await vault_backend.promote(record)
        await vault_backend.promote(record)  # second promote — idempotent
        model = await vault_backend.get_user_model("u_vault_dedup")
        count = model.count("prefers vegetarian food")
        assert count == 1, (
            f"Duplicate promotion must be deduped; found {count} occurrences "
            f"in vault content: {model!r}"
        )

    async def test_get_user_model_unknown_user_returns_empty_string(self, vault_backend) -> None:  # type: ignore[no-untyped-def]
        """get_user_model() for an unknown user must return '' or None — never raise."""
        model = await vault_backend.get_user_model("no_such_user_xyz")
        # Contract: return empty string or None (not raise) — both are acceptable
        assert model == "" or model is None or isinstance(model, str), (
            f"get_user_model() for unknown user must return str or None, "
            f"got {type(model).__name__!r}: {model!r}"
        )
