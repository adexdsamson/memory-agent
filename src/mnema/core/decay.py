"""MNEMA keep_score decay — pure synchronous, no I/O.

Computes keep_score(record, now) for use by the consolidation pipeline (Phase 2)
and the forgetting/eviction pass (Phase 3).

D-12 compliance: this module contains ZERO I/O operations and ZERO async calls.
It may be imported and called from any context including synchronous test code.

The keep_score formula combines three signals:
  - Recency:       exponential decay from last access (Ebbinghaus forgetting curve)
  - Reinforcement: logarithmic access-count boost (spacing-effect diminishing returns)
  - Salience:      LLM-judged long-term importance weight

FORG-03: Protected records are NOT scored by keep_score -- callers (e.g. decay_pass)
must skip protected records BEFORE calling keep_score. The guard lives in the
caller, not inside this function. This is a structural guarantee: the Phase 3
eviction path cannot accidentally evict a protected record because decay_pass
never yields one.
"""

from __future__ import annotations

import math
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mnema.core.schema import MemoryRecord

# ---------------------------------------------------------------------------
# Tunable module-level constants (document rationale inline per PATTERNS.md)
# ---------------------------------------------------------------------------

W_RECENCY: float = 0.4
"""Weight on exponential recency decay.

At salience=0.5, access_count=0, age=0 days: recency contribution = 0.4 * 1.0 = 0.4.
"""

W_REINFORCE: float = 0.3
"""Weight on logarithmic access-count reinforcement.

Log-linear reinforcement follows the Ebbinghaus spacing effect -- early reinforcements
have the highest marginal value. An access_count=5 record scores log(6) ≈ 1.79;
the 0.3 weight caps its contribution at ~0.54 before clamping.
"""

W_SALIENCE: float = 0.3
"""Weight on LLM-judged long-term salience (0.0..1.0).

At salience=1.0 (maximum), contribution = 0.3. For a protected fact with salience=1.0,
the salience term alone is 0.3, providing defense-in-depth even without access activity.
This is intentional -- salience=1.0 records should resist eviction even when stale.
"""

LAMBDA_DECAY: float = 0.05
"""Recency half-life constant.

Half-life = ln(2) / LAMBDA_DECAY ≈ 13.9 days.  A record not accessed in two weeks
decays to ~0.50 of its recency contribution (exp(-0.05 * 14) ≈ 0.497).  Suitable for
dietary preferences that update on a weekly-to-monthly cadence.  Tune against the
Phase 5 demo evaluation if the cadence differs.
"""


# ---------------------------------------------------------------------------
# keep_score — pure synchronous scoring function (D-12)
# ---------------------------------------------------------------------------


def keep_score(record: "MemoryRecord", now: datetime | None = None) -> float:
    """Return the retention score for *record* in [0.0, 1.0].

    Pure sync per D-12 — no I/O, no async, no imports at runtime beyond
    ``math`` and ``datetime``.

    Reference time for recency: ``last_accessed`` if set, else ``created_at``
    (D2-15). This means a record that was recently accessed but is old by
    creation date decays from the *access* timestamp, not the creation date.

    Protected-record skip is the CALLER's responsibility (FORG-03). ``keep_score``
    computes the score regardless of the ``protected`` flag so it can be unit-tested
    directly; the ``decay_pass`` async generator skips protected records before
    calling this function.

    Args:
        record: The MemoryRecord to score. ``access_count`` and ``salience``
            are read directly; ``last_accessed`` / ``created_at`` determine age.
        now: The reference "current" time. Defaults to ``datetime.now(timezone.utc)``
            if omitted. Pass an explicit value in tests for determinism.

    Returns:
        A float in [0.0, 1.0]. Higher means "more worth keeping."

    Threat mitigations:
        T-02-04: ``max(0.0, age_days)`` clamp prevents a negative exp argument
        if ``now`` is somehow earlier than the reference time. Result is clamped
        to [0.0, 1.0] to handle high-access_count overflow.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Reference time: prefer last_accessed (more recent signal) over created_at (D2-15)
    ref_time = record.last_accessed if record.last_accessed is not None else record.created_at

    # T-02-04: clamp to 0 prevents a negative exponent from inflating recency
    age_days = max(0.0, (now - ref_time).total_seconds() / 86400.0)

    recency = math.exp(-LAMBDA_DECAY * age_days)
    reinforce = math.log(1.0 + float(record.access_count))
    score = W_RECENCY * recency + W_REINFORCE * reinforce + W_SALIENCE * record.salience

    # Clamp to [0.0, 1.0]: reinforce can push the score above 1.0 at high access_count
    return min(1.0, max(0.0, score))


# ---------------------------------------------------------------------------
# decay_pass — async generator (consumes a RecordStore.live_records interface)
# ---------------------------------------------------------------------------


async def decay_pass(
    record_store: "Any",
    user_id: str,
    now: datetime | None = None,
) -> AsyncGenerator[tuple["MemoryRecord", float], None]:
    """Async generator yielding (record, keep_score) for all live non-protected records.

    Iterates ``record_store.live_records(user_id)`` (which yields only live records,
    i.e. those with ``valid_until IS NULL``).

    FORG-03 structural guarantee: protected records are SKIPPED entirely -- they are
    never yielded to the caller. The Phase 3 eviction path cannot accidentally act on
    a protected record because it never appears in this generator's output. This is a
    stronger guarantee than yielding score=1.0: the caller cannot act on what it
    never sees.

    Args:
        record_store: Any object exposing
            ``live_records(user_id: str) -> AsyncIterator[MemoryRecord]``.
            Structural typing -- no Protocol base class required (D-08).
        user_id: The user whose live records to score. Hard-scoped: passed
            directly to ``live_records`` so the store enforces user isolation.
        now: Reference "current" time for age computation. Defaults to
            ``datetime.now(timezone.utc)``.  Pass an explicit value in tests.

    Yields:
        ``(record, score)`` pairs where ``score = keep_score(record, now)`` and
        ``record.protected is False``. Protected records are silently skipped.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    async for record in record_store.live_records(user_id):
        if record.protected:
            continue  # FORG-03: skip protected records -- do NOT yield them
        yield (record, keep_score(record, now))
