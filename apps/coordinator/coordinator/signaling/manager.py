"""
Signaling Connection Manager.

Manages active WebSocket connections for peer-to-peer WebRTC signaling.
Enforces stable peer registration, prevents duplicate connection hijacking,
and routes messages between peers safely.
"""

import asyncio
import datetime
import json
import logging
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

from coordinator.signaling.schemas import (
    SignalingMessage,
)

logger = logging.getLogger(__name__)


class DuplicatePeerError(Exception):
    """Raised when attempting to register a peer ID that is already actively connected."""

    pass


class PeerNotFoundError(Exception):
    """Raised when attempting to route a message to a disconnected or unknown peer."""

    pass


class SignalingManager:
    """In-memory coordinator connection registry and message router."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        peer_id: str,
        websocket: WebSocket,
        client_info: dict[str, Any] | None = None,
    ) -> None:
        """
        Register a new peer connection.

        Raises DuplicatePeerError if an active connection already exists for this peer_id.
        Avoids silently replacing active connections.
        """
        async with self._lock:
            existing = self._connections.get(peer_id)
            if existing is not None:
                # Check if the existing socket is still open
                if existing.client_state == WebSocketState.CONNECTED:
                    logger.warning(
                        "Registration rejected: peer_id '%s' is already connected", peer_id
                    )
                    raise DuplicatePeerError(
                        f"Peer '{peer_id}' is already actively connected. "
                        "Silently replacing active connections is disabled."
                    )
                else:
                    # Clean up stale connection
                    logger.info("Cleaning up dead connection for peer_id '%s'", peer_id)
                    self._connections.pop(peer_id, None)
                    self._metadata.pop(peer_id, None)

            self._connections[peer_id] = websocket
            self._metadata[peer_id] = {
                "connected_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "client_info": client_info or {},
            }
            logger.info(
                "Peer registered for signaling: '%s' (active peers: %d)",
                peer_id,
                len(self._connections),
            )

    async def unregister(self, peer_id: str, websocket: WebSocket | None = None) -> bool:
        """
        Remove a peer connection.

        If a websocket reference is provided, unregister only if it matches the registered socket.
        Returns True if removed, False otherwise.
        """
        async with self._lock:
            existing = self._connections.get(peer_id)
            if existing is None:
                return False

            if websocket is not None and existing is not websocket:
                # The connection was already replaced or belongs to another socket
                return False

            self._connections.pop(peer_id, None)
            self._metadata.pop(peer_id, None)
            logger.info(
                "Peer unregistered: '%s' (remaining peers: %d)",
                peer_id,
                len(self._connections),
            )
            return True

    def is_connected(self, peer_id: str) -> bool:
        """Check if a peer is currently connected and active."""
        ws = self._connections.get(peer_id)
        return ws is not None and ws.client_state == WebSocketState.CONNECTED

    def get_connected_peers(self) -> list[str]:
        """Return a sorted list of all active peer IDs."""
        return sorted(self._connections.keys())

    def get_peer_count(self) -> int:
        """Return count of connected peers."""
        return len(self._connections)

    async def send_to(self, target_id: str, message: dict[str, Any] | SignalingMessage) -> None:
        """
        Send a message directly to a specific connected peer.

        Raises PeerNotFoundError if target is not connected.
        """
        async with self._lock:
            ws = self._connections.get(target_id)
            if ws is None or ws.client_state != WebSocketState.CONNECTED:
                raise PeerNotFoundError(f"Target peer '{target_id}' is not connected")

        payload = message.model_dump() if isinstance(message, SignalingMessage) else message
        text = json.dumps(payload)
        await ws.send_text(text)

    async def broadcast(
        self,
        message: dict[str, Any] | SignalingMessage,
        exclude_id: str | None = None,
    ) -> None:
        """Broadcast a message to all connected peers, optionally excluding sender."""
        payload = message.model_dump() if isinstance(message, SignalingMessage) else message
        text = json.dumps(payload)

        async with self._lock:
            targets = [
                (pid, ws)
                for pid, ws in self._connections.items()
                if pid != exclude_id and ws.client_state == WebSocketState.CONNECTED
            ]

        for pid, ws in targets:
            try:
                await ws.send_text(text)
            except Exception as exc:
                logger.warning("Failed to broadcast message to peer '%s': %s", pid, exc)


# Global singleton instance for the coordinator process
signaling_manager = SignalingManager()
