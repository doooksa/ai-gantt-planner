"""MCP -> OpenAI schema bridge."""

import asyncio

from mcp.shared.memory import create_connected_server_and_client_session

from app.llm.mcp_openai_bridge import mcp_tools_to_openai
from app.mcp_server.server import build_mcp_server


def test_bridge_converts_all_tools_to_openai_schema():
    async def go():
        server = build_mcp_server()
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            return (await session.list_tools()).tools

    tools = asyncio.run(go())
    openai_tools = mcp_tools_to_openai(tools)

    assert len(openai_tools) == 4
    for ot in openai_tools:
        assert ot["type"] == "function"
        fn = ot["function"]
        assert fn["name"] in {"get_plan", "validate_patch", "apply_patch", "undo_last"}
        assert "description" in fn and fn["description"]
        # parameters must be a JSON-schema object.
        assert fn["parameters"]["type"] == "object"

    # apply_patch/validate_patch expose the `patch` argument in their schema.
    apply_schema = next(o["function"]["parameters"] for o in openai_tools
                        if o["function"]["name"] == "apply_patch")
    assert "patch" in apply_schema.get("properties", {})
