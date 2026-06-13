"""Phase 2 consolidation tests — CONS-01 through CONS-08.

All tests in this module are RED stubs for the walking-skeleton wave.  They use
the ``engine_with_llm`` fixture (StubEmbedder + StubLLM + SqliteT1 + LocalFS) and
will fail with NotImplementedError until the consolidation pipeline is wired in
Plans 02 through 04.

Each test maps directly to a Phase 2 requirement in the CONS series:
  CONS-01  staging queue is drained and typed records are extracted
  CONS-02  safety/medical content is pinned protected=True + salience=1.0
  CONS-03  entity resolution finds a candidate match by dense cosine
  CONS-04  contradicting match supersedes the old record atomically
  CONS-05  non-contradicting refinement merges into the existing record
  CONS-06  provisional record is upgraded in place by t0_ref reconciliation
  CONS-07  running consolidate() twice produces an identical live set (idempotent)
  CONS-08  protected/FACT records are NEVER auto-superseded by an LLM contradiction
"""

from __future__ import annotations

import pytest


class TestConsolidation:
    async def test_staging_queue_drained(self, engine_with_llm) -> None:
        """CONS-01: consolidate() drains the staging queue and extracts typed records."""
        # RED: will raise until consolidation pipeline is wired
        raise NotImplementedError("CONS-01 not implemented")

    async def test_safety_content_pinned_protected(self, engine_with_llm) -> None:
        """CONS-02: safety/medical content -> protected=True + salience=1.0 (content rule, not LLM)."""
        raise NotImplementedError("CONS-02 not implemented")

    async def test_entity_resolution_finds_match(self, engine_with_llm) -> None:
        """CONS-03: entity resolution matches same-subject near records by dense cosine."""
        raise NotImplementedError("CONS-03 not implemented")

    async def test_contradiction_supersession_atomic(self, engine_with_llm) -> None:
        """CONS-04: contradicting match -> old record superseded atomically (valid_until + superseded_by + edge)."""
        raise NotImplementedError("CONS-04 not implemented")

    async def test_refinement_merges_in_place(self, engine_with_llm) -> None:
        """CONS-05: non-contradicting refinement merges into existing record (no new live record)."""
        raise NotImplementedError("CONS-05 not implemented")

    async def test_provisional_reconciled_in_place(self, engine_with_llm) -> None:
        """CONS-06: provisional record upgraded in place by t0_ref; provisional flag cleared."""
        raise NotImplementedError("CONS-06 not implemented")

    async def test_idempotent_rerun(self, engine_with_llm) -> None:
        """CONS-07: running consolidate() twice produces identical live set -- no duplicates."""
        raise NotImplementedError("CONS-07 not implemented")

    async def test_cons08_protected_never_superseded(self, engine_with_llm) -> None:
        """CONS-08: protected/FACT records NEVER auto-superseded by LLM contradiction alone.

        Safety-critical seeded contradiction test -- a protected record must survive.
        """
        raise NotImplementedError("CONS-08 not implemented")
