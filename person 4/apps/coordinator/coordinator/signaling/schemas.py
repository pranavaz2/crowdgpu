"""
WebRTC Signaling Schemas.

Defines the message structure and types for coordinator WebSocket signaling.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SignalingMessageType(StrEnum):
    """Supported signaling message types."""

    REGISTER = "register"
    REGISTERED = "registered"
    OFFER = "offer"
    ANSWER = "answer"
    ICE_CANDIDATE = "ice_candidate"
    PING = "ping"
    PONG = "pong"
    PEERS_LIST = "peers_list"
    PEER_JOINED = "peer_joined"
    PEER_LEFT = "peer_left"
    ERROR = "error"


class SignalingErrorCode(StrEnum):
    """Standard signaling error codes."""

    PEER_ALREADY_CONNECTED = "PEER_ALREADY_CONNECTED"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    MALFORMED_MESSAGE = "MALFORMED_MESSAGE"
    UNAUTHORIZED = "UNAUTHORIZED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    MISSING_TARGET_ID = "MISSING_TARGET_ID"


class SignalingMessage(BaseModel):
    """Base schema for signaling envelope messages."""

    type: SignalingMessageType | str = Field(..., description="Message type")
    sender_id: str | None = Field(default=None, description="Originating peer or client ID")
    target_id: str | None = Field(default=None, description="Recipient peer or client ID")
    payload: dict[str, Any] | None = Field(default=None, description="SDP, candidate, or payload")
    code: str | None = Field(default=None, description="Error code if type is error")
    message: str | None = Field(
        default=None,
        description="Human readable message or error description",
    )


class IceServerEntry(BaseModel):
    """ICE server configuration entry (STUN / TURN)."""

    urls: list[str] = Field(..., description="List of STUN or TURN URLs")
    username: str | None = Field(default=None, description="Optional TURN username")
    credential: str | None = Field(default=None, description="Optional TURN credential")


class IceServersResponse(BaseModel):
    """Response returned by GET /api/v1/signaling/ice-servers."""

    ice_servers: list[IceServerEntry] = Field(default_factory=list)


class ConnectedPeersResponse(BaseModel):
    """Response returned by GET /api/v1/signaling/peers."""

    connected_peers: list[str] = Field(default_factory=list)
    count: int = Field(default=0)
