"""WebSocket Connection Manager and event broadcaster (P5-007)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from eldercare.api.schemas import WebSocketEvent


class ConnectionManager:
    """Manages active WebSocket connections and thread-safe / async event broadcasting."""

    def __init__(self) -> None:
        self._active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        """Return the current number of active connections."""
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new incoming WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Safely unregister a WebSocket connection."""
        async with self._lock:
            self._active_connections.discard(websocket)

    async def broadcast(self, event: WebSocketEvent | dict[str, Any]) -> int:
        """Broadcast a structured event envelope to all connected WebSocket clients.

        Prunes broken / disconnected sockets automatically.

        Returns:
            Count of clients that successfully received the message.
        """
        if isinstance(event, WebSocketEvent):
            data = event.model_dump(mode="json")
        else:
            data = event

        async with self._lock:
            connections = list(self._active_connections)

        dead_connections: list[WebSocket] = []
        sent_count = 0

        for connection in connections:
            try:
                await connection.send_json(data)
                sent_count += 1
            except Exception:
                dead_connections.append(connection)

        if dead_connections:
            async with self._lock:
                for dead in dead_connections:
                    self._active_connections.discard(dead)

        return sent_count
