"""FastAPI application.

Wires together, in ONE process:
    * the REST API (plan / excel / chat),
    * the MCP server mounted at /mcp over streamable HTTP,
    * a WebSocket /ws that broadcasts {version, diff} after every mutation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api import routes_chat, routes_excel, routes_plan
from .deps import get_settings, get_storage
from .events import get_event_bus
from .mcp_server.server import build_mcp_server

# Build the MCP server and serve it at exactly /mcp (not /mcp/mcp).
_mcp = build_mcp_server()
_mcp.settings.streamable_http_path = "/"
_mcp_app = _mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_storage()  # initialise + seed on first run
    async with _mcp.session_manager.run():
        yield


app = FastAPI(title="AI Gantt Planner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_plan.router)
app.include_router(routes_excel.router)
app.include_router(routes_chat.router)

# Streamable-HTTP MCP endpoint (the agent connects here).
app.mount("/mcp", _mcp_app)


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    bus = get_event_bus()
    queue = bus.subscribe()
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)
