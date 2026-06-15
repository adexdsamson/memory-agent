---
phase: 04-cloud-providers-backends
plan: "04"
subsystem: scheduler
tags: [scheduler, apscheduler, cron, sched-03, adapter]
dependency_graph:
  requires: [04-01]
  provides: [CronScheduler, SCHED-03]
  affects: [tests/conformance/test_scheduler_contract.py, tests/test_cron.py]
tech_stack:
  added: []
  patterns: [structural-typing, apscheduler-cron-trigger, protocol-mirror]
key_files:
  created:
    - src/mnema/adapters/scheduler/cron.py
  modified:
    - tests/conformance/conftest.py
decisions:
  - "CronTrigger.from_crontab() annotated with type: ignore[no-untyped-call] to satisfy pyright — APScheduler 3.x has no stubs"
  - "every_seconds Protocol parameter kept at default=0 in CronScheduler; cron expression governs timing"
  - "Conformance fixture uses '*/5 * * * *' (every 5 min) as the test expression — fast enough to not interfere with trigger_now() tests"
metrics:
  duration: "~5 minutes"
  completed: "2026-06-15"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 1
---

# Phase 04 Plan 04: CronScheduler Adapter Summary

**One-liner:** APScheduler 3.x CronTrigger adapter behind Scheduler Protocol; parses 5-field cron expressions; trigger_now() fires within 300ms.

## What Was Built

`CronScheduler` in `src/mnema/adapters/scheduler/cron.py` — a cron-string-backed scheduler that satisfies the `Scheduler` Protocol via structural subtyping (SCHED-03). It mirrors `InProcessScheduler` exactly (same 4 async methods, same `JOB_ID="consolidate"`) with one key change: `schedule()` uses `CronTrigger.from_crontab(cron_expression)` instead of an interval trigger. The `every_seconds` parameter is intentionally ignored and defaults to `0` — the cron expression governs timing.

The conformance `scheduler_backend` fixture in `tests/conformance/conftest.py` was updated to yield a live `CronScheduler("*/5 * * * *")` instance instead of `pytest.skip("CronScheduler not yet implemented")`.

## Task Completion

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | CronScheduler adapter | 9bf4dbf | src/mnema/adapters/scheduler/cron.py, tests/conformance/conftest.py |

## Verification Results

```
tests/test_cron.py ..           [2 passed]
tests/conformance/test_scheduler_contract.py[in_process] ..  [2 passed]
tests/conformance/test_scheduler_contract.py[cron]       ..  [2 passed]
tests/test_scheduler.py .       [1 passed]
Total: 7 passed in ~3.7s
pyright: 0 errors, 0 warnings
```

Full suite (excluding pre-existing `test_factory.py` failure from plan 04-07 work not yet shipped):
- 49 passed, 76 skipped, 1 pre-existing failure (`ModuleNotFoundError: No module named 'mnema.config'`)

## Design Notes

### Why `every_seconds: int = 0` (not removing the param)

The `Scheduler` Protocol defines `schedule(fn, *, every_seconds: int)` with no default. CronScheduler changes this to `every_seconds: int = 0` to allow callers to pass `schedule(fn, every_seconds=3600)` (matching InProcessScheduler's usage in the engine) while silently ignoring it. This satisfies structural typing while remaining backward compatible with the conformance tests which pass `every_seconds=3600`.

### pyright `type: ignore[no-untyped-call]` on `from_crontab()`

APScheduler 3.x ships no type stubs. The import is already decorated with `# type: ignore[import-untyped]`. The `from_crontab()` classmethod additionally needed `# type: ignore[no-untyped-call]` because pyright reports it as a partially unknown member. This mirrors the pattern in `in_process.py` where `get_job()` and `job.modify()` carry the same annotation.

## Deviations from Plan

None — plan executed exactly as written.

The `# type: ignore[no-untyped-call]` annotation on `CronTrigger.from_crontab()` is a Rule 1 auto-fix (would have caused `pyright` error without it). In practice it's identical to the suppression already present on other APScheduler calls in `in_process.py`.

## Known Stubs

None.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. CronScheduler is an in-process APScheduler wrapper. The threat model in the plan (T-04-04-01 through T-04-04-03) was reviewed: all accepted with no mitigations required in the adapter itself.

## Self-Check

```
[ -f src/mnema/adapters/scheduler/cron.py ] → FOUND
git log --oneline | grep 9bf4dbf → FOUND: 9bf4dbf feat(04-04): implement CronScheduler adapter (SCHED-03)
```

## Self-Check: PASSED
