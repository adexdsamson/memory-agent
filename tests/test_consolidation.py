"""Phase 2 consolidation tests — CONS-01 through CONS-08.

All tests use the ``engine_with_llm`` fixture (StubEmbedder + StubLLM + SqliteT1 +
LocalFS) and call the pipeline end-to-end via engine.consolidate().

Design notes:
  - Content strings for entity-resolution tests (CONS-03/04/05/08) are deliberately
    chosen so that ``sha256(content + newline + content) % 3`` returns the target
    verdict.  This ensures that when the same content is remembered a second time
    (giving vector distance 0 to the existing record), the contradiction judge fires
    deterministically.
  - Content strings for entity-resolution tests must NOT trigger the first-person-
    stative classifier or the safety-keyword detector, so the second remember() call
    does NOT create a provisional record.  If a provisional were created, Step 4 of
    the pipeline (find_by_t0_ref reconciliation) would short-circuit before entity
    resolution fires.
  - Safety-claim tests (CONS-02, CONS-08) use real safety keywords so the content-rule
    gate in the pipeline applies correctly.

Verdicts precomputed via sha256(f'{c}\\n{c}').hexdigest() % 3:
  'spicy food preference item 1'  -> 1 (refine)      -- CONS-03, CONS-05
  'spicy food preference item 0'  -> 2 (contradict)  -- CONS-04
  'I am allergic to shellfish'    -> 2 (contradict)  -- CONS-08 safety sub-test
  'protected food fact item 0'    -> 2 (contradict)  -- CONS-08 gate sub-test
"""

from __future__ import annotations

import hashlib

# ---------------------------------------------------------------------------
# Module-level verdict helpers
# ---------------------------------------------------------------------------

def _verdict_for_pair(existing_content: str, new_content: str) -> str:
    """Return the deterministic verdict StubLLM produces for this (existing, new) pair.

    Mirrors StubLLM._judge: sha256(body.strip()) % 3 -> ['distinct','refine','contradict'].
    """
    body = f"{existing_content}\n{new_content}"
    h = int(hashlib.sha256(body.encode()).hexdigest(), 16) % 3
    return ["distinct", "refine", "contradict"][h]


