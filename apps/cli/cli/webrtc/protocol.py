"""
CrowdGPU P2P Data-Channel Protocol.

Defines the direct peer-to-peer payload format and verification rules:
- Structured JSON envelopes with UUID request IDs
- Cryptographic SHA-256 hash integrity checks
- Direct acknowledgement matching
- No arbitrary command execution
"""

from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from typing import Any

PROTOCOL_VERSION = "crowdgpu-p2p/1.0"


def canonical_json_bytes(data: Any) -> bytes:
    """Produce deterministic UTF-8 bytes for cryptographic hashing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_sha256(data: Any) -> str:
    """Compute SHA-256 hex digest of a Python dictionary or primitive."""
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


def create_p2p_message(
    sender_id: str,
    message_type: str = "p2p_data_sync",
    payload: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Create a structured P2P message envelope with SHA-256 hash."""
    req_id = request_id or f"req-{uuid.uuid4().hex[:12]}"
    now = datetime.datetime.now(datetime.UTC).isoformat()
    data = payload if payload is not None else {"status": "ok", "message": "P2P Data Channel Test"}
    payload_hash = compute_sha256(data)

    return {
        "protocol": PROTOCOL_VERSION,
        "request_id": req_id,
        "sender_id": sender_id,
        "type": message_type,
        "timestamp": now,
        "payload": data,
        "payload_sha256": payload_hash,
    }


def verify_p2p_message(raw_msg: str | dict[str, Any]) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Validate a received P2P message envelope and verify payload SHA-256 integrity.

    Returns:
        (is_valid, description_or_reason, parsed_envelope)
    """
    if isinstance(raw_msg, str):
        try:
            msg = json.loads(raw_msg)
        except json.JSONDecodeError as exc:
            return False, f"Malformed JSON: {exc}", None
    elif isinstance(raw_msg, dict):
        msg = raw_msg
    else:
        return False, "Payload must be a JSON string or dict", None

    if not isinstance(msg, dict):
        return False, "Message root must be an object", None

    # Protocol check
    if msg.get("protocol") != PROTOCOL_VERSION:
        return False, f"Unsupported protocol '{msg.get('protocol')}'", msg

    req_id = msg.get("request_id")
    if not req_id or not isinstance(req_id, str):
        return False, "Missing or invalid 'request_id'", msg

    expected_hash = msg.get("payload_sha256")
    if not expected_hash:
        return False, "Missing 'payload_sha256' cryptographic hash", msg

    payload = msg.get("payload")
    if payload is None:
        return False, "Missing 'payload' body", msg

    actual_hash = compute_sha256(payload)
    if actual_hash != expected_hash:
        return (
            False,
            f"Integrity check failed: expected {expected_hash}, calculated {actual_hash}",
            msg,
        )

    return True, "Integrity verified", msg


def create_p2p_ack(
    receiver_id: str,
    request_id: str,
    verified_hash: str,
    latency_ms: float = 0.0,
    status: str = "verified",
) -> dict[str, Any]:
    """Create a structured acknowledgement referencing the original request ID and verified hash."""
    return {
        "protocol": PROTOCOL_VERSION,
        "type": "ack",
        "response_to": request_id,
        "receiver_id": receiver_id,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "status": status,
        "verified_sha256": verified_hash,
        "latency_ms": round(latency_ms, 2),
    }


def verify_p2p_ack(
    raw_ack: str | dict[str, Any],
    expected_request_id: str,
    expected_hash: str,
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Validate that an acknowledgement correctly matches the expected request ID and hash.
    """
    if isinstance(raw_ack, str):
        try:
            ack = json.loads(raw_ack)
        except json.JSONDecodeError as exc:
            return False, f"Malformed JSON in ACK: {exc}", None
    elif isinstance(raw_ack, dict):
        ack = raw_ack
    else:
        return False, "ACK must be a JSON string or dict", None

    if ack.get("type") != "ack":
        return False, f"Expected message type 'ack', got '{ack.get('type')}'", ack

    if ack.get("response_to") != expected_request_id:
        return (
            False,
            f"ACK mismatch: expected response_to '{expected_request_id}', got '{ack.get('response_to')}'",
            ack,
        )

    if ack.get("verified_sha256") != expected_hash:
        return (
            False,
            f"ACK hash mismatch: expected '{expected_hash}', got '{ack.get('verified_sha256')}'",
            ack,
        )

    return True, "ACK verified successfully", ack
