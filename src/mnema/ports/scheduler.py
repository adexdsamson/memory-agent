"""Scheduler port — SCHED-01/02.

Sync methods — APScheduler 3.x scheduler control API is synchronous even inside
an async application. The adapter (InProcessScheduler) wraps AsyncIOScheduler
which integrates with the running event loop, but start/shutdown/schedule/trigger
are all sync control calls.

No @runtime_checkable — static checking only (D-10).
"""

from __future__ import annotations

from typing import Protocol


class Scheduler(Protocol):
    """Contract for a background consolidation scheduler."""

    def schedule(self, fn: object, *, every_seconds: int) -> None:
        """Register a recurring consolidation function."""
        ...

    def trigger_now(self) -> None:
        """Force an immediate fire of the scheduled function (SCHED-02)."""
        ...

    def start(self) -> None:
        """Start the scheduler background thread/loop."""
        ...

    def shutdown(self) -> None:
        """Shutdown the scheduler, releasing resources."""
        ...
