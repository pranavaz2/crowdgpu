"""
Authentication and identity dependencies.

Provides header-based identity extraction for users (X-User-Id) and worker peers (X-Peer-Id).
Designed to be seamlessly swappable with JWT / OAuth bearer tokens in later phases.
"""

import uuid
from typing import Annotated

from fastapi import Header, HTTPException, status


async def get_current_user_id(
    x_user_id: Annotated[str | None, Header(description="UUID of the authenticated user")] = None,
) -> uuid.UUID:
    """Extract and validate the client User UUID from headers."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required header: X-User-Id",
        )
    try:
        return uuid.UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Malformed X-User-Id header: '{x_user_id}' is not a valid UUID",
        ) from exc


async def get_current_peer_id(
    x_peer_id: Annotated[str | None, Header(description="UUID of the worker peer node")] = None,
) -> uuid.UUID:
    """Extract and validate the worker Peer UUID from headers."""
    if not x_peer_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required header: X-Peer-Id",
        )
    try:
        return uuid.UUID(x_peer_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Malformed X-Peer-Id header: '{x_peer_id}' is not a valid UUID",
        ) from exc
