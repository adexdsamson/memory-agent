"""Standalone unit tests for the MemoryRecord schema (CORE-02/03/04/05).

These tests construct MemoryRecord directly via Pydantic — no engine, no adapters,
no async. They lock the un-retrofittable column contract and the structural defaults
that the rest of the system relies on (the SqliteT1 DDL is derived from this model).
"""

from __future__ import annotations

from mnema.core.schema import MemoryRecord, RecordType


def _record(**overrides: object) -> MemoryRecord:
    base: dict[str, object] = {
        "user_id": "u1",
        "session_id": "s1",
        "record_type": RecordType.FACT,
        "content": "test",
    }
    base.update(overrides)
    return MemoryRecord(**base)  # type: ignore[arg-type]


def test_minimal_construction() -> None:
    """CORE-01/02: a record constructs from the four mandatory scope+content fields."""
    record = _record()
    assert record.user_id == "u1"
    assert record.session_id == "s1"
    assert record.content == "test"
    assert record.record_type is RecordType.FACT


def test_protected_is_bool_not_int() -> None:
    """CORE-04: `protected` is a real bool (structural flag), not an int 0/1."""
    record = _record()
    assert record.protected is False
    assert isinstance(record.protected, bool)


def test_new_record_is_live() -> None:
    """CORE-05: new records have valid_until=None so the hot path's IS NULL filter keeps them."""
    record = _record()
    assert record.valid_until is None


def test_embedding_provenance_unset_at_construction() -> None:
    """CORE-03: embedding provenance is None at construction — WritePath sets it at write time."""
    record = _record()
    assert record.embedding_model is None
    assert record.embedding_dim is None
    assert record.embedding_version is None


def test_record_type_string_coerced_to_enum() -> None:
    """CORE-02: a plain string record_type is coerced to the RecordType StrEnum member."""
    record = _record(record_type="fact")
    assert record.record_type is RecordType.FACT
    assert isinstance(record.record_type, RecordType)


def test_access_count_baseline_zero() -> None:
    """RECALL-07: access_count starts at 0; recall is what increments it."""
    record = _record()
    assert record.access_count == 0
    assert record.last_accessed is None


def test_un_retrofittable_columns_present() -> None:
    """The full un-retrofittable column set must exist on the model (drives the DDL)."""
    fields = MemoryRecord.model_fields.keys()
    for col in (
        "user_id",
        "session_id",
        "agent_id",
        "embedding_model",
        "embedding_dim",
        "embedding_version",
        "protected",
        "valid_until",
        "access_count",
        "last_accessed",
    ):
        assert col in fields, f"missing un-retrofittable column: {col}"
