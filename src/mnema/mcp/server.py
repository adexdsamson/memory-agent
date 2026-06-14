"""MNEMA MCP server — thin FastMCP wrapper over MemoryEngine (IFACE-02).

All business logic lives in the engine. This file contains ONLY protocol
plumbing: tool registration, arg extraction, response serialization.

Per D3-13: closure-capture injection — engine is passed in, closed over by
  nested @mcp.tool functions. No lifespan needed: engine already exists before
  server creation.
Per D3-14: user_id is explicit and required on every tool. It is never
  defaulted or ambient — the MCP client must supply it on every call.
Per D3-15: stdio transport for MVP; mcp_server.run() uses stdio by default.
Per D3-16: Client(mcp) in-process transport — no subprocess in tests.

SECURITY NOTE:
  T-03-04-01: user_id isolation enforced by engine on every verb.
  T-03-04-02: engine.forget() raises ValueError for cross-user or protected;
    FastMCP propagates the exception as a tool error to the client.
  T-03-04-05: stdio transport is local-only (MVP); HTTP/SSE auth → post-MVP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP

if TYPE_CHECKING:
    from mnema.core.engine import MemoryEngine


def create_mcp_server(engine: "MemoryEngine") -> FastMCP:
    """Create a FastMCP server wrapping the provided MemoryEngine.

    The server is a thin protocol layer — all business logic lives in `engine`.
    user_id is an explicit, required argument on every tool (D3-14 isolation
    contract). No tool duplicates any logic from the engine.

    API probe confirmed (2026-06-14): FastMCP 3.4.2 call_tool returns
    CallToolResult with both .data (Python value) and .content (list[TextContent]).
    .data is the canonical return value attribute used by all tests in this plan.

    Args:
        engine: A fully-constructed MemoryEngine instance. Closed over by
            the tool functions — the engine's lifetime must exceed the server's.

    Returns:
        A FastMCP instance with five tools registered: remember, recall,
        forget, consolidate, expand.
    """
    mcp: FastMCP = FastMCP("mnema")

    @mcp.tool
    async def remember(
        content: str,
        user_id: str,
        session_id: str,
        type_hint: str | None = None,
        durable: bool = False,
    ) -> str:
        """Store an utterance in memory.

        Args:
            content: The utterance text to store.
            user_id: Mandatory user scope boundary (D3-14 — explicit, required).
            session_id: Session provenance stamped on T0 and T1 records.
            type_hint: Optional record type hint ("fact", "preference", etc.).
            durable: If True, forces a provisional T1 write.

        Returns:
            The t0:// reference string for the stored turn.
        """
        return await engine.remember(
            content,
            user_id=user_id,
            session_id=session_id,
            type_hint=type_hint,
            durable=durable,
        )

    @mcp.tool
    async def recall(
        query: str,
        user_id: str,
        k: int = 10,
        budget: int = 2000,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant memories within a token budget.

        Args:
            query: Natural-language recall query.
            user_id: Mandatory user scope boundary (D3-14 — explicit, required).
            k: Dense KNN candidate count.
            budget: Token budget for packing summaries (RECALL-04).

        Returns:
            List of serialized MemoryRecord dicts: id, summary, record_type,
            salience, protected. Ordered by relevance × salience × recency.
        """
        records = await engine.recall(query, user_id=user_id, k=k, budget=budget)
        return [
            {
                "id": r.id,
                "summary": r.summary,
                "record_type": r.record_type.value,
                "salience": r.salience,
                "protected": r.protected,
            }
            for r in records
        ]

    @mcp.tool
    async def forget(record_id: str, user_id: str, reason: str = "") -> None:
        """Evict a record (mark for forgetting).

        The engine enforces:
          - Cross-user scope check: raises ValueError if record.user_id != user_id.
          - Protection check: raises ValueError if record.protected is True.
        FastMCP propagates ValueError as a tool error to the client (T-03-04-02).

        Args:
            record_id: The id of the record to evict.
            user_id: Mandatory user scope boundary (D3-14 — explicit, required).
            reason: Optional reason string for the eviction audit log.
        """
        await engine.forget(record_id, user_id=user_id, reason=reason)

    @mcp.tool
    async def consolidate(user_id: str) -> str:
        """Run offline consolidation for a user.

        Passes user_id to engine.consolidate(user_id=user_id) — this makes
        D3-14 isolation real, not deceptive. Consolidation is scoped to the
        requesting user's staged turns, vault, and eviction pass (T-03-04-06).

        Args:
            user_id: The user whose staged turns to consolidate (D3-14).

        Returns:
            "consolidated" on success.
        """
        await engine.consolidate(user_id=user_id)
        return "consolidated"

    @mcp.tool
    async def expand(record_id: str, user_id: str) -> dict[str, Any] | None:
        """Return the verbatim T0 turn behind a record.

        Returns None if the record does not exist or does not belong to user_id
        (scope check — T-03-04-01). No T0 data crosses user boundaries.

        Args:
            record_id: The MemoryRecord id whose T0 turn to retrieve.
            user_id: Mandatory user scope boundary (D3-14 — explicit, required).

        Returns:
            Dict with content, role, created_at (ISO format), or None.
        """
        turn = await engine.expand(record_id, user_id=user_id)
        if turn is None:
            return None
        return {
            "content": turn.content,
            "role": turn.role,
            "created_at": turn.created_at.isoformat(),
        }

    return mcp


if __name__ == "__main__":
    # Stdio entry point — dev/smoke test only.
    # Production deployments should construct a MemoryEngine from config and
    # pass it to create_mcp_server(), then call mcp_server.run().
    import asyncio  # noqa: PLC0415

    async def _build_engine() -> "MemoryEngine":
        """Construct a minimal local engine for stdio smoke-testing."""
        from mnema import MemoryEngine  # noqa: PLC0415
        from mnema.adapters.embedding.stub import StubEmbedder  # noqa: PLC0415
        from mnema.adapters.object_store.local_fs import LocalFS  # noqa: PLC0415
        from mnema.adapters.scheduler.in_process import InProcessScheduler  # noqa: PLC0415
        from mnema.adapters.vector_store.sqlite_t1 import SqliteT1  # noqa: PLC0415

        embedder = StubEmbedder(dim=128)
        t1 = await SqliteT1.open(".mnema_dev.db", dim=128)
        t0 = LocalFS(".mnema_dev_t0")
        scheduler = InProcessScheduler()
        await scheduler.start()
        return MemoryEngine(embedder=embedder, t1=t1, t0=t0, scheduler=scheduler)

    _engine = asyncio.run(_build_engine())
    _mcp_server = create_mcp_server(_engine)
    _mcp_server.run()  # Uses stdio transport by default (D3-15)
