"""REST + SSE API tests via FastAPI TestClient.

The chat route is exercised with an in-memory MCP session and a scripted fake
LLM (no network, no key) by overriding its swappable providers.
"""

import json
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session

from app.api import routes_chat
from app.deps import set_storage
from app.main import app
from app.mcp_server.server import build_mcp_server
from app.storage.db import Storage

from conftest import make_xlsx
from fake_llm import FakeLLM, assistant_text, assistant_tool_calls


@pytest.fixture
def storage():
    s = Storage(":memory:")
    s.ensure_seeded()
    set_storage(s)
    yield s
    s.close()
    set_storage(None)


@pytest.fixture
def client(storage):
    # No `with` -> skip lifespan. These tests don't use the mounted /mcp (chat
    # uses the in-memory provider), and the MCP session_manager can only .run()
    # once per instance, which re-entering lifespan per test would violate.
    return TestClient(app)


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "commit" in body


def test_get_plan(client):
    plan = client.get("/api/plan").json()
    assert len(plan["tasks"]) == 8
    assert all("start" in t and "end" in t for t in plan["tasks"])


def test_export_excel_returns_xlsx(client):
    r = client.get("/api/export-excel")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert r.content[:2] == b"PK"  # xlsx is a zip


def test_upload_excel_replaces_plan(client, storage):
    headers = ["задача", "описание", "исполнитель", "длительность", "предшественники"]
    rows = [["Alpha", "", "Ann", 2, ""], ["Beta", "", "Bob", 3, "Alpha"]]
    xlsx = make_xlsx(headers, rows)

    r = client.post("/api/upload-excel", files={"file": ("plan.xlsx", xlsx, "application/octet-stream")})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert [t["name"] for t in body["plan"]["tasks"]] == ["Alpha", "Beta"]
    assert body["plan"]["version"] == 1  # bumped from seed's 0


def test_upload_excel_bad_file_returns_400(client):
    r = client.post("/api/upload-excel", files={"file": ("x.xlsx", b"not a real xlsx", "application/octet-stream")})
    assert r.status_code == 400
    assert "Excel" in r.json()["detail"] or "xlsx" in r.json()["detail"].lower()


def test_undo_restores_previous(client, storage):
    # Upload replaces the plan (a mutation), then undo restores the seed.
    xlsx = make_xlsx(["задача", "длительность", "предшественники"], [["Solo", 1, ""]])
    client.post("/api/upload-excel", files={"file": ("p.xlsx", xlsx, "application/octet-stream")})
    assert [t["name"] for t in client.get("/api/plan").json()["tasks"]] == ["Solo"]

    r = client.post("/api/undo")
    assert r.json()["ok"] is True
    assert len(client.get("/api/plan").json()["tasks"]) == 8


def test_reset_demo(client, storage):
    xlsx = make_xlsx(["задача", "длительность", "предшественники"], [["Solo", 1, ""]])
    client.post("/api/upload-excel", files={"file": ("p.xlsx", xlsx, "application/octet-stream")})
    r = client.post("/api/reset-demo")
    assert r.json()["ok"] is True
    plan = client.get("/api/plan").json()
    assert len(plan["tasks"]) == 8 and plan["version"] == 0


# --- chat SSE -------------------------------------------------------------


@pytest.fixture
def fake_chat(storage):
    """Override chat providers: in-memory MCP session + scripted fake LLM."""

    @asynccontextmanager
    async def mem_session(_base_url):
        server = build_mcp_server()
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            yield session

    original_session = routes_chat.session_provider
    original_llm = routes_chat.llm_provider
    routes_chat.session_provider = mem_session

    def set_script(script):
        routes_chat.llm_provider = lambda: FakeLLM(script)

    yield set_script
    routes_chat.session_provider = original_session
    routes_chat.llm_provider = original_llm


def _sse_events(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_chat_applies_and_streams_events(client, storage, fake_chat):
    fake_chat([
        assistant_tool_calls([("get_plan", {})]),
        assistant_tool_calls([("apply_patch", {"patch": {"ops": [
            {"type": "update_task", "selector": {"by_name": "Design"},
             "payload": {"duration_days": 5}}]}})]),
        assistant_text("Готово: Design теперь 5 дней."),
    ])

    r = client.post("/api/chat", json={"message": "Увеличь длительность Design до 5 дней."})
    assert r.status_code == 200
    events = _sse_events(r.text)
    types = [e["type"] for e in events]

    assert "applied" in types
    assert "done" in types
    done = next(e for e in events if e["type"] == "done")
    assert "5" in done["text"]
    assert storage.get_plan().by_id("design").duration_days == 5


def test_chat_reports_error_without_key(client, storage, monkeypatch):
    # Simulate a missing key regardless of whether .env provided one: the error
    # must surface as a clean SSE 'error' event, not a crash.
    import app.deps as deps

    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setattr(deps, "_settings", None)  # force settings re-read

    r = client.post("/api/chat", json={"message": "привет"})
    events = _sse_events(r.text)
    assert any(e["type"] == "error" and "OPENROUTER_API_KEY" in e["error"] for e in events)
