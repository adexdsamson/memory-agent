"""Phase 5 evaluation baseline test stub — EVAL-02.

RED stub to be implemented in Wave 3. Collects cleanly so Wave 3 can drive
implementation against a concrete test file.

Requirement covered:
  EVAL-02 — Before/after baseline: naive full-transcript vs MNEMA recall(budget)
            on scripted probe suite; output EVAL.md.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(strict=False, reason="RED stub — implement in Wave 3")
async def test_eval_baseline_comparison(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """EVAL-02: MNEMA passes all probes; naive baseline comparison produces valid report.

    Sequence:
      1. Seeds deterministic data (allergy, superseded diet, cross-session constraint).
      2. Calls baseline.run_eval(tmp_path).
      3. Asserts the returned dict has the required keys.
      4. Asserts MNEMA passes more probes than naive on the superseded-avoidance probe.

    Deferred imports keep collection clean even before run_eval is implemented.
    """
    from mnema.eval.baseline import run_eval  # noqa: PLC0415

    result = await run_eval(tmp_path)
    assert "probes_passed_mnema" in result
    assert "probes_passed_naive" in result
    assert "token_reduction_pct" in result
