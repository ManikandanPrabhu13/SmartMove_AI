"""
websocket.py

Live WebSocket endpoint for the SmartMove-AI dashboard. Every
telemetry/emergency broadcast produced by mqtt/handlers.py is
pushed to every client connected here in real time.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.ws.manager import manager

logger = logging.getLogger("smartmove.api.websocket")

router = APIRouter(
    tags=["WebSocket"]
)


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):

    await manager.connect(websocket)

    try:
        while True:
            # Dashboard clients are broadcast-only consumers; any
            # inbound message is just used as a keep-alive/ping and
            # otherwise ignored.
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)

    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        manager.disconnect(websocket)
