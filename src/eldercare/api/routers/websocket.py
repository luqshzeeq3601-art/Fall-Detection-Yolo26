"""FastAPI WebSocket endpoint for real-time event streaming (P5-007)."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from eldercare.api.auth import SESSION_COOKIE, user_for_token
from eldercare.api.ws import ConnectionManager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket) -> None:
    """Stream real-time system and fall incident events conforming to API_SPEC.md §6."""
    manager: ConnectionManager = websocket.app.state.connection_manager
    if websocket.app.state.require_auth:
        with websocket.app.state.session_factory() as db:
            user = user_for_token(db, websocket.cookies.get(SESSION_COOKIE))
        if user is None:
            await websocket.close(code=4401, reason="Sign in required")
            return
    await manager.connect(websocket)
    try:
        while True:
            # Keepalive listener: client can send text messages or ping
            message = await websocket.receive_text()
            if message.strip().lower() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
