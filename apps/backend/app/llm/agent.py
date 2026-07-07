"""The agent loop: natural language -> MCP tool calls -> plan mutations.

Loop (per spec, max 10 iterations):
    user message
      -> chat.completions with the MCP tools (converted to OpenAI schema)
      -> tool_calls -> session.call_tool() -> results appended back
      -> repeat until the model returns a final text answer.

The agent is transport-agnostic: it takes an already-connected MCP `session`
(HTTP in prod, in-memory in tests) and an OpenAI-compatible `llm` client, so it
can be unit-tested with a fake LLM and no network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from mcp import ClientSession

from .mcp_openai_bridge import mcp_tools_to_openai, tool_result_to_text

MAX_ITERATIONS = 10

# Cap the model's output per turn. The agent only emits small tool-call payloads
# (a patch) and a 1-2 sentence summary, so this is ample — and it stops the
# request from pre-authorizing the model's full context (e.g. 64k), which fails
# the OpenRouter credit check ("can only afford N tokens") on low-limit keys.
MAX_RESPONSE_TOKENS = 2048

SYSTEM_PROMPT = (
    "Ты редактор плана проекта. Перед правками всегда читай план через get_plan. "
    "Для проверки используй validate_patch, затем apply_patch. Массовые операции "
    "— одним патчем с селектором (by_assignee и т.п.). Выбирай правильный тип "
    "операции: перенос задачи во времени («на N дней позже/раньше») — это "
    "shift_task с payload {\"days\": N}, а НЕ изменение длительности. Изменение "
    "зависимостей — set_dependencies с ПОЛНЫМ новым списком предшественников. "
    "Точную форму payload каждой операции смотри в описании инструмента "
    "apply_patch. Ответ пользователю — кратко на русском: одна-две фразы с сутью "
    "результата. НЕ перечисляй изменённые задачи и их новые даты — детальный "
    "список показывается пользователю отдельно в блоке «Applied changes»."
)

# Async callback the caller (e.g. the SSE route) passes to receive progress
# events: {"type": "tool"|"applied"|"message", ...}.
EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class AgentResult:
    text: str
    applied_diffs: list[dict] = field(default_factory=list)
    iterations: int = 0


async def _emit(on_event: EventCallback | None, event: dict[str, Any]) -> None:
    if on_event is not None:
        await on_event(event)


async def run_agent(
    session: ClientSession,
    llm: Any,
    model: str,
    user_message: str,
    *,
    history: list[dict] | None = None,
    on_event: EventCallback | None = None,
) -> AgentResult:
    tools = (await session.list_tools()).tools
    openai_tools = mcp_tools_to_openai(tools)

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    applied_diffs: list[dict] = []

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = await llm.chat.completions.create(
            model=model,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
            max_tokens=MAX_RESPONSE_TOKENS,
        )
        msg = response.choices[0].message
        tool_calls = list(msg.tool_calls or [])

        assistant_entry: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
        messages.append(assistant_entry)

        if not tool_calls:
            text = msg.content or ""
            await _emit(on_event, {"type": "message", "text": text})
            return AgentResult(text=text, applied_diffs=applied_diffs, iterations=iteration)

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            result = await session.call_tool(name, args)
            text = tool_result_to_text(result)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": text})
            await _emit(on_event, {"type": "tool", "name": name})

            if name == "apply_patch":
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = {}
                if payload.get("ok") and payload.get("diff"):
                    applied_diffs.append(payload["diff"])
                    await _emit(on_event, {"type": "applied", "diff": payload["diff"]})

    fallback = (
        "Достигнут лимит в 10 шагов, задача не завершена полностью. "
        "Уточни запрос или разбей его на части."
    )
    await _emit(on_event, {"type": "message", "text": fallback})
    return AgentResult(text=fallback, applied_diffs=applied_diffs, iterations=MAX_ITERATIONS)
