"""Bridge between the MCP tool protocol and the OpenAI chat-completions tools API.

Two directions:
    * `mcp_tools_to_openai` — MCP tool list -> OpenAI `tools=[...]` schema.
    * `tool_result_to_text` — MCP CallToolResult -> string for a `role:"tool"`
      message (prefers structured JSON, falls back to concatenated text).
"""

from __future__ import annotations

import json
from typing import Any

from mcp.types import CallToolResult, Tool


def mcp_tools_to_openai(tools: list[Tool]) -> list[dict[str, Any]]:
    """Convert MCP tool definitions to OpenAI function-tool schema."""
    openai_tools: list[dict[str, Any]] = []
    for t in tools:
        schema = t.inputSchema or {"type": "object", "properties": {}}
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": schema,
                },
            }
        )
    return openai_tools


def tool_result_to_text(result: CallToolResult) -> str:
    """Serialize an MCP tool result into a compact string for the LLM."""
    if result.structuredContent is not None:
        return json.dumps(result.structuredContent, ensure_ascii=False)

    parts: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    body = "\n".join(parts) if parts else "{}"
    if result.isError:
        return json.dumps({"ok": False, "error": body}, ensure_ascii=False)
    return body
