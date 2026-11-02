"""
Signaling API Router — /api/v1/signaling.

Provides:
- WebSocket endpoint for WebRTC SDP & ICE candidate signaling.
- REST endpoints for querying active signaling peers and ICE server configuration.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from coordinator.config import settings
from coordinator.signaling.manager import (
    DuplicatePeerError,
    PeerNotFoundError,
    signaling_manager,
)
from coordinator.signaling.schemas import (
    ConnectedPeersResponse,
    IceServerEntry,
    IceServersResponse,
    SignalingErrorCode,
    SignalingMessageType,
)

import hashlib
import hmac
import time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signaling", tags=["Signaling"])

# Per-peer rate limiting tracker
_peer_rate_limits: dict[str, list[float]] = {}


def generate_signaling_token(peer_id: str) -> str:
    """Generate a cryptographic HMAC token for signaling session authentication."""
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        peer_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signaling_token(peer_id: str, token: str) -> bool:
    """Verify that a peer presents an authentic HMAC token issued by the coordinator."""
    expected = generate_signaling_token(peer_id)
    return hmac.compare_digest(expected, token)


@router.get(
    "/peers",
    response_model=ConnectedPeersResponse,
    status_code=status.HTTP_200_OK,
    summary="List active WebRTC signaling peers",
)
async def list_signaling_peers() -> ConnectedPeersResponse:
    """Return all peer IDs currently connected to the signaling gateway."""
    peers = signaling_manager.get_connected_peers()
    return ConnectedPeersResponse(connected_peers=peers, count=len(peers))


@router.get(
    "/ice-servers",
    response_model=IceServersResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve WebRTC ICE server configurations",
)
async def get_ice_servers() -> IceServersResponse:
    """
    Return configured STUN and TURN servers for WebRTC peer connections.
    Secrets are never leaked; credentials are provided only if configured.
    """
    entries: list[IceServerEntry] = []

    # Configured STUN servers
    if settings.stun_servers:
        entries.append(IceServerEntry(urls=list(settings.stun_servers)))

    # Configured TURN server if available
    if settings.turn_server:
        entry = IceServerEntry(
            urls=[settings.turn_server],
            username=settings.turn_username,
            credential=settings.turn_credential,
        )
        entries.append(entry)

    return IceServersResponse(ice_servers=entries)


@router.websocket("/ws")
@router.websocket("/ws/{path_peer_id}")
async def signaling_websocket(
    websocket: WebSocket,
    path_peer_id: str | None = None,
    peer_id: str | None = Query(default=None),
    token: str | None = Query(default=None),
) -> None:
    """
    Bi-directional WebRTC signaling WebSocket endpoint with authentication and rate limiting.

    Flow:
    1. Accept WebSocket.
    2. Register peer ID (via path, query param '?peer_id=...', or initial 'register' JSON).
    3. In production mode, require valid HMAC token proof.
    4. Relay 'offer', 'answer', and 'ice_candidate' messages between peers.
    5. Handle 'ping'/'pong', 'get_peers', rate limits, and error reporting.
    6. Safely unregister peer on disconnect and broadcast 'peer_left'.
    """
    await websocket.accept()

    registered_peer_id: str | None = path_peer_id or peer_id
    auth_token: str | None = token

    # If peer_id was not provided in URL, wait for initial 'register' message
    if not registered_peer_id:
        try:
            init_text = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
            init_data = json.loads(init_text)
            if (
                not isinstance(init_data, dict)
                or init_data.get("type") != SignalingMessageType.REGISTER
            ):
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.MALFORMED_MESSAGE,
                        "message": "Initial message must be a 'register' type with 'peer_id'",
                    })
                )
                await websocket.close(code=1008, reason="Registration required")
                return
            registered_peer_id = init_data.get("peer_id")
            if not auth_token:
                auth_token = init_data.get("token")
            if not registered_peer_id or not isinstance(registered_peer_id, str):
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.MALFORMED_MESSAGE,
                        "message": "Field 'peer_id' must be a non-empty string",
                    })
                )
                await websocket.close(code=1008, reason="Invalid peer_id")
                return
        except TimeoutError:
            await websocket.close(code=1008, reason="Registration timed out")
            return
        except json.JSONDecodeError:
            await websocket.send_text(
                json.dumps({
                    "type": SignalingMessageType.ERROR,
                    "code": SignalingErrorCode.MALFORMED_MESSAGE,
                    "message": "Initial message is not valid JSON",
                })
            )
            await websocket.close(code=1008, reason="Malformed JSON")
            return

    # Authenticate signaling identity in production or when token required
    is_production = settings.environment.lower() == "production"
    if is_production or settings.signaling_require_token:
        if not auth_token or not verify_signaling_token(registered_peer_id, auth_token):
            await websocket.send_text(
                json.dumps({
                    "type": SignalingMessageType.ERROR,
                    "code": SignalingErrorCode.UNAUTHORIZED,
                    "message": "Signaling authentication failed: valid token required",
                })
            )
            await websocket.close(code=1008, reason="Signaling authentication required")
            return
    else:
        if not auth_token:
            logger.debug(
                "[%s] WebRTC signaling connected using unauthenticated development identity",
                registered_peer_id,
            )

    # Attempt registration with duplicate protection
    try:
        await signaling_manager.register(
            registered_peer_id,
            websocket,
            client_info={
                "client_host": websocket.client.host if websocket.client else None,
                "client_port": websocket.client.port if websocket.client else None,
            },
        )
    except DuplicatePeerError as exc:
        await websocket.send_text(
            json.dumps({
                "type": SignalingMessageType.ERROR,
                "code": SignalingErrorCode.PEER_ALREADY_CONNECTED,
                "message": str(exc),
            })
        )
        await websocket.close(code=1008, reason="Peer ID already active")
        return

    # Confirm registration to the connected peer
    await websocket.send_text(
        json.dumps({
            "type": SignalingMessageType.REGISTERED,
            "peer_id": registered_peer_id,
        })
    )

    # Notify others of peer joining
    await signaling_manager.broadcast(
        {"type": SignalingMessageType.PEER_JOINED, "peer_id": registered_peer_id},
        exclude_id=registered_peer_id,
    )

    MAX_SIGNALING_MESSAGE_SIZE = 65536

    try:
        while True:
            data_text = await websocket.receive_text()

            # Rate limiting check
            now = time.monotonic()
            timestamps = _peer_rate_limits.setdefault(registered_peer_id, [])
            _peer_rate_limits[registered_peer_id] = [t for t in timestamps if now - t < 60.0]
            if len(_peer_rate_limits[registered_peer_id]) >= settings.signaling_rate_limit_per_minute:
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.RATE_LIMITED,
                        "message": f"Rate limit exceeded: maximum {settings.signaling_rate_limit_per_minute} messages per minute",
                    })
                )
                continue
            _peer_rate_limits[registered_peer_id].append(now)

            # Reject oversized payloads
            if len(data_text) > MAX_SIGNALING_MESSAGE_SIZE:
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.MALFORMED_MESSAGE,
                        "message": f"Signaling message exceeds maximum size of {MAX_SIGNALING_MESSAGE_SIZE} bytes",
                    })
                )
                continue

            try:
                data = json.loads(data_text)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.MALFORMED_MESSAGE,
                        "message": "Received payload is not valid JSON",
                    })
                )
                continue

            if not isinstance(data, dict):
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.MALFORMED_MESSAGE,
                        "message": "Message must be a JSON object",
                    })
                )
                continue

            msg_type = data.get("type")
            if not msg_type:
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.MALFORMED_MESSAGE,
                        "message": "Missing required field 'type'",
                    })
                )
                continue

            # Validate message type is recognized
            allowed_types = {t.value for t in SignalingMessageType}.union({"get_peers"})
            if str(msg_type) not in allowed_types:
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.MALFORMED_MESSAGE,
                        "message": f"Unsupported signaling message type '{msg_type}'",
                    })
                )
                continue

            # Validate payload dictionary and content for SDP and ICE messages
            if msg_type in (SignalingMessageType.OFFER, SignalingMessageType.ANSWER):
                payload_dict = data.get("payload")
                if not isinstance(payload_dict, dict):
                    await websocket.send_text(
                        json.dumps({
                            "type": SignalingMessageType.ERROR,
                            "code": SignalingErrorCode.MALFORMED_MESSAGE,
                            "message": f"Message of type '{msg_type}' requires a dictionary 'payload'",
                        })
                    )
                    continue
                sdp_content = payload_dict.get("sdp")
                if not isinstance(sdp_content, str) or len(sdp_content) < 3 or len(sdp_content) > 32768:
                    await websocket.send_text(
                        json.dumps({
                            "type": SignalingMessageType.ERROR,
                            "code": SignalingErrorCode.MALFORMED_MESSAGE,
                            "message": "SDP payload must be a string between 3 and 32768 bytes",
                        })
                    )
                    continue

            elif msg_type == SignalingMessageType.ICE_CANDIDATE:
                payload_dict = data.get("payload")
                if not isinstance(payload_dict, dict):
                    await websocket.send_text(
                        json.dumps({
                            "type": SignalingMessageType.ERROR,
                            "code": SignalingErrorCode.MALFORMED_MESSAGE,
                            "message": "ICE candidate message requires a dictionary 'payload'",
                        })
                    )
                    continue
                cand_content = payload_dict.get("candidate")
                if not isinstance(cand_content, str) or len(cand_content) < 3 or len(cand_content) > 2048:
                    await websocket.send_text(
                        json.dumps({
                            "type": SignalingMessageType.ERROR,
                            "code": SignalingErrorCode.MALFORMED_MESSAGE,
                            "message": "ICE candidate payload must be a string between 3 and 2048 bytes",
                        })
                    )
                    continue

            # Heartbeat / ping handling
            if msg_type == SignalingMessageType.PING:
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.PONG,
                        "sender_id": "coordinator",
                    })
                )
                continue

            # Query list of connected peers
            if msg_type in (SignalingMessageType.PEERS_LIST, "get_peers"):
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.PEERS_LIST,
                        "peers": signaling_manager.get_connected_peers(),
                    })
                )
                continue

            # Relay messages: offer, answer, ice_candidate, etc.
            target_id = data.get("target_id")
            if not target_id or not isinstance(target_id, str):
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.MISSING_TARGET_ID,
                        "message": f"Message of type '{msg_type}' requires a non-empty string 'target_id'",
                    })
                )
                continue

            if len(target_id) > 128 or "\n" in target_id or "\r" in target_id:
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.MALFORMED_MESSAGE,
                        "message": "Malformed target_id format",
                    })
                )
                continue

            if target_id == registered_peer_id:
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.MALFORMED_MESSAGE,
                        "message": "Cannot send signaling messages to self",
                    })
                )
                continue

            # Ensure sender_id cannot be spoofed
            data["sender_id"] = registered_peer_id

            try:
                await signaling_manager.send_to(target_id, data)
                logger.debug(
                    "Relayed '%s' message from '%s' to '%s'",
                    msg_type,
                    registered_peer_id,
                    target_id,
                )
            except PeerNotFoundError:
                await websocket.send_text(
                    json.dumps({
                        "type": SignalingMessageType.ERROR,
                        "code": SignalingErrorCode.TARGET_NOT_FOUND,
                        "target_id": target_id,
                        "message": (
                            f"Target peer '{target_id}' is not connected to signaling gateway"
                        ),
                    })
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for peer '%s'", registered_peer_id)
    except Exception as exc:
        logger.exception(
            "Unexpected error in signaling loop for peer '%s': %s",
            registered_peer_id,
            exc,
        )
    finally:
        # Guaranteed cleanup
        removed = await signaling_manager.unregister(registered_peer_id, websocket)
        if removed:
            await signaling_manager.broadcast(
                {"type": SignalingMessageType.PEER_LEFT, "peer_id": registered_peer_id},
                exclude_id=registered_peer_id,
            )
