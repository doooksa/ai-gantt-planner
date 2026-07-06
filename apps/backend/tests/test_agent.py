"""Agent loop driven by a scripted fake LLM over an in-memory MCP session.

Proves the full cycle (get_plan -> validate/apply -> final answer) without any
network or API key. The live 10-command gate lives in test_agent_scenarios.py.
"""

import asyncio

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from app.deps import set_storage
from app.llm.agent import run_agent
from app.mcp_server.server import build_mcp_server
from app.storage.db import Storage

from fake_llm import FakeLLM, assistant_text, assistant_tool_calls


@pytest.fixture
def storage():
    s = Storage(":memory:")
    s.ensure_seeded()
    set_storage(s)
    yield s
    s.close()
    set_storage(None)


def _run_agent(llm, message, events=None):
    async def go():
        server = build_mcp_server()
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            async def on_event(ev):
                if events is not None:
                    events.append(ev)
            return await run_agent(session, llm, "fake/model", message, on_event=on_event)

    return asyncio.run(go())


def test_agent_reads_then_applies(storage):
    llm = FakeLLM([
        assistant_tool_calls([("get_plan", {})]),
        assistant_tool_calls([("apply_patch", {"patch": {"ops": [
            {"type": "update_task", "selector": {"by_name": "Design"},
             "payload": {"duration_days": 5}}]}})]),
        assistant_text("Готово. Design теперь длится 5 дней."),
    ])
    events = []
    result = _run_agent(llm, "Увеличь длительность Design до 5 дней.", events)

    assert "5" in result.text
    assert storage.get_plan().by_id("design").duration_days == 5
    assert len(result.applied_diffs) == 1
    # An 'applied' event was emitted for the SSE stream.
    assert any(e["type"] == "applied" for e in events)
    assert any(e["type"] == "tool" and e["name"] == "get_plan" for e in events)


def test_agent_mass_reassign_single_patch(storage):
    llm = FakeLLM([
        assistant_tool_calls([("get_plan", {})]),
        assistant_tool_calls([("apply_patch", {"patch": {"ops": [
            {"type": "reassign", "selector": {"by_assignee": "Ivan"},
             "payload": {"assignee": "Maria"}}]}})]),
        assistant_text("Все задачи Ivan переназначены на Maria."),
    ])
    result = _run_agent(llm, "Все задачи Ivan переназначь на Maria.")

    assert result.iterations == 3
    assert [t.assignee for t in storage.get_plan().tasks if t.assignee == "Ivan"] == []
    assert storage.get_plan().by_id("backend-api").assignee == "Maria"


def test_agent_recovers_from_invalid_patch(storage):
    # First apply is a cycle (returns ok:false); agent then applies a valid patch.
    llm = FakeLLM([
        assistant_tool_calls([("apply_patch", {"patch": {"ops": [
            {"type": "set_dependencies", "selector": {"by_name": "Design"},
             "payload": {"predecessors": ["Demo"]}}]}})]),
        assistant_tool_calls([("apply_patch", {"patch": {"ops": [
            {"type": "update_task", "selector": {"by_name": "Design"},
             "payload": {"duration_days": 4}}]}})]),
        assistant_text("Первая попытка создала цикл, применил корректный вариант."),
    ])
    result = _run_agent(llm, "Поменяй зависимости Design.")

    # Only the valid apply is recorded as an applied diff.
    assert len(result.applied_diffs) == 1
    assert storage.get_plan().by_id("design").duration_days == 4


def test_agent_stops_at_iteration_limit(storage):
    # Always ask for a tool call -> never terminates -> hits the 10-step cap.
    llm = FakeLLM([assistant_tool_calls([("get_plan", {})]) for _ in range(20)])
    result = _run_agent(llm, "зациклись")
    assert result.iterations == 10
    assert "лимит" in result.text.lower()
