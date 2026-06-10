"""Scheduler port — SCHED-01/02.

Async methods (D-11 async-first). MNEMA runs inside an asyncio event loop, and
the reference adapter (InProcessScheduler) wraps APScheduler's AsyncIOScheduler,
which must be driven from the running loop. The control surface is therefore
defined as `async def` so callers always `await` it — a sync declaration here
would let a sync adapter structurally satisfy the Protocol yet break the engine,
and would mislead callers into NOT awaiting (un-awaited coroutines silently no-op).

No @runtime_checkable — static checking only (D-10).
"""

from __future__ import annotations

from typing import Protocol


class Scheduler(Protocol):
    """Contract for a background consolidation scheduler."""

    async def schedule(self, fn: object, *, every_seconds: int) -> None:
        """Register a recurring consolidation function."""
        ...

    async def trigger_now(self) -> None:
        """Force an immediate fire of the scheduled function (SCHED-02)."""
        ...

    async def start(self) -> None:
        """Start the scheduler background thread/loop."""
        ...

    async def shutdown(self) -> None:
        """Shutdown the scheduler, releasing resources."""
        ...