def _find_new_content_for_verdict(
    existing_content: str, target: str, prefix: str = "seed"
) -> str:
    """Iterate candidate suffixes until StubLLM would return ``target`` verdict.

    Deterministic for any fixed (existing, target) pair.
    """
    for i in range(1000):
        candidate = f"{prefix}_{i}_{existing_content[:20]}"
        if _verdict_for_pair(existing_content, candidate) == target:
            return candidate
    raise RuntimeError(
        f"Could not find content for verdict {target!r} with existing={existing_content!r}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConsolidation:
    async def test_staging_queue_drained(self, engine_with_llm) -> None:
        """CONS-01: consolidate() drains the staging queue and extracts typed records.

        Uses a first-person preference claim so the classifier writes a provisional
        T1 record, and consolidate() upgrades it to confirmed (provisional=False).
        """
        user_id = "cons01_user"
        await engine_with_llm.remember(
            "I prefer vegetarian food",
            user_id=user_id,
            session_id="s1",
        )
        await engine_with_llm.consolidate()

        records = await engine_with_llm.t1.get_live_records(user_id)
        assert len(records) >= 1, "Expected at least one live record after consolidation"
        assert all(not r.provisional for r in records), (
            "Expected all records to be non-provisional after consolidation"
        )

    async def test_safety_content_pinned_protected(self, engine_with_llm) -> None:
        """CONS-02: safety/medical content -> protected=True + salience=1.0.

        type_hint='preference' is deliberately passed to prove the CONTENT rule
        overrides the caller hint — protection is content-driven, not hint-driven.
        """
        user_id = "cons02_user"
        await engine_with_llm.remember(
            "I am allergic to peanuts",
            user_id=user_id,
            session_id="s1",
            type_hint="preference",
        )
        await engine_with_llm.consolidate()

        records = await engine_with_llm.t1.get_live_records(user_id)
        assert len(records) >= 1, "Expected at least one live record"
        protected_records = [r for r in records if r.protected]
        assert len(protected_records) >= 1, (
            "CONS-02: safety content must produce a protected record"
        )
        for r in protected_records:
            assert r.salience == 1.0, (
                f"CONS-02: protected record must have salience=1.0, got {r.salience}"
            )

    async def test_entity_resolution_finds_match(self, engine_with_llm) -> None:
        """CONS-03: entity resolution finds a near match and merges via 'refine' verdict.

        Content 'spicy food preference item 1' is chosen because:
          sha256('spicy food preference item 1\\nspicy food preference item 1') % 3 == 1 (refine)
        It does NOT match _FIRST_PERSON_STATIVE, so no provisional is written.
        The second remember() of the same content produces vector distance 0 -> entity
        resolution finds the existing record -> judge returns 'refine' -> merged in place.
        """
        user_id = "cons03_user"
        content = "spicy food preference item 1"

        # Sanity check: same-content verdict is 'refine'
        assert _verdict_for_pair(content, content) == "refine", (
            f"Test invariant broken: expected 'refine' for same-content pair of {content!r}"
        )

        # First pass: no provisional (not first-person stative), consolidate inserts confirmed R1
        await engine_with_llm.remember(content, user_id=user_id, session_id="s1")
        await engine_with_llm.consolidate()

        records_after_first = await engine_with_llm.t1.get_live_records(user_id)
        assert len(records_after_first) == 1, (
            f"Expected 1 live record after first consolidation, got {len(records_after_first)}"
        )

        # Second pass: same content, same vector (dist=0) -> entity resolution fires
        await engine_with_llm.remember(content, user_id=user_id, session_id="s2")
        await engine_with_llm.consolidate()

        records_after_second = await engine_with_llm.t1.get_live_records(user_id)
        assert len(records_after_second) == 1, (
            f"CONS-03: expected 1 live record after refine (no duplicate), "
            f"got {len(records_after_second)}"
        )

    async def test_contradiction_supersession_atomic(self, engine_with_llm) -> None:
        """CONS-04: contradicting match supersedes old record atomically.

        Content 'spicy food preference item 0' is chosen because:
          sha256('spicy food preference item 0\\nspicy food preference item 0') % 3
          == 2 (contradict)
        It does NOT match _FIRST_PERSON_STATIVE, so no provisional is written.
        The second remember() of the same content -> entity resolution finds R1 ->
        judge returns 'contradict' -> R1 superseded (valid_until set), R2 inserted
        with supersedes edge.
        """
        user_id = "cons04_user"
        content = "spicy food preference item 0"

        # Sanity check: same-content verdict is 'contradict'
        assert _verdict_for_pair(content, content) == "contradict", (
            f"Test invariant broken: expected 'contradict' for same-content pair of {content!r}"
        )

        # First pass: insert confirmed R1
        await engine_with_llm.remember(content, user_id=user_id, session_id="s1")
        await engine_with_llm.consolidate()

        records_after_first = await engine_with_llm.t1.get_live_records(user_id)
        assert len(records_after_first) == 1, "Expected 1 live record after first consolidation"
        r1_id = records_after_first[0].id

        # Verify R1 is not protected (so supersession is allowed)
        assert not records_after_first[0].protected, (
            "R1 must not be protected for CONS-04 supersession test"
        )

        # Second pass: same content, same vector (dist=0) -> entity resolution fires
        await engine_with_llm.remember(content, user_id=user_id, session_id="s2")
        await engine_with_llm.consolidate()

        # Exactly one live record (R2, the new one)
        live_records = await engine_with_llm.t1.get_live_records(user_id)
        assert len(live_records) == 1, (
            f"CONS-04: expected 1 live record after supersession, got {len(live_records)}"
        )

        # Old record R1 must have valid_until set (superseded)
        r1_refreshed = await engine_with_llm.t1.get(r1_id)
        assert r1_refreshed is not None, "R1 should still exist (not deleted)"
        assert r1_refreshed.valid_until is not None, (
            "CONS-04: old record must have valid_until set after supersession"
        )

        # New live record R2 is the winner
        r2 = live_records[0]
        assert r2.superseded_by is None, (
            "CONS-04: the new live record should not have superseded_by set"
        )
        assert r2.id != r1_id, "R2 must be a different record than R1"

        # R2 must carry a 'supersedes' edge
        supersedes_edges = [e for e in r2.graph_edges if e.get("rel") == "supersedes"]
        assert len(supersedes_edges) >= 1, (
            "CONS-04: new record must have a 'supersedes' graph edge"
        )

    async def test_refinement_merges_in_place(self, engine_with_llm) -> None:
        """CONS-05: non-contradicting refinement merges into existing record (no new live record).

        Content 'spicy food preference item 1' is chosen because same-content verdict is 'refine'.
        Different user_id from CONS-03 so no cross-test interference.
        """
        user_id = "cons05_user"
        content = "spicy food preference item 1"

        assert _verdict_for_pair(content, content) == "refine"

        # First pass: insert confirmed R1
        await engine_with_llm.remember(content, user_id=user_id, session_id="s1")
        await engine_with_llm.consolidate()

        records_first = await engine_with_llm.t1.get_live_records(user_id)
        assert len(records_first) == 1
        r1_id = records_first[0].id

        # Second pass: same content -> entity resolution finds R1 -> refine -> merge
        await engine_with_llm.remember(content, user_id=user_id, session_id="s2")
        await engine_with_llm.consolidate()

        records_second = await engine_with_llm.t1.get_live_records(user_id)
        assert len(records_second) == 1, (
            "CONS-05: refinement must not create a new record; "
            f"expected 1, got {len(records_second)}"
        )
        # The surviving record should be R1 (same id, merged in place)
        assert records_second[0].id == r1_id, (
            "CONS-05: refinement must keep the existing record id (merged in place)"
        )

    async def test_provisional_reconciled_in_place(self, engine_with_llm) -> None:
        """CONS-06: provisional record upgraded in place by t0_ref — no duplicate.

        Uses durable=True to force a provisional T1 write on the fast path.
        After consolidation the provisional flag is cleared; no new record is created.
        """
        user_id = "cons06_user"
        await engine_with_llm.remember(
            "I eat gluten free",
            user_id=user_id,
            session_id="s1",
            durable=True,
        )

        records_before = await engine_with_llm.t1.get_live_records(user_id)
        assert len(records_before) >= 1, "Expected a provisional record before consolidation"
        assert any(r.provisional for r in records_before), (
            "CONS-06: should have at least one provisional record before consolidate()"
        )

        await engine_with_llm.consolidate()

        records_after = await engine_with_llm.t1.get_live_records(user_id)
        assert all(not r.provisional for r in records_after), (
            "CONS-06: all records should be non-provisional after consolidate()"
        )
        assert len(records_after) == len(records_before), (
            f"CONS-06: no duplicate records — expected {len(records_before)}, "
            f"got {len(records_after)}"
        )

    async def test_idempotent_rerun(self, engine_with_llm) -> None:
        """CONS-07: running consolidate() twice produces the same set of live records.

        The second consolidate() runs on an empty staging queue (all items drained
        in the first run) and must be a no-op — no duplicate records inserted.
        """
        user_id = "cons07_user"
        await engine_with_llm.remember(
            "I am vegan",
            user_id=user_id,
            session_id="s1",
            durable=True,
        )
        await engine_with_llm.consolidate()

        ids_first = {r.id for r in await engine_with_llm.t1.get_live_records(user_id)}
        assert len(ids_first) >= 1, "Expected at least one live record after first consolidation"

        # Second consolidate() on empty queue — must be idempotent
        await engine_with_llm.consolidate()

        ids_second = {r.id for r in await engine_with_llm.t1.get_live_records(user_id)}
        assert ids_first == ids_second, (
            f"CONS-07: idempotent rerun must produce same live record set; "
            f"first={ids_first}, second={ids_second}"
        )

    async def test_cons08_protected_never_superseded(self, engine_with_llm) -> None:
        """CONS-08: protected/FACT records NEVER auto-superseded by LLM contradiction alone.

        Safety-critical seeded contradiction test.  Two sub-tests:

        (a) Safety-claim path: remember a real allergy -> consolidate() pins protected=True.

        (b) CONS-08 gate path: use content 'protected food fact item 0' which:
            - Is NOT a safety keyword (no provisional written on second remember)
            - Same-content verdict = 'contradict' (sha256 % 3 == 2)
            The record is manually set protected=True after first consolidation to
            simulate a prior safety upgrade.  The second remember() of the same content
            with durable=False (no provisional) flows through entity resolution:
            dist=0 -> match found -> judge='contradict' -> CONS-08 gate fires ->
            contradiction_pending edge added, record remains live with valid_until=None.
        """
        user_id = "cons08_user"

        # --- Sub-test (a): safety claim pinned protected after consolidation ---
        await engine_with_llm.remember(
            "I am allergic to shellfish",
            user_id=user_id,
            session_id="s1",
        )
        await engine_with_llm.consolidate()

        all_live = await engine_with_llm.t1.get_live_records(user_id)
        safety_protected = [r for r in all_live if r.protected]
        assert len(safety_protected) >= 1, (
            "CONS-08 sub-test (a): safety claim must yield a protected record after consolidation"
        )

        # --- Sub-test (b): CONS-08 structural gate via seeded contradiction ---
        # Content chosen: NOT first-person stative, NOT safety keyword, same-content='contradict'
        protected_content = "protected food fact item 0"
        assert _verdict_for_pair(protected_content, protected_content) == "contradict", (
            f"Test invariant broken: expected 'contradict' for {protected_content!r}"
        )

        # First pass: remember + consolidate -> inserts a new confirmed record R_prot
        # (no provisional: not first-person stative AND not safety)
        await engine_with_llm.remember(
            protected_content,
            user_id=user_id,
            session_id="s2",
        )
        await engine_with_llm.consolidate()

        # Locate the just-inserted record
        live_after_setup = await engine_with_llm.t1.get_live_records(user_id)
        r_prot_candidates = [r for r in live_after_setup if r.content == protected_content]
        assert len(r_prot_candidates) == 1, (
            f"Expected 1 record with content={protected_content!r}, "
            f"got {len(r_prot_candidates)}"
        )
        r_prot = r_prot_candidates[0]
        r_prot_id = r_prot.id

        # Manually pin protected=True to simulate a safety-upgrade (CONS-08 gate test)
        await engine_with_llm.t1.update(r_prot_id, protected=True, salience=1.0)

        # Verify the pin took effect
        r_prot_refreshed = await engine_with_llm.t1.get(r_prot_id)
        assert r_prot_refreshed is not None
        assert r_prot_refreshed.protected is True, "Manual protected pin must take effect"

        # Second pass: same content, durable=False -> NO provisional written
        # (not safety, not first-person stative) -> entity resolution fires
        await engine_with_llm.remember(
            protected_content,
            user_id=user_id,
            session_id="s3",
        )
        await engine_with_llm.consolidate()

        # --- CONS-08 assertions ---
        final_live = await engine_with_llm.t1.get_live_records(user_id)

        # The protected record must still be live
        assert any(r.id == r_prot_id for r in final_live), (
            "CONS-08 VIOLATION: protected record was superseded by LLM contradiction"
        )

        # The protected record must have a contradiction_pending edge (audit trail)
        surviving = next(r for r in final_live if r.id == r_prot_id)
        contradiction_edges = [
            e for e in surviving.graph_edges if e.get("rel") == "contradiction_pending"
        ]
        assert len(contradiction_edges) >= 1, (
            "CONS-08: contradiction_pending edge must be recorded on the protected record"
        )

        # The protected record's valid_until must still be None (not superseded)
        assert surviving.valid_until is None, (
            "CONS-08: protected record must not have valid_until set (not superseded)"
        )
