"""MCP tools exercised over an in-memory transport (no HTTP, no LLM)."""

import asyncio
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from app.deps import set_storage
from app.mcp_server.server import build_mcp_server
from app.storage.db import Storage


@pytest.fixture
def storage():
    s = Storage(":memory:")
    s.ensure_seeded()
    set_storage(s)
    yield s
    s.close()
    set_storage(None)


def _run(coro):
    return asyncio.run(coro)


def _result_json(result):
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def _with_session(fn):
    server = build_mcp_server()
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        return await fn(session)


def test_list_tools_exactly_four(storage):
    async def go(session):
        tools = (await session.list_tools()).tools
        return sorted(t.name for t in tools)

    names = _run(_with_session(go))
    assert names == ["apply_patch", "get_plan", "undo_last", "validate_patch"]


def test_get_plan_returns_dated_plan(storage):
    async def go(session):
        res = await session.call_tool("get_plan", {})
        return _result_json(res)

    plan = _run(_with_session(go))
    assert len(plan["tasks"]) == 8
    assert all("start" in t and "end" in t for t in plan["tasks"])


def test_validate_patch_does_not_persist(storage):
    async def go(session):
        patch = {"ops": [{"type": "update_task",
                          "selector": {"by_name": "Design"},
                          "payload": {"duration_days": 9}}]}
        res = await session.call_tool("validate_patch", {"patch": patch})
        return _result_json(res)

    out = _run(_with_session(go))
    assert out["ok"] is True
    # Not persisted.
    assert storage.get_plan().by_id("design").duration_days == 3


def test_apply_patch_persists_and_bumps_version(storage):
    async def go(session):
        patch = {"ops": [{"type": "update_task",
                          "selector": {"by_name": "Design"},
                          "payload": {"duration_days": 5}}]}
        res = await session.call_tool("apply_patch", {"patch": patch})
        return _result_json(res)

    out = _run(_with_session(go))
    assert out["ok"] is True
    assert storage.get_plan().by_id("design").duration_days == 5
    assert storage.get_plan().version == 1


def test_apply_patch_invalid_returns_error(storage):
    async def go(session):
        # Cycle: Design depends on Demo (which transitively depends on Design).
        patch = {"ops": [{"type": "set_dependencies",
                          "selector": {"by_name": "Design"},
                          "payload": {"predecessors": ["Demo"]}}]}
        res = await session.call_tool("apply_patch", {"patch": patch})
        return _result_json(res)

    out = _run(_with_session(go))
    assert out["ok"] is False
    assert out["code"] == "cycle"
    assert storage.get_plan().version == 0  # untouched


def test_undo_last_restores(storage):
    async def go(session):
        await session.call_tool("apply_patch", {"patch": {"ops": [
            {"type": "update_task", "selector": {"by_name": "Design"},
             "payload": {"duration_days": 5}}]}})
        res = await session.call_tool("undo_last", {})
        return _result_json(res)

    out = _run(_with_session(go))
    assert out["ok"] is True
    assert storage.get_plan().by_id("design").duration_days == 3
