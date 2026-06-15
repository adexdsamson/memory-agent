"""MNEMA evaluation baseline — naive vs MNEMA recall comparison (EVAL-02).

Implements the before/after evaluation comparing:
  - Naive strategy: concatenate ALL T0 turns for the user into one string.
  - MNEMA strategy: recall(query=probe_query, budget=EVAL_BUDGET).

Metrics (D5-06):
  (a) Protected-fact retention — allergy honored after a long history.
  (b) Superseded-fact avoidance — no stale diet preference in context.
  (c) Cross-session recall accuracy — planted constraint recalled correctly.
  (d) Context tokens used — MNEMA budgeted vs naive full-transcript count.

Scoring is containment-based and deterministic (D5-07) — no LLM grading.
Output EVAL.md reports our own numbers + methodology (D5-08).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Probe:
    """A single evaluation probe: a query + expected containment constraints.

    Attributes:
        query: The recall query to issue against both naive and MNEMA strategies.
        must_contain: Phrases that MUST appear (case-insensitive) in the context.
        must_not_contain: Phrases that must NOT appear (case-insensitive) in context.
        req_id: The requirement ID this probe validates (e.g. "DEMO-04-protection").
    """

    query: str
    must_contain: list[str]
    must_not_contain: list[str]
    req_id: str = field(default="")


def containment_check(
    context: str,
    must_contain: list[str],
    must_not_contain: list[str],
) -> bool:
    """Deterministic containment scorer (D5-07).

    Checks that all must_contain phrases appear case-insensitively AND all
    must_not_contain phrases are absent. Score is binary — no partial credit.

    Args:
        context: The assembled context string to evaluate.
        must_contain: All of these phrases must appear in context.
        must_not_contain: None of these phrases may appear in context.

    Returns:
        True if all must_contain phrases are found AND all must_not_contain
        phrases are absent; False otherwise.
    """
    ctx_lower = context.lower()
    contained = all(phrase.lower() in ctx_lower for phrase in must_contain)
    excluded = all(phrase.lower() not in ctx_lower for phrase in must_not_contain)
    return contained and excluded


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVAL_BUDGET: int = 300
"""Token budget for MNEMA recall in the eval harness (D5-05)."""

# ---------------------------------------------------------------------------
# Probe suite — populated in Wave 3
# ---------------------------------------------------------------------------

PROBES: list[Probe] = []
"""Scripted probe suite covering DEMO-02..04 requirements.

Populated in Wave 3 once the scenario fixtures are written. Empty in Wave 0 so
this module is importable from RED test stubs without raising at collection time.
"""

# ---------------------------------------------------------------------------
# Eval stubs — implemented in Wave 3
# ---------------------------------------------------------------------------


async def run_eval(data_dir: Path) -> dict[str, object]:
    """Run the full before/after evaluation over seeded data.

    Seeds deterministic data, runs each probe against both naive and MNEMA
    strategies, collects containment scores and token counts, and returns
    a results dict.

    Args:
        data_dir: Directory containing the persistent SQLite + LocalFS store
            populated by the scenario fixtures.

    Returns:
        A dict with keys:
          - "probes_passed_mnema": int — number of probes passed by MNEMA.
          - "probes_passed_naive": int — number of probes passed by naive strategy.
          - "token_reduction_pct": float — percentage reduction in tokens vs naive.
          - "probe_details": list[dict] — per-probe breakdown.

    Raises:
        NotImplementedError: Until Wave 3 implements this function.
    """
    raise NotImplementedError("implement in Wave 3")


async def write_eval_report(
    results: dict[str, object],
    output_path: Path,
    *,
    suite_description: Optional[str] = None,
) -> None:
    """Write an EVAL.md report from eval results (D5-08).

    Formats the results dict into a Markdown report with methodology section
    and writes it to output_path.

    Args:
        results: The dict returned by run_eval().
        output_path: Path where EVAL.md should be written.
        suite_description: Optional one-paragraph methodology description.
            Defaults to a standard description if not provided.

    Raises:
        NotImplementedError: Until Wave 3 implements this function.
    """
    raise NotImplementedError("implement in Wave 3")
