"""MNEMA budget packer — pure synchronous, no I/O.

Provides re_rank(), TokenCounter Protocol, TiktokenCounter, ByteLengthCounter,
and pack_records() for token-budget-aware recall output.

D-12 compliance: this module contains ZERO I/O operations and ZERO async calls.
It may be imported and called from any context including synchronous test code.

The two-pass packer (D3-07, RECALL-05) ensures that protected records and live
FACT-type records are ALWAYS included in the output regardless of budget pressure
from high-volume off-topic history. Pass 1 reserves slots for the critical set;
Pass 2 fills remaining budget by re-rank score.

RECALL-03: re_rank() composite score = similarity * salience * recency_decay
RECALL-04: pack_records() fits summaries under a caller-supplied token budget
RECALL-05: Two-pass packer preserves critical facts under adversarial flood conditions
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from mnema.core.decay import LAMBDA_DECAY

if TYPE_CHECKING:
    from mnema.core.schema import MemoryRecord


# ---------------------------------------------------------------------------
# TokenCounter Protocol — pluggable token counting (D3-06, D-12)
# ---------------------------------------------------------------------------


class TokenCounter(Protocol):
    """Pluggable token counter for the budget packer (D3-06).

    Must be synchronous (D-12 — pure logic, no I/O).
    No @runtime_checkable — static checking only (D-10).
    """

    def count(self, text: str) -> int:
        """Return the token count for text."""
        ...


# ---------------------------------------------------------------------------
# TokenCounter adapters
# ---------------------------------------------------------------------------


class TiktokenCounter:
    """Default token counter backed by tiktoken cl100k_base.

    Pre-built binary wheel available for Python 3.12 Windows (verified 2026-06-14).
    Import is deferred into __init__ so a missing tiktoken installation only fails
    at construction time, not at module import time (allows ByteLengthCounter
    fallback in environments without tiktoken).
    """

    def __init__(self) -> None:
        import tiktoken  # noqa: PLC0415

        self._enc = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        """Return tiktoken BPE token count for text."""
        return len(self._enc.encode(text))


class ByteLengthCounter:
    """Portable fallback token counter: estimate tokens as len(text.encode("utf-8")) // 4.

    This 4-byte approximation is accurate for English short summaries
    (e.g. a 9-token English sentence of ~36 characters gives 9 via this heuristic).
    Zero runtime dependencies — works in any environment without tiktoken.
    Use as the default counter in tests and offline/restricted environments.
    """

    def count(self, text: str) -> int:
        """Return estimated token count for text (len(utf-8 bytes) // 4, min 1)."""
        return max(1, len(text.encode("utf-8")) // 4)


# ---------------------------------------------------------------------------
# re_rank — pure sync re-ranking function (D3-05, RECALL-03)
# ---------------------------------------------------------------------------


def re_rank(
    records: "list[MemoryRecord]",
    similarity_scores: "dict[str, float]",
    now: datetime | None = None,
) -> "list[MemoryRecord]":
    """Re-rank records by relevance * salience * recency_decay (D3-05, RECALL-03).

    Pure sync per D-12 — no I/O, no async calls.

    Composite score = similarity * salience * exp(-LAMBDA_DECAY * age_days)

    Where:
      - similarity: from similarity_scores dict (defaults to 0.5 for buffer-
        synthesized records without a vector hit — per RESEARCH.md Pattern 3).
      - salience: LLM-judged long-term importance weight from the record.
      - recency_decay: exponential decay from last_accessed (or created_at if
        last_accessed is None), reusing LAMBDA_DECAY from decay.py (D-12).

    Args:
        records: The records to re-rank. Returned in a new sorted list; input
            list is not mutated.
        similarity_scores: Mapping from record_id to raw vector similarity score.
            Records not in this dict receive a default similarity of 0.5.
        now: Reference time for recency decay. Defaults to datetime.now(UTC).
            Pass an explicit value in tests for determinism.

    Returns:
        A new list of records sorted by descending composite score.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    def composite(r: "MemoryRecord") -> float:
        ref = r.last_accessed if r.last_accessed is not None else r.created_at
        age_days = max(0.0, (now - ref).total_seconds() / 86400.0)
        recency = math.exp(-LAMBDA_DECAY * age_days)
        sim = similarity_scores.get(r.id, 0.5)
        return sim * r.salience * recency

    return sorted(records, key=composite, reverse=True)


# ---------------------------------------------------------------------------
# pack_records — two-pass budget packer (D3-07, RECALL-04/05)
# ---------------------------------------------------------------------------


def pack_records(
    ranked: "list[MemoryRecord]",
    budget: int,
    counter: TokenCounter,
) -> "list[MemoryRecord]":
    """Two-pass budget packer (D3-07, RECALL-04, RECALL-05).

    Pass 1: Reserve slots for the CRITICAL_SET = records where:
        record.protected is True  OR
        (record.record_type == RecordType.FACT AND record.valid_until is None)

    Critical records are always included (up to budget). Protected records have
    priority within the critical set (they appear first in ranked because re_rank
    scores them highest — salience=1.0 by convention for allergy/protected facts).
    If the critical set alone exceeds budget, it is truncated at the budget limit
    (critical set items maintain their relative re-rank order from Pass 1).

    Pass 2: Fill remaining budget by re-rank score (descending). Use ``continue``
    (not ``break``) when a record is oversized so shorter later records can still
    fit (RESEARCH.md Pitfall 3).

    Budget unit: tokens counted by counter.count(record.summary or record.content[:80]).

    Args:
        ranked: Records sorted by descending composite score (output of re_rank).
        budget: Maximum total token budget for the output.
        counter: TokenCounter implementation to measure each record's cost.

    Returns:
        A list of records whose token costs sum to <= budget, with critical facts
        always included (Pass 1 reservation).

    Threat mitigations:
        T-03-02-01 (RECALL-05 adversarial displacement): The two-pass reservation
        ensures a caller cannot provide a large budget-consuming non-critical history
        that pushes a critical fact out. Critical slots are reserved in Pass 1;
        budget overflow in Pass 2 cannot retroactively remove them.
    """
    from mnema.core.schema import RecordType  # noqa: PLC0415

    # Partition: critical = protected OR (FACT-type AND live/not-expired)
    critical: list[MemoryRecord] = [
        r
        for r in ranked
        if r.protected or (r.record_type == RecordType.FACT and r.valid_until is None)
    ]

    packed: list[MemoryRecord] = []
    used = 0

    # Pass 1: reserve slots for critical records (in ranked order)
    for rec in critical:
        cost = counter.count(rec.summary or rec.content[:80])
        if used + cost <= budget:
            packed.append(rec)
            used += cost

    # Build O(1) lookup of already-packed IDs before Pass 2
    packed_ids: set[str] = {r.id for r in packed}

    # Pass 2: fill remaining budget from all ranked records (skip already-packed)
    for rec in ranked:
        if rec.id in packed_ids:
            continue
        cost = counter.count(rec.summary or rec.content[:80])
        if used + cost > budget:
            continue  # skip oversized record — a shorter later record may still fit
        packed.append(rec)
        packed_ids.add(rec.id)
        used += cost

    return packed
