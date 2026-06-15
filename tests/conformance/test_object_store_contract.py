"""ObjectStorePort conformance contract tests.

Parametrized over all registered object_store_backend fixture backends.
Local-always backends (local_fs) run unconditionally.
moto_s3 backend stubs with skip until OSSS3Store ships in plan 04-06.
OSS backend skips when MNEMA_TEST_OSS is absent.

Key assertions:
  - append() + get() roundtrip preserves Turn content
  - append() returns a t0://session_id/N formatted ref
  - archive() returns a non-empty ref
  - append_audit() does not raise
  - invalid session_id raises ValueError (T-04-01-03 path-traversal guard)
"""

from __future__ import annotations


def _make_record(user_id: str, summary: str):  # type: ignore[return]
    """Helper to construct a minimal MemoryRecord for object store contract tests."""
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    return MemoryRecord(
        user_id=user_id,
        session_id="s_os_contract",
        record_type=RecordType.FACT,
        content=summary,
        summary=summary,
    )


def _make_turn(session_id: str, content: str):  # type: ignore[return]
    """Helper to construct a minimal Turn for object store contract tests."""
    from mnema.core.schema import Turn  # noqa: PLC0415

    return Turn(session_id=session_id, content=content, role="user")


class TestObjectStoreContract:
    """ObjectStorePort Protocol contract assertions.

    All assertions must hold for every registered object_store_backend.
    """

    async def test_append_and_get_roundtrip(self, object_store_backend) -> None:  # type: ignore[no-untyped-def]
        """append() + get() must roundtrip Turn content faithfully."""
        turn = _make_turn("sess_01", "the user said hello")
        ref = await object_store_backend.append("sess_01", turn)
        retrieved = await object_store_backend.get(ref)
        assert retrieved.content == turn.content, (
            f"get({ref!r}) must return a Turn with content {turn.content!r}; "
            f"got {retrieved.content!r}"
        )

    async def test_append_ref_format(self, object_store_backend) -> None:  # type: ignore[no-untyped-def]
        """append() must return a ref in 't0://session_id/N' format."""
        turn = _make_turn("sess_01", "ref format test")
        ref = await object_store_backend.append("sess_01", turn)
        assert ref.startswith("t0://sess_01/"), (
            f"append() ref must start with 't0://sess_01/'; got {ref!r}"
        )

    async def test_archive_returns_ref(self, object_store_backend) -> None:  # type: ignore[no-untyped-def]
        """archive() must return a non-empty ref string."""
        record = _make_record("u_os_archive", "archived cold storage record")
        ref = await object_store_backend.archive(record)
        assert ref is not None, "archive() must return a non-None ref"
        assert len(ref) > 0, "archive() must return a non-empty ref string"

    async def test_append_audit_does_not_raise(self, object_store_backend) -> None:  # type: ignore[no-untyped-def]
        """append_audit() must not raise for a valid audit entry dict."""
        entry = {
            "record_id": "r1",
            "user_id": "u1",
            "keep_score": 0.1,
            "evicted_at": "2026-01-01T00:00:00Z",
            "reason": "decay",
        }
        # Must not raise
        await object_store_backend.append_audit(entry)

    async def test_invalid_session_id_raises(self, object_store_backend) -> None:  # type: ignore[no-untyped-def]
        """append() with a path-traversal session_id must raise ValueError (T-04-01-03).

        The _VALID_SESSION_ID guard must reject session_ids containing '..', '/',
        or other characters that could be used for directory traversal.
        """
        import pytest  # noqa: PLC0415

        turn = _make_turn("../../etc/passwd", "path traversal attempt")
        with pytest.raises(ValueError):
            await object_store_backend.append("../../etc/passwd", turn)
