"""CronScheduler — APScheduler 3.x CronTrigger behind the Scheduler Protocol.

Satisfies Scheduler Protocol via structural subtyping (SCHED-03).
Accepts a standard 5-field cron expression ('*/30 * * * *').
APScheduler 3.x only — pinned <4 in pyproject.toml; 4.x has a different API.

every_seconds parameter to schedule() is intentionally ignored: the cron
expression governs timing. Callers from MemoryEngine pass every_seconds as a
keyword argument (satisfying the Protocol signature), but CronScheduler uses
the cron_expression supplied at construction time instead.

Usage::

    scheduler = CronScheduler("*/30 * * * *")
    await scheduler.start()
    await scheduler.schedule(consolidate_fn, every_seconds=0)
    # fires every 30 minutes per the cron expression
    await scheduler.trigger_now()  # immediate fire for testing
    await scheduler.shutdown()
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

JOB_ID = "consolidate"


class CronScheduler:
    """Cron-string scheduler backed by APScheduler 3.x CronTrigger.

    Satisfies Scheduler Protocol via structural subtyping — same four async
    methods as InProcessScheduler (SCHED-03). No Protocol inheritance (D-08).

    CRITICAL implementation notes:
      - Use APScheduler 3.x API (AsyncIOScheduler, not AsyncScheduler from 4.x)
      - CronTrigger.from_crontab() parses standard 5-field cron expressions
      - next_run_time=None on add_job prevents an immediate first-fire on schedule()
      - trigger_now() uses datetime.now() (local time), not datetime.utcnow()
        APScheduler 3.x uses local time for internal comparison
      - shutdown(wait=False) avoids blocking the event loop on test teardown
      - every_seconds parameter is ignored — cron_expression governs timing
    """

    JOB_ID: str = JOB_ID

    def __init__(self, cron_expression: str) -> None:
        """Initialise CronScheduler with a 5-field cron expression.

        Args:
            cron_expression: Standard 5-field cron string, e.g. "*/30 * * * *".
                Passed directly to CronTrigger.from_crontab(). Malformed strings
                raise ValueError at schedule() time (not at construction time).
        """
        self._cron = cron_expression
        self._scheduler: AsyncIOScheduler = AsyncIOScheduler()

    async def start(self) -> None:
        """Start the underlying AsyncIOScheduler on the current event loop."""
        self._scheduler.start()

    async def schedule(self, fn: Any, *, every_seconds: int = 0) -> None:
        """Register fn to run according to the cron expression.

        The every_seconds parameter is intentionally ignored: the cron expression
        supplied at construction time governs timing, not the interval. This parameter
        exists solely to satisfy the Scheduler Protocol signature so CronScheduler can
        be used wherever InProcessScheduler is accepted.

        next_run_time=None means the first execution is deferred until the first
        cron tick or trigger_now() is called explicitly.

        Args:
            fn: Async callable to invoke on each cron tick (typically consolidate()).
            every_seconds: Ignored. Present only for Protocol compatibility.
        """
        trigger = CronTrigger.from_crontab(self._cron)  # type: ignore[no-untyped-call]
        self._scheduler.add_job(  # type: ignore[no-untyped-call]
            fn,
            trigger,
            id=self.JOB_ID,
            next_run_time=None,
        )

    async def trigger_now(self) -> None:
        """Fire the scheduled consolidation job immediately.

        Sets next_run_time to datetime.now() (local time), which APScheduler 3.x
        picks up on the next event loop tick and dispatches within ~100ms.
        No-ops if schedule() has not been called yet.
        """
        job = self._scheduler.get_job(self.JOB_ID)  # type: ignore[no-untyped-call]
        if job is not None:
            job.modify(next_run_time=datetime.now())  # type: ignore[no-untyped-call]

    async def shutdown(self) -> None:
        """Shut down the scheduler without waiting for running jobs to complete."""
        self._scheduler.shutdown(wait=False)
