"""MNEMA T1 record schema — single source of truth.

All un-retrofittable columns are defined here. The SQL DDL in SqliteT1 is derived
from this model. Any column missing here cannot be added without a migration.

Do NOT import from any adapter or port — this file has zero outward dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    """Return the current UTC time as an aware datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class RecordType(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    PROCEDURE = "procedure"


class Turn(BaseModel):
    """T0 raw episodic unit — one conversational turn appended verbatim."""

    id: str = Field(default_factory=lambda: f"turn_{uuid.uuid4().hex[:12]}")
    session_id: str
    content: str
    role: str = "user"
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    """T1 working-memory record — typed, scoped, with full embedding provenance.

    Column layout follows CORE-01..05 requirements; all un-retrofittable columns
    are non-nullable or have stable defaults. The `protected` flag is structural
    (a boolean DDL column), not a salience threshold — the decay pass skips a
    protected record *before* any score math.
    """

    model_config = ConfigDict(from_attributes=False)

    # Identity + scope (CORE-01) — ALL mandatory / non-defaulted
    id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:12]}")
    user_id: str  # hard isolation boundary — non-defaulted
    session_id: str  # write-time provenance only, never in recall WHERE-clause
    agent_id: Optional[str] = None  # optional narrowing filter inside user boundary

    # Content (CORE-02)
    record_type: RecordType
    content: str
    summary: str = ""  # <= ~12 tokens; WritePath injects this
    keywords: list[str] = Field(default_factory=list)  # Phase 2 BM25, empty now

    # Embedding provenance (CORE-03) — un-retrofittable
    embedding_model: Optional[str] = None
    embedding_dim: Optional[int] = None
    embedding_version: Optional[str] = None

    # Safety (CORE-04) — structural, NOT a salience threshold
    protected: bool = False  # decay pass skips this BEFORE any score math

    # Lifecycle + supersession
    salience: float = 0.5
    confidence: float = 0.9
    provisional: bool = True  # cleared by consolidation (Phase 2)
    valid_from: datetime = Field(default_factory=_utcnow)
    valid_until: Optional[datetime] = None  # CORE-05: hot path filters IS NULL
    superseded_by: Optional[str] = None

    # Provenance
    t0_ref: Optional[str] = None  # "t0://session_id/offset" — backs expand(id)
    source_refs: list[str] = Field(default_factory=list)

    # Reinforcement (RECALL-07)
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)

    # Graph edges (Phase 2, store empty for now)
    graph_edges: list[dict[str, Any]] = Field(
        default_factory=lambda: []  # type: ignore[return-value]
    )
