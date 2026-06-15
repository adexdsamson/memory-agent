"""Phase 5 demo scenario test stubs — DEMO-01 through DEMO-05.

All tests are RED stubs (xfail) to be implemented in Wave 1/2. They collect cleanly
so Wave 1 can drive implementation against a concrete test file.

Requirements covered:
  DEMO-01 — Interactive nutrition-coach CLI runs on build_engine(LocalConfig)
  DEMO-02 — Cross-session recall: constraint from session 1 honored in session 2
  DEMO-03 — Supersession: diet change sets valid_until + superseded_by on old record
  DEMO-04 — Decay + protected: backdated transient evicted; allergy survives; expand() recovers
  DEMO-05 — Budget packing: large history packed under token budget; verbatim expand()
"""

from __future__ import annotations

import pytest

from mnema.config import LocalConfig, build_engine

# NOTE: Engine internals (SqliteT1, InProcessScheduler, etc.) are deferred into test
# bodies and fixture bodies to avoid ImportError at collection time (RED phase).


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def persistent_engine_factory(tmp_path):  # type: ignore[return]
    """Factory that builds a MemoryEngine over fixed persistent paths.

    Yields a (make_engine, close_engine) tuple:
      - make_engine() -> MemoryEngine: opens (or reopens) the engine over the
        same sqlite_path + local_fs_path + vault_path in tmp_path. Each call
        returns a fresh engine instance over the SAME files.
      - close_engine(eng): flushes the WAL via eng.t1.close() then shuts down
        the scheduler — safe to call between sessions in DEMO-02 cross-session test.

    Uses tmp_path (unique per test) to prevent cross-test data leakage (T-05-00-02).
    """
    data_dir = tmp_path / "mnema_data"
    data_dir.mkdir()
    cfg = LocalConfig(
        sqlite_path=str(data_dir / "mnema.db"),
        local_fs_path=str(data_dir / "t0"),
        vault_path=str(data_dir / "vault"),
    )

    async def make_engine():  # type: ignore[return]
        return await build_engine(cfg)

    async def close_engine(eng) -> None:  # type: ignore[no-untyped-def]
        # Use the public t1 property to flush WAL (T-05-00-01 mitigation).
        await eng.t1.close()
        await eng._scheduler.shutdown()

    yield make_engine, close_engine


# ---------------------------------------------------------------------------
# RED test stubs
# ---------------------------------------------------------------------------


