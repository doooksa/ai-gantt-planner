"""Phase 2 LIVE gate: the 10 reference commands against a real LLM.

These call OpenRouter for real, so they are SKIPPED unless OPENROUTER_API_KEY is
set. Run the gate with a cheap model, e.g.:

    LLM_MODEL=anthropic/claude-haiku-4.5 \
    OPENROUTER_API_KEY=<your-openrouter-key> \
    ./.venv/Scripts/python.exe -m pytest tests/test_agent_scenarios.py -v

Gate target: 5/5 stable runs. Each test starts from a fresh seed (in-memory).
Assertions check the deterministic DOMAIN effect of the command, not the exact
wording of the model's answer.
"""

import asyncio
import os

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from app.deps import get_settings, make_llm_client, set_storage
from app.llm.agent import run_agent
from app.mcp_server.server import build_mcp_server
from app.storage.db import Storage

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.getenv("OPENROUTER_API_KEY"),
        reason="live gate: set OPENROUTER_API_KEY (and optionally a cheap LLM_MODEL)",
    ),
]


@pytest.fixture
def storage():
    s = Storage(":memory:")
    s.ensure_seeded()
    set_storage(s)
    yield s
    s.close()
    set_storage(None)


def run(command: str, history=None):
    """Run one agent turn from the current storage state; return AgentResult."""
    llm = make_llm_client()
    model = get_settings().llm_model

    async def go():
        server = build_mcp_server()
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            return await run_agent(session, llm, model, command, history=history or [])

    return asyncio.run(go())


def _start(storage, task_id):
    from app.excel import scheduled_plan
    return scheduled_plan(storage.get_plan()).by_id(task_id).start


# 1
def test_shift_frontend_later(storage):
    before = _start(storage, "frontend")
    run('Перенеси задачу "Frontend" на 3 дня позже.')
    after = _start(storage, "frontend")
    assert (after - before).days == 3


# 2
def test_reassign_ivan_to_maria(storage):
    run("Все задачи Ivan переназначь на Maria.")
    assert [t.id for t in storage.get_plan().tasks if t.assignee == "Ivan"] == []
    assert storage.get_plan().by_id("backend-api").assignee == "Maria"


# 3
def test_add_security_review(storage):
    run('Добавь задачу "Security review" на 2 дня после Backend API, исполнитель Anna.')
    tasks = storage.get_plan().tasks
    sec = next((t for t in tasks if "security" in t.name.lower()), None)
    assert sec is not None
    assert sec.assignee == "Anna"
    assert "backend-api" in sec.predecessor_ids


# 4
def test_demo_also_depends_on_excel_export(storage):
    run("Сделай Demo зависимой ещё и от Excel Export.")
    demo = storage.get_plan().by_id("demo")
    assert "excel-export" in demo.predecessor_ids
    assert "testing" in demo.predecessor_ids  # existing dep preserved


# 5
def test_increase_design_duration(storage):
    run("Увеличь длительность Design до 5 дней.")
    assert storage.get_plan().by_id("design").duration_days == 5


# 6
def test_delete_testing_warns(storage):
    result = run("Удали задачу Testing.")
    assert storage.get_plan().by_id("testing") is None
    # Demo depended on Testing -> agent should mention the dependent / removal.
    assert result.text.strip() != ""


# 7
def test_remove_frontend_dependency(storage):
    run("Убери зависимость Frontend от Design.")
    assert "design" not in storage.get_plan().by_id("frontend").predecessor_ids


# 8
def test_show_session_changes(storage):
    # Make a change, then ask what changed (same conversation history).
    run("Увеличь длительность Design до 5 дней.")
    result = run("Покажи, что изменилось за сессию.")
    assert result.text.strip() != ""


# 9
def test_busiest_assignee(storage):
    result = run("Кто самый загруженный исполнитель?")
    assert result.text.strip() != ""


# 10
def test_undo_last_change(storage):
    run("Увеличь длительность Design до 5 дней.")
    assert storage.get_plan().by_id("design").duration_days == 5
    run("Отмени последнее изменение.")
    assert storage.get_plan().by_id("design").duration_days == 3
