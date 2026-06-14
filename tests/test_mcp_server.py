"""Phase 3 MCP server surface tests — IFACE-02.

IFACE-02  The MCP server exposes the five engine verbs (remember, recall, forget,
          consolidate, expand) as MCP tools — a thin wrapper over the SDK.

Uses FastMCP's in-process Client(server) transport for hermetic assertions
(D3-16 — no subprocess, no network).

mcp_server fixture: calls create_mcp_server() from mnema.mcp.server (deferred
import).  Tests will FAIL at fixture setup until Plan 03-04 implements server.py.

IMPORTANT: async def test functions must NOT call asyncio.run() — they run
inside the pytest-asyncio event loop already.  Only the Hypothesis sync wrapper
in test_forgetting.py uses asyncio.run() (RESEARCH.md Pitfall 6).
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# mcp_server fixture — wraps the shared engine fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def mcp_server(engine):  # type: ignore[return]
    """Create a FastMCP server wrapping the test engine.

    Deferred import of create_mcp_server so pytest can collect tests in RED
    state before mnema.mcp.server is implemented (Plan 03-04).
    """
    from mnema.mcp.server import create_mcp_server  # noqa: PLC0415

    return create_mcp_server(engine)


# ---------------------------------------------------------------------------
# IFACE-02: MCP tool surface tests
# ---------------------------------------------------------------------------


async def test_mcp_tools_list(mcp_server) -> None:
    """IFACE-02: MCP server exposes the five engine verbs as tools.

    Expected tool names: remember, recall, forget, consolidate, expand.
    """
    from fastmcp import Client  # noqa: PLC0415

    async with Client(mcp_server) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert {"remember", "recall", "forget", "consolidate", "expand"} <= tool_names, (
            f"IFACE-02: expected 5 tools in MCP server; found: {tool_names}"
        )


async def test_mcp_remember_recall_roundtrip(mcp_server) -> None:
    """IFACE-02: remember/recall roundtrip via MCP tool surface.

    Calls 'remember' to store a peanut allergy fact, then 'recall' with a
    relevant query.  The allergy fact must appear in recall results — proving
    the MCP surface delegates to the same engine logic as the SDK.
    """
    from fastmcp import Client  # noqa: PLC0415

    async with Client(mcp_server) as client:
        await client.call_tool(
            "remember",
            {
                "content": "I am allergic to peanuts",
                "user_id": "u1",
                "session_id": "s1",
                "type_hint": "fact",
            },
        )
        result = await client.call_tool(
            "recall",
            {
                "query": "food allergies",
                "user_id": "u1",
            },
        )
        assert result.data is not None, "recall tool returned None data"
        # result.data is a list of dicts (as returned by the tool)
        summaries = (
            [r.get("summary", "") for r in result.data]
            if isinstance(result.data, list)
            else []
        )
        assert any("peanut" in s.lower() for s in summaries), (
            f"IFACE-02: peanut allergy not found in recall results: {summaries}"
        )
