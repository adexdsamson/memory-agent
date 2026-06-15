"""MNEMA nutrition-coach reference demo (DEMO-01).

CLI interactive chat loop on build_engine(LocalConfig). Per D5-01/D5-02/D5-04.

Usage::

    python -m mnema.demo.coach --data-dir mnema_demo_data --session-id session-1

The demo showcases the core MNEMA guarantees:
  - Protected facts (allergies) survive every decay pass.
  - Superseded preferences (old diets) are excluded from recall.
  - Cross-session persistence: a constraint stated in session 1 is recalled in session 2.
  - Budget-bounded recall: large history packed under token limit.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from mnema.config import LocalConfig, build_engine
from mnema.core.engine import MemoryEngine, ScopedHandle


@dataclass
class CoachSession:
    """Holds the engine and scope for one interactive session."""

    engine: MemoryEngine
    scope: ScopedHandle
    data_dir: Path
    session_id: str = field(default="session-1")


async def suggest_meal(scope: ScopedHandle, query: str) -> str:
    """Return a constraint-respecting meal suggestion based on recalled facts.

    Calls scope.recall(query, budget=300) to retrieve the most relevant records
    within 300 tokens, then formats them as a suggestion string. Protected facts
    (allergies) always appear in the result by design (two-pass packer).

    Args:
        scope: The ScopedHandle bound to the user's engine and user_id.
        query: The meal-related query to recall against (e.g. "lunch ideas").

    Returns:
        A human-readable suggestion string listing retrieved constraints.
    """
    results = await scope.recall(query, budget=300)
    if not results:
        return "Suggested meal: No dietary constraints on record — anything goes!"
    constraints = [r.summary or r.content[:80] for r in results]
    return "Suggested meal considering your constraints:\n" + "\n".join(
        f"  - {c}" for c in constraints
    )


async def run_session(data_dir: Path, session_id: str) -> None:
    """Run an interactive nutrition-coach chat loop on build_engine(LocalConfig).

    Builds the engine over fixed local paths (D5-10: cross-session persistence).
    Runs a minimal REPL:
      1. Reads a line from stdin.
      2. Calls scope.remember(turn, session_id=session_id).
      3. Calls scope.recall(turn, budget=500) and prints recalled records.
      4. Exits on "quit" or "exit".
    After the loop, calls engine.consolidate() and engine._t1.close() (WAL flush).

    Args:
        data_dir: Directory for persistent SQLite + LocalFS files.
        session_id: Session identifier stamped on all T0 / T1 records.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg = LocalConfig(
        sqlite_path=str(data_dir / "mnema.db"),
        local_fs_path=str(data_dir / "t0"),
        vault_path=str(data_dir / "vault"),
    )
    engine = await build_engine(cfg)
    scope = engine.scope(user_id="coach_user")

    print("MNEMA Nutrition Coach — type your food facts or 'quit' to exit.")
    print(f"Session: {session_id}  |  Data: {data_dir}")
    print("-" * 60)

    try:
        while True:
            try:
                turn = input("> ").strip()
            except EOFError:
                break

            if turn.lower() in ("quit", "exit", ""):
                if turn.lower() in ("quit", "exit"):
                    break
                continue

            await scope.remember(turn, session_id=session_id)
            suggestion = await suggest_meal(scope, turn)
            print(suggestion)
            print()
    finally:
        await engine.consolidate()
        await engine.t1.close()
        await engine._scheduler.shutdown()  # type: ignore[union-attr]
        print("Session saved. Goodbye.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MNEMA Nutrition Coach reference demo (DEMO-01)"
    )
    parser.add_argument(
        "--data-dir",
        default="mnema_demo_data",
        help="Directory for persistent SQLite + LocalFS files (default: mnema_demo_data)",
    )
    parser.add_argument(
        "--session-id",
        default="session-1",
        help="Session identifier for this run (default: session-1)",
    )
    args = parser.parse_args()
    asyncio.run(run_session(Path(args.data_dir), args.session_id))
