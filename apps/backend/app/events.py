"""Tiny in-process pub/sub bus for broadcasting plan mutations to WebSocket
clients. Every mutation (apply_patch, undo, upload, reset) publishes
`{"version": int, "diff": <Diff|None>}`; each connected `/ws` client drains its
own queue.
"""

from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def publish(self, message: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            q.put_nowait(message)


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
