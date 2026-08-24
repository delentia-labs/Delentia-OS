"""
WebSocket Live Event Stream Manager
Provides real-time pub/sub telemetry broadcasting to GUI, CLI, and external subscribers.
"""

import json
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket


class WebSocketManager:
    """Manages active WebSocket connections and broadcasts telemetry events."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        
        # Send initial welcome & heartbeat configuration
        welcome_packet = {
            "type": "CONNECTION_ESTABLISHED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "server": "Delentia-OS-WebSocket-Daemon",
            "active_clients": len(self.active_connections),
            "stream_channels": ["CORD_ENTROPY", "FDIA_GATE", "LORA_SWAP", "APPROVAL_QUEUE", "SYSTEM_LOGS"]
        }
        await websocket.send_text(json.dumps(welcome_packet))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket."""
        async with self._lock:
            self.active_connections.discard(websocket)

    async def broadcast(self, event_type: str, data: Dict[str, Any], intent_id: Optional[str] = None) -> int:
        """
        Broadcast a telemetry event packet to all connected clients.
        
        Returns:
            Number of clients successfully sent to.
        """
        if not self.active_connections:
            return 0

        packet = {
            "event_type": event_type,
            "intent_id": intent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        raw_msg = json.dumps(packet, default=str)

        dead_connections: List[WebSocket] = []
        sent_count = 0

        async with self._lock:
            for connection in list(self.active_connections):
                try:
                    await connection.send_text(raw_msg)
                    sent_count += 1
                except Exception:
                    dead_connections.append(connection)

            for dead in dead_connections:
                self.active_connections.discard(dead)

        return sent_count

    def broadcast_sync(self, event_type: str, data: Dict[str, Any], intent_id: Optional[str] = None) -> None:
        """Thread-safe synchronous wrapper for broadcast."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.broadcast(event_type, data, intent_id))
            else:
                loop.run_until_complete(self.broadcast(event_type, data, intent_id))
        except RuntimeError:
            pass


# Global singleton instance
WS_MANAGER = WebSocketManager()
