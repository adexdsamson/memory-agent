"""Phase 5 evaluation baseline test — EVAL-02.

GREEN implementation: verifies MNEMA passes all 3 containment probes, the naive
baseline fails the superseded-fact avoidance probe (sees the preference content
more than once), and MNEMA uses fewer context tokens than the naive full-transcript.

Also writes EVAL.md to the project root as the Phase 5 deliverable.

Requirement covered:
  EVAL-02 — Before/after baseline: naive full-transcript vs MNEMA recall(budget)
            on scripted probe suite; output EVAL.md.
"""

from __future__ import annotations

from pathlib import Path


async def test_eval_baseline_comparison(tmp_path: Path) -> None:
    """EVAL-02: MNEMA passes all probes; naive baseline fails supersession probe.

    Sequence:
      1. Creates a fresh data dir under tmp_path.
      2. Calls baseline.run_eval(data_dir) which seeds deterministic data and
         runs each probe against both the naive full-transcript and MNEMA strategies.
      3. Asserts structure: required keys are present.
      4. Asserts MNEMA correctness: passes all 3 containment probes.
      5. Asserts naive limitation: fails the supersession avoidance probe
         (sees the preference content duplicated in the full transcript).
      6. Asserts token efficiency: MNEMA uses fewer context tokens than naive.
      7. Writes the eval report to a temp path and asserts content.
      8. Writes the eval report to the project root (EVAL.md — the deliverable).
    """
    from mnema.eval.baseline import run_eval, write_eval_report  # noqa: PLC0415

    data_dir = tmp_path / "eval_data"
    data_dir.mkdir()

    results = await run_eval(data_dir)

    # --- Structure assertions ---
    assert "probes_passed_mnema" in results
    assert "probes_passed_naive" in results
    assert "avg_mnema_tokens" in results
    assert "avg_naive_tokens" in results
    assert "token_reduction_pct" in results
    assert "probe_results" in results

    # --- MNEMA correctness: must pass ALL 3 probes ---
    assert results["probes_passed_mnema"] == 3, (
        f"MNEMA must pass all 3 probes, got {results['probes_passed_mnema']}. "
        f"Per-probe breakdown: {results['probe_results']}"
    )

    # --- Naive limitation: must fail the supersession avoidance probe ---
    # Naive baseline includes ALL T0 turns, so the diet preference content appears
    # more than once (both the original remember() and the superseding remember()
    # are stored as T0 turns). MNEMA's live-record filter returns only the current
    # record, so the content appears exactly once.
    assert results["probes_passed_naive"] <= 2, (
        f"Naive baseline must fail the supersession avoidance probe "
        f"(content duplicated in full transcript), but got "
        f"{results['probes_passed_naive']} probes passed. "
        f"Per-probe breakdown: {results['probe_results']}"
    )

    # --- Token efficiency: MNEMA must use fewer tokens than naive ---
    assert results["avg_mnema_tokens"] < results["avg_naive_tokens"], (
        f"MNEMA must use fewer context tokens than naive full-transcript stuffing. "
        f"MNEMA avg: {results['avg_mnema_tokens']:.1f}, "
        f"Naive avg: {results['avg_naive_tokens']:.1f}"
    )

    # --- Report: write to tmp path and validate content ---
    eval_tmp_path = tmp_path / "EVAL.md"
    await write_eval_report(results, eval_tmp_path)
    assert eval_tmp_path.exists(), "EVAL.md was not created at the tmp path"
    content = eval_tmp_path.read_text(encoding="utf-8")
    assert "MNEMA" in content, "EVAL.md must contain 'MNEMA'"
    assert "Naive" in content, "EVAL.md must contain 'Naive'"
    assert "Methodology" in content, "EVAL.md must contain 'Methodology' section"
    assert "PASS" in content or "FAIL" in content, "EVAL.md must contain probe results"

    # --- Deliverable: write EVAL.md to the project root ---
    project_root_eval = Path(__file__).parent.parent / "EVAL.md"
    await write_eval_report(results, project_root_eval)
    assert project_root_eval.exists(), "EVAL.md was not written to project root"
