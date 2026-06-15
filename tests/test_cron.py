"""CronScheduler standalone RED stubs — SCHED-03.

These tests are RED until plan 04-04 ships CronScheduler.
They fail with ImportError or AttributeError until the adapter exists.

Purpose: Prove that CronScheduler satisfies the Scheduler Protocol via
schedule() + trigger_now() and uses a cron expression for timing.
"""

from __future__ import annotations

import asyncio


class TestCronScheduler:
    """Standalone RED stubs for the CronScheduler adapter (SCHED-03).

    All tests FAIL until src/mnema/adapters/scheduler/cron.py ships in plan 04-04.
    """

    def test_cron_scheduler_imports(self) -> None:
        """CronScheduler must be importable from mnema.adapters.scheduler.cron.

        RED until plan 04-04. Fails with ImportError until the module exists.
        """
        # Will fail with ModuleNotFoundError if apscheduler is not installed
        pytest = __import__("pytest")
        pytest.importorskip("apscheduler")

        # Will fail with ImportError until plan 04-04 creates the module
        from mnema.adapters.scheduler.cron import CronScheduler  # noqa: PLC0415

        assert CronScheduler is not None

    async def test_cron_schedule_and_trigger(self) -> None:
        """CronScheduler.schedule() + trigger_now() must fire the function at least once.

        RED until plan 04-04 implements CronScheduler.
        Mirrors the sentinel pattern from tests/test_scheduler.py.
        """
        from mnema.adapters.scheduler.cron import CronScheduler  # noqa: PLC0415

        scheduler = CronScheduler("*/5 * * * *")
        await scheduler.start()

        call_count = 0

        async def sentinel() -> None:
            nonlocal call_count
            call_count += 1

        await scheduler.schedule(sentinel, every_seconds=0)
        await scheduler.trigger_now()
        await asyncio.sleep(0.2)

        assert call_count >= 1, (
            f"CronScheduler.trigger_now() must fire the sentinel function; "
            f"call_count={call_count}"
        )

        await scheduler.shutdown()
