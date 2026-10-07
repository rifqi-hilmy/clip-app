"""In-process pub/sub that lets worker threads push events to WebSocket clients."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class EventHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def _broadcast(self, event: dict[str, Any]) -> None:
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_json(event)
            except Exception:  # client gone
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def publish(self, event: dict[str, Any]) -> None:
        """Thread-safe: may be called from worker threads."""
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._broadcast(event), self._loop)


hub = EventHub()
