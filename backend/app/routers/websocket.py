"""
WebSocket endpoints for real-time features.
"""

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.services.realtime_service import ws_manager

import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/ws", tags=["WebSocket"])


async def authenticate_ws(token: str) -> dict:
    """Authenticate WebSocket connection using JWT token."""
    try:
        payload = decode_token(token)
        return payload
    except Exception:
        return None


@router.websocket("/dashboard")
async def ws_dashboard(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket for live dashboard updates.
    Connect with ?token=<jwt_access_token>
    Receives: {"type": "dashboard_update", "dashboard_id": "..."}
    """
    payload = await authenticate_ws(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return

    org_id = payload.get("org_id", "default")

    await ws_manager.connect(websocket, org_id, "dashboard")
    try:
        while True:
            data = await websocket.receive_text()
            # Client can send heartbeat or subscribe to specific dashboards
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws_manager.send_personal(websocket, {"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, org_id, "dashboard")


@router.websocket("/events")
async def ws_events(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket for live event stream.
    Connect with ?token=<jwt_access_token>
    Receives: {"type": "new_event", "data": {...}}
    """
    payload = await authenticate_ws(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return

    org_id = payload.get("org_id", "default")

    await ws_manager.connect(websocket, org_id, "events")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws_manager.send_personal(websocket, {"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, org_id, "events")


@router.websocket("/alerts")
async def ws_alerts(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket for real-time alert notifications.
    Connect with ?token=<jwt_access_token>
    Receives: {"type": "alert_triggered", "data": {...}}
    """
    payload = await authenticate_ws(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return

    org_id = payload.get("org_id", "default")

    await ws_manager.connect(websocket, org_id, "alerts")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws_manager.send_personal(websocket, {"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, org_id, "alerts")
