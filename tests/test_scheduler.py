"""Scheduler port tests.

Verifies that InProcessScheduler:
  - Can be started and shut down cleanly.
  - Fires scheduled functions on trigger_now().
  - Allows test code to synchronously verify consolidation was called (SCHED-02).

trigger_now() is the test-time escape hatch that lets deterministic tests
verify consolidation without waiting for a wall-clock interval.
"""

from __future__ import annotations

import asyncio

import pytest


class TestScheduler:
    async def test_trigger_now_fires_consolidate(self) -> None:
        """scheduler.trigger_now() invokes a scheduled function immediately.

        The sentinel pattern proves SCHED-02: consolidation can be triggered
        on demand in tests without a real time-based trigger.
        """
        from mnema.adapters.scheduler.in_process import InProcessScheduler  # noqa: PLC0415

        scheduler = InProcessScheduler()
        await scheduler.start()

        call_count = 0

        async def sentinel() -> None:
            nonlocal call_count
            call_count += 1

        await scheduler.schedule(sentinel, every_seconds=3600)
        await scheduler.trigger_now()
        # Give the in-process scheduler a moment to dispatch
        await asyncio.sleep(0.2)

        assert call_count >= 1, (
            f"Expected sentinel to be called at least once after trigger_now(), "
            f"but call_count={call_count}"
        )

        await scheduler.shutdown()
