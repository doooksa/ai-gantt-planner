"""Chat endpoint: streams the agent's progress + result as Server-Sent Events.

SSE event payloads (JSON in each `data:` line):
    {"type": "tool",    "name": ...}          # a tool was called
    {"type": "applied", "diff": {...}}        # apply_patch succeeded -> diff
    {"type": "message", "text": ...}          # final assistant text
    {"type": "done",    "text": ..., "applied": [...]}
    {"type": "error",   "error": ...}

The agent connects to THIS process's MCP server over streamable HTTP (per spec).
`session_provider` is swappable so tests can inject an in-memory MCP session and
a fake LLM without a network or an API key.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from ..deps import get_settings, make_llm_client
from ..llm.agent import run_agent

router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@asynccontextmanager
async def _http_mcp_session(mcp_url: str) -> AsyncIterator[ClientSession]:
    """Default provider: connect to the mounted MCP server over streamable HTTP.

    `mcp_url` is the internal canonical endpoint (http://127.0.0.1:PORT/mcp/) —
    see deps.Settings.mcp_self_url for why it must be internal + trailing-slash.
    """
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


# Overridable in tests: (mcp_url) -> async context manager yielding ClientSession.
session_provider: Callable[[str], Any] = _http_mcp_session

# Overridable in tests: () -> OpenAI-compatible client.
llm_provider: Callable[[], Any] = make_llm_client


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(body: ChatRequest) -> StreamingResponse:
    settings = get_settings()
    model = settings.llm_model
    mcp_url = settings.mcp_self_url

    async def event_stream() -> AsyncIterator[str]:
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(ev: dict[str, Any]) -> None:
            await queue.put(ev)

        async def run() -> None:
            try:
                llm = llm_provider()
                async with session_provider(mcp_url) as session:
                    result = await run_agent(
                        session, llm, model, body.message,
                        history=body.history, on_event=on_event,
                    )
                await queue.put({"type": "done", "text": result.text, "applied": result.applied_diffs})
            except Exception as exc:  # surface a clean error event to the client
                await queue.put({"type": "error", "error": str(exc)})
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
