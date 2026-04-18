from __future__ import annotations

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

router = APIRouter(tags=["agent-ws"])


@router.websocket("/ws/sessions/{session_id}")
async def agent_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        await websocket.send_json(
            {"type": "error", "session_id": session_id, "message": "not implemented"}
        )
        await websocket.close(code=1011)
    except WebSocketDisconnect:
        return
