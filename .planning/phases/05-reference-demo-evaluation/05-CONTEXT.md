# Phase 5: Reference Demo & Evaluation - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning
**Mode:** Smart-discuss (autonomous) — all three grey areas **Accepted as recommended**. Locked for planning; the success criteria are about MEMORY behavior (not LLM eloquence), so everything is proven deterministically.

<domain>
## Phase Boundary

The final milestone phase: an **interactive nutrition-coach demo** that proves the engine end-to-end through the SDK alone, and a **before/after evaluation** quantifying MNEMA against naive transcript-stuffing on the same scripted suite. Consumes the now-complete engine (Phases 1–4) via `build_engine()` + the five verbs — adds NO new engine capability.

**Out of scope:** new engine features; hybrid retrieval (Phase-later); a real nutrition database; production UX; cloud-LLM-graded answers (the demo + eval are deterministic/hermetic by default).
</domain>

<decisions>
## Implementation Decisions

### Area 1 — Demo form factor & LLM (DEMO-01…05) [Accepted]
- **D5-01:** A **CLI interactive chat + meal-planning loop** (`python -m mnema.demo.coach`) built on `build_engine(LocalConfig)`.
- **D5-02:** **StubLLM by default** — hermetic, deterministic, zero credentials. Real Qwen/Claude is opt-in via config/env. The four memory behaviors do not depend on LLM quality.
- **D5-03:** DEMO-02…05 are each a **deterministic automated pytest scenario** (scripted session) AND reproducible via the loop:
  - DEMO-02 cross-session recall: a constraint stated in session 1 is respected in session 2 (separate engine open over a persistent store).
  - DEMO-03 supersession: a diet change retires the old record and **surfaces `valid_until`/`superseded_by`** (assert the mechanism, not just chat output) — via `forget()` + consolidation.
  - DEMO-04 decay + protected: a seeded **backdated transient** is evicted then recovered from cold storage, while a **pinned allergy survives** the decay pass untouched.
  - DEMO-05 budget packing: a large history is packed under a token budget with **one verbatim `expand()`** on demand.
- **D5-04:** Meal planning is a **deterministic, constraint-respecting suggestion** (consumes recalled constraints/allergies) — proves the engine, not a nutrition DB.

### Area 2 — Eval harness & metrics (EVAL-02) [Accepted]
- **D5-05:** Compare **naive "stuff the whole T0 transcript" vs MNEMA `recall(budget=…)`** on the same scripted probe suite.
- **D5-06:** Metrics: (a) **protected-fact retention** (allergy honored after a long history), (b) **superseded-fact avoidance** (no stale diet), (c) **cross-session recall accuracy** on planted probes, (d) **context tokens used** (MNEMA budgeted vs full transcript).
- **D5-07:** **Containment-based deterministic scoring** — does the packed/assembled context contain the right (current) fact, exclude the stale one, and fit under budget? No LLM-answer grading (deterministic with StubLLM).
- **D5-08:** Output an **`EVAL.md`/report with our own numbers + methodology** — no competitor claims, just "MNEMA vs naive baseline on this suite."

### Area 3 — Packaging & scope [Accepted]
- **D5-09:** Code in **`src/mnema/demo/coach.py`** + **`src/mnema/eval/baseline.py`** (+ tests under `tests/`).
- **D5-10:** Demo uses a **fixed local sqlite + LocalFS data dir** (not `:memory:`) so an early session persists into a later session (DEMO-02 cross-session).
- **D5-11:** **MVP-proof** polish — clear, scripted, reproducible behaviors + eval numbers; not a polished product.

### Carried-forward locked decisions
- Uses `build_engine(LocalConfig)` (Phase 4 factory) + the five async verbs + `ScopedHandle`. The protected-fact + supersession + budget guarantees are exactly what the demo showcases (the project Core Value). pyright strict; pytest-asyncio; ruff; `uv run --extra dev`.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/mnema/config.py::build_engine(LocalConfig())` — the demo's entry point (wires SqliteT1 + LocalFS + LocalFSVault + InProcessScheduler + StubEmbedder + StubLLM; registers the consolidation job).
- `MemoryEngine` verbs: `remember`, `recall(query, *, user_id, budget=None)`, `forget`, `consolidate(user_id=None)`, `expand(record_id, *, user_id)`; `scope(user_id)` → ScopedHandle.
- Eviction/decay: `engine.evict(user_id)` / consolidation eviction pass; cold-store recovery via the archive + `expand`.
- `src/mnema/core/packer.py` — token counting (TiktokenCounter / ByteLengthCounter) for the eval's token metric.
- `LocalConfig(sqlite_path=..., local_fs_path=..., vault_path=...)` — set a fixed dir for cross-session persistence (D5-10).

### Established Patterns
- pytest-asyncio (`asyncio_mode=auto`), hermetic StubLLM/StubEmbedder, `uv run --extra dev pytest`, pyright strict, ruff line-length 100. No new runtime deps expected (tiktoken already in via Phase 3).

### Integration Points
- Demo + eval are pure SDK consumers — they import `mnema.config.build_engine` and the engine verbs; no engine internals.
- A persistent data dir means tests must use a tmp dir / clean up to stay hermetic; the two-session demo opens two engines over the same store.

### Open code-review carryover
- Phase 1–4 deferred todos exist; none blocks Phase 5.
</code_context>

<specifics>
## Specific Ideas
- The demo IS the Core-Value proof: "never forgets a protected fact (allergy), never acts on a superseded one (old diet), recalls within a token budget." Each DEMO-0x maps directly to one of those guarantees — make that mapping explicit in the demo output + tests.
- The eval must report **our own numbers honestly** (methodology stated; deterministic; reproducible) — it is a before/after vs the naive baseline, not a benchmark against other products.
</specifics>

<deferred>
## Deferred Ideas
- Real-LLM coach + LLM-graded answers (needs creds; opt-in only).
- Web/GUI demo; real nutrition database; multi-user demo.
- Hybrid retrieval / extra providers (separate later phase).
</deferred>
