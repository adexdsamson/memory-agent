# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-10)

**Core value:** An agent never forgets a protected fact (e.g. an allergy) and never acts on a superseded one — recalling the right context within a fixed token budget, regardless of which model provider or storage backend is configured.
**Current focus:** Phase 1 — Schema, Ports & Local Core Foundation

## Current Position

Phase: 1 of 5 (Schema, Ports & Local Core Foundation)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-06-10 — Roadmap created (5 phases, 58 v1 requirements mapped)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: —
- Trend: —

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Inside-out build order — schema → ports → local adapters → core orchestrators → cloud adapters → surfaces → demo (research-mandated, all four researchers concurred).
- Roadmap: Highest-risk surface (consolidation/supersession) front-loaded to Phase 2 while system is small and fully local/deterministic.
- Roadmap: Hybrid retrieval (BM25/graph/RRF), Function Compute, OpenAI/Ollama, REST, and public benchmarks are v2 — excluded from v1 phases.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2 flagged for deeper research at planning time: entity-resolution thresholds, contradiction-vs-refinement boundary, idempotency/locking model, provisional→confirmed state machine (MEDIUM confidence).
- Phase 4 flagged for deeper research: sqlite-vec extension loading on Windows demo machines, exact dependency pins at lock time, tsvector-vs-true-BM25 adequacy.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-10
Stopped at: ROADMAP.md and STATE.md created; REQUIREMENTS.md traceability populated.
Resume file: None
