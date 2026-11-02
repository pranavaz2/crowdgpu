"""
Authentication and identity dependencies.

Provides authenticated identity extraction for users (X-User-Id, Bearer token) and worker peers (X-Peer-Id, X-Peer-Token).
Enforces cryptographic token verification in production while allowing safe local development fallbacks.
"""

import hashlib
import hmac
import logging
import uuid
from typing import Annotated

from fastapi import Header, HTTPException, status

from coordinator.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cryptographic Token Helpers (HMAC-SHA256)
# ---------------------------------------------------------------------------

def generate_worker_token(peer_id: uuid.UUID) -> str:
    """Generate a deterministic HMAC-SHA256 authentication token for a registered peer."""
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        f"worker-auth:{peer_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_worker_token(peer_id: uuid.UUID, token: str) -> bool:
    """Verify in constant time that a worker token is authentic for the given peer ID."""
    if not token or not isinstance(token, str):
        return False
    expected = generate_worker_token(peer_id)
    return hmac.compare_digest(expected, token.strip())


def generate_user_token(user_id: uuid.UUID) -> str:
    """Generate a deterministic HMAC-SHA256 authentication token for a user."""
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        f"user-auth:{user_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_user_token(user_id: uuid.UUID, token: str) -> bool:
    """Verify in constant time that a user token is authentic for the given user ID."""
    if not token or not isinstance(token, str):
        return False
    expected = generate_user_token(user_id)
    return hmac.compare_digest(expected, token.strip())


def _extract_bearer_token(
    token_header: str | None,
    auth_header: str | None,
) -> str | None:
    """Extract a raw token string from either a dedicated token header or Authorization: Bearer <token>."""
    if token_header and token_header.strip():
        return token_header.strip()
    if auth_header and auth_header.strip():
        parts = auth_header.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return auth_header.strip()
    return None


# ---------------------------------------------------------------------------
# User Authentication Dependency
# ---------------------------------------------------------------------------

async def get_current_user_id(
    x_user_id: Annotated[str | None, Header(description="UUID of the authenticated user")] = None,
    x_user_token: Annotated[str | None, Header(description="Cryptographic user authentication token")] = None,
    authorization: Annotated[str | None, Header(description="Bearer authorization token")] = None,
) -> uuid.UUID:
    """Extract and validate the client User UUID.

    In production mode:
      - X-User-Id is strictly required.
      - A cryptographic user token (X-User-Token or Authorization: Bearer <token>) is mandatory.
      - Plain header spoofing without the corresponding HMAC token is rejected (401/403).

    In development mode:
      - If X-User-Id is omitted and settings.demo_auth_enabled is True, falls back to demo_user_id.
      - If a token is supplied, it is validated for integrity.
    """
    token = _extract_bearer_token(x_user_token, authorization)
    is_production = settings.environment.lower() == "production"

    if not x_user_id:
        if settings.demo_auth_enabled and not is_production:
            return uuid.UUID(settings.demo_user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required header: X-User-Id",
        )

    try:
        user_uuid = uuid.UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Malformed X-User-Id header: '{x_user_id}' is not a valid UUID",
        ) from exc

    if is_production:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User authentication token required in production (Authorization: Bearer <token> or X-User-Token)",
            )
        if not verify_user_token(user_uuid, token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user authentication credential",
            )
    else:
        # Development mode: if token is provided, verify it; otherwise permit demo header
        if token and not verify_user_token(user_uuid, token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid user authentication credential",
            )

    return user_uuid


# ---------------------------------------------------------------------------
# Worker Peer Authentication Dependencies
# ---------------------------------------------------------------------------

async def get_current_peer_id(
    x_peer_id: Annotated[str | None, Header(description="UUID of the worker peer node")] = None,
    x_worker_id: Annotated[str | None, Header(description="Alias header for worker peer node UUID")] = None,
    x_peer_token: Annotated[str | None, Header(description="Worker authentication token")] = None,
    authorization: Annotated[str | None, Header(description="Bearer authorization token")] = None,
) -> uuid.UUID:
    """Extract and cryptographically authenticate the worker Peer UUID from headers.

    In production mode:
      - X-Peer-Id (or X-Worker-ID) is strictly required.
      - A valid cryptographic worker token bound to the peer ID is mandatory.
      - Unauthorized result submission or job status updates are rejected (401/403).
    """
    peer_raw = x_peer_id or x_worker_id
    if not peer_raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required header: X-Peer-Id or X-Worker-ID",
        )

    try:
        peer_id = uuid.UUID(peer_raw)
    except ValueError as exc:
        if x_worker_id and not x_peer_id:
            peer_id = uuid.uuid5(uuid.NAMESPACE_DNS, peer_raw)
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Malformed peer ID header: '{peer_raw}' is not a valid UUID",
            ) from exc

    token = _extract_bearer_token(x_peer_token, authorization)
    is_production = settings.environment.lower() == "production"

    if is_production:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Worker authentication token required in production (Authorization: Bearer <token> or X-Peer-Token)",
            )
        if not verify_worker_token(peer_id, token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid worker authentication token for peer '{peer_id}'",
            )
    else:
        # Development mode: if token is supplied, verify it; otherwise allow local dev diagnostics
        if token and not verify_worker_token(peer_id, token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid worker authentication token for peer '{peer_id}'",
            )

    return peer_id


async def get_optional_peer_id(
    x_peer_id: Annotated[str | None, Header(description="UUID of the worker peer node")] = None,
    x_worker_id: Annotated[str | None, Header(description="Alias header for worker peer node UUID")] = None,
    x_peer_token: Annotated[str | None, Header(description="Worker authentication token")] = None,
    authorization: Annotated[str | None, Header(description="Bearer authorization token")] = None,
) -> uuid.UUID | None:
    """Extract optional worker Peer UUID, verifying token credentials if present or in production."""
    peer_raw = x_peer_id or x_worker_id
    is_production = settings.environment.lower() == "production"

    if not peer_raw:
        if is_production:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing required header in production: X-Peer-Id or X-Worker-ID",
            )
        return None

    try:
        peer_id = uuid.UUID(peer_raw)
    except ValueError as exc:
        if x_worker_id and not x_peer_id:
            peer_id = uuid.uuid5(uuid.NAMESPACE_DNS, peer_raw)
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Malformed peer ID header: '{peer_raw}' is not a valid UUID",
            ) from exc

    token = _extract_bearer_token(x_peer_token, authorization)

    if is_production:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Worker authentication token required in production",
            )
        if not verify_worker_token(peer_id, token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid worker authentication token for peer '{peer_id}'",
            )
    else:
        if token and not verify_worker_token(peer_id, token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid worker authentication token for peer '{peer_id}'",
            )

    return peer_id


def verify_peer_authorization(target_peer_id: uuid.UUID, caller_peer_id: uuid.UUID | None) -> None:
    """Verify that a worker operation cannot be performed on behalf of an arbitrary peer."""
    if caller_peer_id is not None and caller_peer_id != target_peer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Cannot perform operation for peer '{target_peer_id}' using identity '{caller_peer_id}'",
        )