async def test_coach_entrypoint(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """DEMO-01: Coach module imports and suggest_meal returns a string.

    Verifies that the coach entrypoint can be called on a freshly built engine
    and that suggest_meal(scope, query) returns a non-empty str.
    """
    from mnema.demo.coach import suggest_meal  # noqa: PLC0415

    cfg = LocalConfig(
        sqlite_path=str(tmp_path / "mnema.db"),
        local_fs_path=str(tmp_path / "t0"),
        vault_path=str(tmp_path / "vault"),
    )
    eng = await build_engine(cfg)
    scope = eng.scope(user_id="coach_user")
    await scope.remember("I am allergic to peanuts", session_id="s1")
    await eng.consolidate()
    result = await suggest_meal(scope, "what can I eat for lunch")
    assert isinstance(result, str)
    assert len(result) > 0
    await eng.t1.close()
    await eng._scheduler.shutdown()


@pytest.mark.xfail(strict=False, reason="RED stub — implement in Wave 1")
async def test_cross_session_recall(persistent_engine_factory) -> None:  # type: ignore[no-untyped-def]
    """DEMO-02: Constraint from session 1 is recalled in session 2.

    Opens engine1, remembers a peanut allergy, consolidates (flushes staging
    queue to confirmed T1), closes engine1 (WAL checkpoint). Opens engine2 over
    the same file paths and asserts "peanut" appears in a food-allergy recall.
    """
    make_engine, close_engine = persistent_engine_factory

    # Session 1
    eng1 = await make_engine()
    scope1 = eng1.scope(user_id="demo_user")
    await scope1.remember("I am allergic to peanuts", session_id="s1")
    await eng1.consolidate()
    await close_engine(eng1)

    # Session 2 — same SQLite file + LocalFS, new engine instance
    eng2 = await make_engine()
    scope2 = eng2.scope(user_id="demo_user")
    results = await scope2.recall("food allergies", budget=500)
    assert any("peanut" in r.content for r in results)
    await close_engine(eng2)


@pytest.mark.xfail(strict=False, reason="RED stub — implement in Wave 1/2")
async def test_supersession_surfaces_fields(persistent_engine_factory) -> None:  # type: ignore[no-untyped-def]
    """DEMO-03: Diet change retires old record with valid_until + superseded_by.

    Uses 'spicy food preference item 0' — a pre-verified content string whose
    self-pair SHA256 verdict is 'contradict' (index 2), ensuring the StubLLM
    judges the second remember() as a contradiction.

    Asserts that after the second consolidation:
      - The first record has valid_until IS NOT None.
      - The first record has superseded_by IS NOT None.
    """
    make_engine, close_engine = persistent_engine_factory
    eng = await make_engine()
    scope = eng.scope(user_id="demo_user")

    # First remember + consolidate: creates confirmed T1 record
    diet_content = "spicy food preference item 0"
    await scope.remember(diet_content, session_id="s1")
    await eng.consolidate()

    # Get the first record's id
    live = await eng.t1.get_live_records("demo_user")
    diet_records = [r for r in live if diet_content in r.content]
    assert len(diet_records) >= 1
    old_id = diet_records[0].id

    # Second remember with same content — deterministic contradict verdict
    await scope.remember(diet_content, session_id="s1")
    await eng.consolidate()

    # Old record must now have valid_until and superseded_by set
    old_record = await eng.t1.get(old_id)
    assert old_record is not None
    assert old_record.valid_until is not None, "old record should be retired"
    assert old_record.superseded_by is not None, "old record should point to successor"

    await close_engine(eng)


@pytest.mark.xfail(strict=False, reason="RED stub — implement in Wave 1/2")
async def test_decay_protected_and_recovery(persistent_engine_factory) -> None:  # type: ignore[no-untyped-def]
    """DEMO-04: Backdated transient evicted; pinned allergy survives; expand() recovers turn.

    Sequence:
      1. Seed allergy via remember() — safety keyword triggers protected=True.
      2. Seed kale transient via remember() + consolidate() to get valid t0_ref.
      3. Backdate the kale record via t1.update(created_at=past, last_accessed=past,
         salience=0.2) so its keep_score falls below KEEP_THRESHOLD=0.3.
      4. Run engine.evict() — transient evicted, allergy survives.
      5. Assert recalled allergy still contains "peanut".
      6. Assert kale not in live records.
      7. Assert expand(kale_id) returns non-None Turn with "kale" in content.
    """
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    make_engine, close_engine = persistent_engine_factory
    eng = await make_engine()
    scope = eng.scope(user_id="demo_user")

    # Seed allergy (safety keyword → protected=True after consolidation)
    await scope.remember("I am allergic to peanuts", session_id="s1")

    # Seed kale transient via remember() to get a valid t0_ref
    await scope.remember("I used to enjoy kale smoothies", session_id="s1")
    await eng.consolidate()  # flush both to T1

    # Find the kale record
    live = await eng.t1.get_live_records("demo_user")
    kale_records = [r for r in live if "kale" in r.content]
    assert len(kale_records) >= 1
    kale_id = kale_records[0].id

    # Backdate the kale record to 60 days ago with low salience
    past = datetime.now(timezone.utc) - timedelta(days=60)
    await eng.t1.update(kale_id, created_at=past, last_accessed=past, salience=0.2)

    # Evict — kale should be evicted (keep_score ≈ 0.08 < 0.3)
    evicted_count = await eng.evict(user_id="demo_user")
    assert evicted_count >= 1

    # Allergy survives eviction (protected=True)
    allergy_results = await scope.recall("allergy peanuts", budget=500)
    assert any("peanut" in r.content for r in allergy_results)

    # Kale is gone from live records
    live_after = await eng.t1.get_live_records("demo_user")
    assert not any("kale" in r.content for r in live_after)

    # Cold-store recovery via expand() reads the original T0 JSONL turn
    turn = await scope.expand(kale_id)
    assert turn is not None
    assert "kale" in turn.content

    await close_engine(eng)


@pytest.mark.xfail(strict=False, reason="RED stub — implement in Wave 1/2")
async def test_budget_packing_and_expand(persistent_engine_factory) -> None:  # type: ignore[no-untyped-def]
    """DEMO-05: Large history packed under token budget; verbatim expand() works.

    Seeds 20+ non-protected records + 1 protected allergy, then recalls with
    budget=300. Asserts:
      - Non-protected records' token sum fits within budget.
      - expand() on a seeded record returns the original Turn content.
    """
    from mnema.core.packer import TiktokenCounter  # noqa: PLC0415

    make_engine, close_engine = persistent_engine_factory
    eng = await make_engine()
    scope = eng.scope(user_id="demo_user")

    # Seed 20+ non-protected records
    for i in range(20):
        await scope.remember(f"meal fact {i}: I enjoy various foods item {i}", session_id="s1")

    # Seed a protected allergy (safety keyword detection)
    await scope.remember("I am allergic to peanuts", session_id="s1")
    await eng.consolidate()

    # Recall with budget=300
    budget = 300
    results = await scope.recall("meal history", budget=budget)
    assert len(results) > 0

    counter = TiktokenCounter()
    non_protected = [r for r in results if not r.protected]
    non_protected_tokens = sum(counter.count(r.summary or r.content[:80]) for r in non_protected)

    # Non-protected records must fit within the budget
    assert non_protected_tokens <= budget

    # Protected allergy must appear in results regardless of budget
    assert any(r.protected for r in results), "protected allergy must always be included"

    # Verbatim expand on first result with a t0_ref
    first_with_ref = next((r for r in results if r.t0_ref is not None), None)
    if first_with_ref is not None:
        turn = await scope.expand(first_with_ref.id)
        assert turn is not None

    await close_engine(eng)
