"""Build the FastMCP server and expose it as a mountable ASGI app.

The same server instance is (a) mounted into FastAPI at /mcp via
`streamable_http_app()` and (b) connected to in tests via an in-memory transport
using `build_mcp_server()._mcp_server`.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import register


def build_mcp_server() -> FastMCP:
    mcp = FastMCP("ai-gantt-planner")
    register(mcp)
    return mcp
