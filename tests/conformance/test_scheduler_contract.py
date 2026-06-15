"""Scheduler conformance contract tests.

Parametrized over all registered scheduler_backend fixture backends.
Local-always backends (in_process) run unconditionally.
Gated backends (cron) skip until CronScheduler ships in plan 04-04.

Key assertions:
  - trigger_now() fires a scheduled function immediately (sentinel pattern)
  - schedule() does NOT fire the function before trigger_now() is called
    (next_run_time=None contract for job queued with no immediate execution)
"""

from __future__ import annotations

import asyncio


def _make_record(user_id: str, summary: str):  # type: ignore[return]
    """Helper to construct a minimal MemoryRecord for scheduler contract tests."""
    from mnema.core.schema import MemoryRecord, RecordType  # noqa: PLC0415

    return MemoryRecord(
        user_id=user_id,
        session_id="s_sched_contract",
        record_type=RecordType.FACT,
        content=summary,
        summary=summary,
    )


class TestSchedulerContract:
    """Scheduler Protocol contract assertions.

    All assertions must hold for every registered scheduler_backend.
    """

    async def test_trigger_now_fires_function(self, scheduler_backend) -> None:  # type: ignore[no-untyped-def]
        """schedule() + trigger_now() must invoke the function at least once.

        Proves SCHED-02: trigger_now() is the test-time escape hatch that lets
        deterministic tests verify consolidation without waiting for a wall-clock
        interval.
        """
        call_count = 0

        async def sentinel() -> None:
            nonlocal call_count
            call_count += 1

        await scheduler_backend.schedule(sentinel, every_seconds=3600)
        await scheduler_backend.trigger_now()
        # Give the in-process scheduler a moment to dispatch
        await asyncio.sleep(0.2)

        assert call_count >= 1, (
            f"Expected sentinel to be called at least once after trigger_now(), "
            f"but call_count={call_count}"
        )

    async def test_schedule_does_not_fire_immediately(self, scheduler_backend) -> None:  # type: ignore[no-untyped-def]
        """schedule() must not fire the function before trigger_now() is called.

        The next_run_time=None contract: a newly scheduled job must NOT execute
        until trigger_now() is explicitly called (or the interval elapses — which
        at every_seconds=3600 will not happen during the test).
        """
        counter = 0

        async def increment() -> None:
            nonlocal counter
            counter += 1

        await scheduler_backend.schedule(increment, every_seconds=3600)
        # Wait a brief moment — job must NOT fire spontaneously
        await asyncio.sleep(0.05)
        assert counter == 0, (
            f"schedule() must not fire the function before trigger_now(); "
            f"got counter={counter} after 50ms"
        )
