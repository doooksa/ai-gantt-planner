"""A scripted, OpenAI-compatible fake LLM for offline agent tests.

It mimics the tiny slice of the AsyncOpenAI surface the agent uses:
    llm.chat.completions.create(...) -> response with .choices[0].message
where message has `.content` and `.tool_calls` (each with .id/.function.name/
.function.arguments). Each call to create() returns the next scripted turn.

Build turns with `assistant_tool_calls([...])` and `assistant_text("...")`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Function:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    function: _Function
    type: str = "function"


@dataclass
class _Message:
    content: str | None = None
    tool_calls: list[_ToolCall] | None = None


@dataclass
class _Choice:
    message: _Message


@dataclass
class _Response:
    choices: list[_Choice]


def assistant_tool_calls(calls: list[tuple[str, dict]]) -> _Message:
    """calls: list of (tool_name, arguments_dict)."""
    tcs = [
        _ToolCall(id=f"call_{i}", function=_Function(name=name, arguments=json.dumps(args)))
        for i, (name, args) in enumerate(calls)
    ]
    return _Message(content=None, tool_calls=tcs)


def assistant_text(text: str) -> _Message:
    return _Message(content=text)


@dataclass
class FakeLLM:
    script: list[_Message]
    calls: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._queue = list(self.script)
        # Expose the chat.completions.create shape.
        self.chat = self
        self.completions = self

    async def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        if not self._queue:
            return _Response([_Choice(_Message(content="(конец сценария)"))])
        return _Response([_Choice(self._queue.pop(0))])
