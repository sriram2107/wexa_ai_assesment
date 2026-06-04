"""
WebSocket connection manager for real-time features:
- Live dashboard updates
- Real-time alert notifications
- Live event stream
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import WebSocket
import structlog

logger = structlog.get_logger()


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        # {org_id: {connection_type: [websocket, ...]}}
        self.active_connections: dict[str, dict[str, list[WebSocket]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, org_id: str, channel: str = "dashboard"):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            if org_id not in self.active_connections:
                self.active_connections[org_id] = {}
            if channel not in self.active_connections[org_id]:
                self.active_connections[org_id][channel] = []
            self.active_connections[org_id][channel].append(websocket)

        logger.info("ws_connected", org_id=org_id, channel=channel)

    async def disconnect(self, websocket: WebSocket, org_id: str, channel: str = "dashboard"):
        """Remove a WebSocket connection."""
        async with self._lock:
            if (
                org_id in self.active_connections
                and channel in self.active_connections[org_id]
            ):
                try:
                    self.active_connections[org_id][channel].remove(websocket)
                except ValueError:
                    pass

        logger.info("ws_disconnected", org_id=org_id, channel=channel)

    async def broadcast_to_org(self, org_id: str, channel: str, message: dict):
        """Send a message to all connections of a specific org and channel."""
        connections = (
            self.active_connections.get(org_id, {}).get(channel, [])
        )
        dead_connections = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)

        # Clean up dead connections
        for dc in dead_connections:
            await self.disconnect(dc, org_id, channel)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send a message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception:
            pass

    async def broadcast_event(self, org_id: str, event_data: dict):
        """Broadcast a new event to the live event stream."""
        await self.broadcast_to_org(org_id, "events", {
            "type": "new_event",
            "data": event_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def broadcast_dashboard_update(self, org_id: str, dashboard_id: str):
        """Notify clients that a dashboard should be refreshed."""
        await self.broadcast_to_org(org_id, "dashboard", {
            "type": "dashboard_update",
            "dashboard_id": dashboard_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def broadcast_alert(self, org_id: str, alert_data: dict):
        """Broadcast an alert notification."""
        await self.broadcast_to_org(org_id, "alerts", {
            "type": "alert_triggered",
            "data": alert_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_connection_count(self, org_id: str = None) -> int:
        """Get total active connection count."""
        total = 0
        orgs = [org_id] if org_id else list(self.active_connections.keys())
        for oid in orgs:
            for channel_conns in self.active_connections.get(oid, {}).values():
                total += len(channel_conns)
        return total


# Singleton instance
ws_manager = ConnectionManager()
