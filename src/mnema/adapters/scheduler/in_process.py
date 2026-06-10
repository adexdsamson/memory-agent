"""InProcessScheduler — APScheduler 3.x AsyncIOScheduler behind the Scheduler Protocol.

Uses APScheduler 3.11.x (pinned <4 in pyproject.toml — 4.x is alpha with a
different API). The AsyncIOScheduler attaches to the running asyncio event loop,
making trigger_now() and scheduled dispatch work inside pytest-asyncio tests.

Satisfies Scheduler Protocol via structural subtyping (async variant):
  - async start() -> None
  - async schedule(fn, *, every_seconds: int) -> None
  - async trigger_now() -> None
  - async shutdown() -> None
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]


JOB_ID = "consolidate"


class InProcessScheduler:
    """In-process scheduler backed by APScheduler 3.x AsyncIOScheduler.

    CRITICAL implementation notes:
      - Use APScheduler 3.x API (AsyncIOScheduler, not AsyncScheduler from 4.x)
      - next_run_time=None on add_job prevents an immediate first-fire on schedule()
      - trigger_now() uses datetime.now() (local time), not datetime.utcnow()
        APScheduler 3.x uses local time for internal comparison
      - shutdown(wait=False) avoids blocking the event loop on test teardown
    """

    JOB_ID: str = JOB_ID

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler = AsyncIOScheduler()

    async def start(self) -> None:
        """Start the underlying AsyncIOScheduler on the current event loop."""
        self._scheduler.start()

    async def schedule(self, fn: Any, *, every_seconds: int) -> None:
        """Register fn to run on an interval. Does not fire immediately.

        next_run_time=None means the first execution is deferred until the
        interval elapses or trigger_now() is called explicitly.
        """
        self._scheduler.add_job(  # type: ignore[no-untyped-call]
            fn,
            "interval",
            seconds=every_seconds,
            id=self.JOB_ID,
            next_run_time=None,
        )

    async def trigger_now(self) -> None:
        """Fire the scheduled consolidation job immediately.

        Sets next_run_time to datetime.now() (local time), which APScheduler 3.x
        picks up on the next event loop tick and dispatches within ~100ms.
        """
        job = self._scheduler.get_job(self.JOB_ID)  # type: ignore[no-untyped-call]
        if job is not None:
            job.modify(next_run_time=datetime.now())  # type: ignore[no-untyped-call]

    async def shutdown(self) -> None:
        """Shut down the scheduler without waiting for running jobs to complete."""
        self._scheduler.shutdown(wait=False)
