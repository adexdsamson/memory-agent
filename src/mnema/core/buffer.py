"""MNEMA in-memory recent-session buffer (WRITE-02 / RECALL-01).

RecentSessionBuffer holds the most recent K turns per (user_id, session_id) pair
in a bounded deque. This is the "read-after-write freshness" fix: a turn stated
in the current session is immediately recallable via the buffer before any T1
provisional write has completed or been indexed.

This module is pure in-memory — no async, no I/O, no database access.
All state lives in a dict of deques; there is no persistence.

Buffer scoping model (from Plan 04 note):
  In a multi-user context the buffer must be keyed by (user_id, session_id) so
  that a recall for user_id="u1" never surfaces turns written by user_id="u2".
  WritePath stores turns under (user_id, session_id) and RecallPath fetches
  them with as_candidates_for_user(user_id) which returns all sessions for
  that user (correct: cross-session recall is desired, cross-user is not).
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from mnema.core.schema import Turn


class RecentSessionBuffer:
    """Bounded in-memory buffer of recent turns, keyed by (user_id, session_id).

    Stores at most `k` turns per (user_id, session_id) key. Oldest turns are
    silently evicted when the deque reaches capacity (FIFO via deque(maxlen=k)).

    Methods are all synchronous — there is no I/O; callers do not await.
    """

    def __init__(self, k: int = 20) -> None:
        """Initialise buffer.

        Args:
            k: Maximum number of turns to retain per (user_id, session_id) key.
               Defaults to 20.
        """
        self._k = k
        # Key: (user_id, session_id) → bounded deque of Turns
        self._turns: dict[tuple[str, str], deque[Turn]] = {}

    def push(self, turn: Turn, session_id: str, user_id: str = "__default__") -> None:
        """Append a turn to the (user_id, session_id) deque.

        Evicts the oldest turn silently when the deque is full.

        Args:
            turn: The Turn to store.
            session_id: The session this turn belongs to.
            user_id: The user this turn belongs to (default: "__default__" for
                     backward-compat with single-user callers).
        """
        key = (user_id, session_id)
        if key not in self._turns:
            self._turns[key] = deque(maxlen=self._k)
        self._turns[key].append(turn)

    def as_candidates(self, session_id: Optional[str] = None) -> list[Turn]:
        """Return turns from all (user_id, session_id) keys, optionally filtered.

        If `session_id` is provided, returns only turns for that session across all
        users (primarily for single-user use; prefer as_candidates_for_user in
        multi-user contexts).

        If `session_id` is None, flattens all sessions across all users.

        Args:
            session_id: Optional session filter.

        Returns:
            List of Turn objects, in insertion order within each session.
        """
        result: list[Turn] = []
        if session_id is not None:
            for (_, sid), dq in self._turns.items():
                if sid == session_id:
                    result.extend(dq)
        else:
            for dq in self._turns.values():
                result.extend(dq)
        return result

    def as_candidates_for_user(self, user_id: str) -> list[Turn]:
        """Return all buffered turns for a specific user across all their sessions.

        This is the correct recall-time query: cross-session recall for one user,
        never crossing user boundaries (D-02 isolation).

        Args:
            user_id: The user whose turns to retrieve.

        Returns:
            List of Turn objects in insertion order within each session.
        """
        result: list[Turn] = []
        for (uid, _), dq in self._turns.items():
            if uid == user_id:
                result.extend(dq)
        return result
