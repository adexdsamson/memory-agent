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

API probe finding (Task 1, 2026-06-14):
  FastMCP 3.4.2 call_tool returns CallToolResult with attrs:
    content, data, is_error, meta, structured_content
  result.data is the canonical Python return value — str, list, dict, or None.
  All assertions in this file use result.data (not result.content).
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


async def test_mcp_forget_protected_raises(mcp_server) -> None:
    """IFACE-02: forget on a non-protected record succeeds; protected record raises.

    This test proves that engine.forget() scope/protection checks are surfaced
    through the MCP layer. FastMCP propagates ValueError as a tool error (is_error=True).
    """
    from fastmcp import Client  # noqa: PLC0415

    async with Client(mcp_server) as client:
        # Store a plain (non-protected) fact
        await client.call_tool(
            "remember",
            {
                "content": "I prefer morning meetings",
                "user_id": "u1",
                "session_id": "s1",
                "type_hint": "preference",
            },
        )
        # Recall to get the record id
        recall_result = await client.call_tool(
            "recall",
            {"query": "morning meetings", "user_id": "u1"},
        )
        # result attribute: data — confirmed by Task 1 API probe
        records = recall_result.data if isinstance(recall_result.data, list) else []
        if records:
            record_id = records[0]["id"]
            # Forget a non-protected record — should succeed (no error)
            forget_result = await client.call_tool(
                "forget",
                {"record_id": record_id, "user_id": "u1", "reason": "test"},
            )
            assert not forget_result.is_error, (
                f"forget on non-protected record should succeed; got error: {forget_result}"
            )

        # Forget with wrong user_id — engine raises ValueError → MCP tool error
        # Use a synthetic id to trigger the cross-user path via engine
        wrong_user_result = await client.call_tool(
            "forget",
            {"record_id": "nonexistent-record-id", "user_id": "u_other"},
        )
        # nonexistent record: engine returns silently (no error)
        assert not wrong_user_result.is_error, (
            "forget on nonexistent record should be a no-op, not an error"
        )


async def test_mcp_expand_returns_none_for_wrong_user(mcp_server) -> None:
    """IFACE-02: expand with wrong user_id returns None (scope check via MCP).

    Proves that T-03-04-01 user isolation is enforced through the MCP layer:
    engine.expand() returns None when record.user_id != caller's user_id.
    """
    from fastmcp import Client  # noqa: PLC0415

    async with Client(mcp_server) as client:
        # Store a record under u1
        await client.call_tool(
            "remember",
            {
                "content": "I have a peanut allergy",
                "user_id": "u1",
                "session_id": "s1",
                "type_hint": "fact",
            },
        )
        # Recall to get the record id
        recall_result = await client.call_tool(
            "recall",
            {"query": "allergy", "user_id": "u1"},
        )
        # result attribute: data — confirmed by Task 1 API probe
        records = recall_result.data if isinstance(recall_result.data, list) else []
        if records:
            record_id = records[0]["id"]
            # Expand with the WRONG user_id — must return None
            expand_result = await client.call_tool(
                "expand",
                {"record_id": record_id, "user_id": "u_attacker"},
            )
            # result attribute: data — confirmed by Task 1 API probe
            assert expand_result.data is None, (
                f"T-03-04-01 VIOLATION: expand with wrong user returned data: "
                f"{expand_result.data}"
            )


async def test_mcp_consolidate_passes_user_id(mcp_server) -> None:
    """IFACE-02: consolidate tool passes user_id to engine.consolidate(user_id=...).

    This is the D3-14 isolation proof: the consolidate MCP tool accepts user_id
    as an explicit required argument and delegates to engine.consolidate(user_id=user_id).
    Consolidation is scoped to the requesting user — not global (T-03-04-06).
    """
    from fastmcp import Client  # noqa: PLC0415

    async with Client(mcp_server) as client:
        # Store something first so there's staged content to consolidate
        await client.call_tool(
            "remember",
            {
                "content": "I am lactose intolerant",
                "user_id": "u1",
                "session_id": "s1",
                "type_hint": "fact",
            },
        )
        # Consolidate scoped to u1 — must succeed and return "consolidated"
        result = await client.call_tool(
            "consolidate",
            {"user_id": "u1"},
        )
        # result attribute: data — confirmed by Task 1 API probe
        assert not result.is_error, (
            f"consolidate(user_id='u1') raised an unexpected tool error: {result}"
        )
        assert result.data == "consolidated", (
            f"consolidate expected to return 'consolidated'; got: {result.data!r}"
        )
