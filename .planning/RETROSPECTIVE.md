# MNEMA — Living Retrospective

## Milestone: v1.0 — Local-core memory engine + cloud backends + demo

**Shipped:** 2026-06-15
**Phases:** 5 | **Plans:** 28 | **Tasks:** 31

### What Was Built
A portable, provider-agnostic tiered memory engine for AI agents, proven end-to-end:
- T0 (raw episodic) / T1 (typed working memory) / T2 (canonical vault) + a recent-session buffer
- Fast online write (no LLM on the write path), offline consolidation + active supersession
- Deliberate, recoverable forgetting with a **Hypothesis-proven** protected-fact guarantee (a protected record can never be evicted, under any input)
- Budget-aware recall: relevance×salience×recency re-rank + a two-pass packer that reserves critical-fact slots
- Six swappable adapter axes (LLM / embedding / object-T0 / vector-T1 / vault-T2 / scheduler) with real cloud adapters (Qwen, Anthropic, Voyage, Alibaba OSS, Postgres+pgvector, cron) behind a shared conformance suite + a config-keyed factory
- MCP server + SDK; a nutrition-coach demo and a before/after eval (MNEMA 3/3 vs naive 2/3 probes, ~38% fewer context tokens)

### What Worked
- **Inside-out build order** (schema + un-retrofittable columns → ports → adapters → engine → cloud → demo): the un-retrofittable T1 schema decided in Phase 1 never needed a migration across 5 phases.
- **Walking-skeleton + RED-stub waves**: every phase opened with failing tests mapped 1:1 to success criteria; "GREEN-gate" final plans made completion unambiguous.
- **Conformance suite as the portability proof** (Phase 4): asserting the safety invariants on *every* backend caught Protocol drift by construction; the moto-S3 + sqlite-vec local backends keep the CI gate hermetic while cloud/Postgres are credential/Docker-gated.
- **Adversarial code-review + verify gates per phase** found real, load-bearing bugs that green tests missed: the content-driven `protected` flag (CR-04, Phase 1 — allergies weren't protected without an explicit hint), supersession atomicity + idempotency fence (Phase 2), eviction-without-cold-store = silent hard-delete (Phase 3), `migrate_embedder` wiping all users' vectors (Phase 4), and weak eval assertions that would pass with broken behavior (Phase 5).
- **Two safety invariants stayed load-bearing throughout**: content-driven `protected` + the CONS-08 structural supersession gate.

### What Was Inefficient
- **Recurring worktree merge-aborts**: gate-running `uv` commands dirtied `uv.lock` in the main tree, aborting the next worktree merge; recovered each time (cherry-pick / FF), then fixed the discipline (clean lock before merge; verify-before-branch-delete).
- **Background-subagent Bash loss mid-Phase-4**: background executors abruptly lost Bash access (foreground kept it). Lost a couple of dispatch cycles before pivoting Phase 4's tail + all of Phase 5 to foreground/inline execution.
- **Tracking-hygiene drift**: `phase.complete` left REQUIREMENTS.md checkboxes and three phases' `nyquist_compliant` flags unflipped (requirements were satisfied; the table was stale) — surfaced at audit.
- **Windows + uv pytest backgrounding**: long `uv run pytest` auto-backgrounded and a zombie pytest once locked the venv; resolved by killing strays + file-redirected runs.

### Patterns Established
- **Optional-extra adapters**: cloud deps behind a `cloud` extra; **test gate `--extra dev` (adapters skip without creds), type gate `--extra dev --extra cloud` (SDKs present)**.
- **vec0 upsert = DELETE-then-INSERT** (sqlite-vec ignores `INSERT OR REPLACE` on re-embed).
- **Deterministic stubs** (StubLLM/StubEmbedder) make consolidation, supersession, decay, packing, and the demo/eval fully hermetic + reproducible.
- **Recover-don't-redo**: when an executor died/lost-Bash mid-plan, merge its committed/staged work or commit-from-orchestrator rather than re-running.

### Key Lessons
- Adversarial review/verify gates earn their cost — the highest-value bugs (protected-flag, eviction-hard-delete, migrate data-loss) all passed the green test suite.
- Pin the Python upper bound and the conformance backend matrix early; "≥2 backends/axis" needs a hermetic 2nd backend (moto-S3) or it silently becomes "1 + gated."
- An honest before/after eval needs *strengthened* assertions (`== expected`, content-containment) — a `<=` assertion can pass with a fully-broken baseline.

### Cost Observations
- Model mix: ~all sonnet (executors/researchers/planners/checkers/fixers) under an opus orchestrator.
- Multi-session (spanning 2026-06-10 → 06-15); heavy subagent fan-out per phase (research → pattern-map → plan → 2× checker → wave executors → review → fix → verify).
- Notable: foreground subagents and inline orchestrator execution were the reliable fallback when background-worktree execution degraded.

---

## Cross-Milestone Trends

| Milestone | Phases | Plans | Tests (final) | Status |
|-----------|--------|-------|---------------|--------|
| v1.0 | 5 | 28 | 124 passed / 71 skipped | Shipped 2026-06-15 |
