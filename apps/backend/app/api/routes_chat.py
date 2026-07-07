"""Chat endpoint: streams the agent's progress + result as Server-Sent Events.

SSE event payloads (JSON in each `data:` line):
    {"type": "tool",    "name": ...}          # a tool was called
    {"type": "applied", "diff": {...}}        # apply_patch succeeded -> diff
    {"type": "message", "text": ...}          # final assistant text
    {"type": "done",    "text": ..., "applied": [...]}
    {"type": "error",   "error": ...}

The agent talks to THIS process's own MCP server. It connects over an IN-PROCESS
(in-memory) MCP transport rather than looping back out over HTTP: no network
round-trip, and none of the streamable-HTTP transport's host/DNS-rebinding checks
(which reject a public Host header with 421). The HTTP `/mcp` endpoint stays
mounted for external MCP clients. `session_provider` is swappable so tests (and
the offline path) inject their own session + fake LLM.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session

from ..deps import get_settings, make_llm_client
from ..llm.agent import run_agent
from ..mcp_server.server import build_mcp_server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@asynccontextmanager
async def _inmemory_mcp_session(_ignored: str = "") -> AsyncIterator[ClientSession]:
    """Default provider: an in-process MCP session to this app's own server.

    Uses in-memory streams (no HTTP, no host header, no port), so it works
    identically locally and behind a proxy like Render. Tools resolve the shared
    Storage singleton, so state matches the REST API.
    """
    server = build_mcp_server()
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        yield session


# Overridable in tests: (arg) -> async context manager yielding ClientSession.
session_provider: Callable[[str], Any] = _inmemory_mcp_session

# Overridable in tests: () -> OpenAI-compatible client.
llm_provider: Callable[[], Any] = make_llm_client


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _describe_error(exc: BaseException) -> str:
    """Unwrap anyio/TaskGroup ExceptionGroups to the underlying cause so the
    client sees the real reason, not 'unhandled errors in a TaskGroup'."""
    seen = 0
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions and seen < 5:
        exc = exc.exceptions[0]
        seen += 1
    return f"{type(exc).__name__}: {exc}".strip()


@router.post("/chat")
async def chat(body: ChatRequest) -> StreamingResponse:
    model = get_settings().llm_model

    async def event_stream() -> AsyncIterator[str]:
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(ev: dict[str, Any]) -> None:
            await queue.put(ev)

        async def run() -> None:
            try:
                llm = llm_provider()
                async with session_provider("") as session:
                    result = await run_agent(
                        session, llm, model, body.message,
                        history=body.history, on_event=on_event,
                    )
                await queue.put({"type": "done", "text": result.text, "applied": result.applied_diffs})
            except Exception as exc:  # surface a clean, unwrapped error to the client
                logger.exception("chat agent failed")  # full traceback in server logs
                await queue.put({"type": "error", "error": _describe_error(exc)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                yield _sse(ev)
        finally:
            await task

    return StreamingResponse(event_stream(), media_type="text/event-stream")
