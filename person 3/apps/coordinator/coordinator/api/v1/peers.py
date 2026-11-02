"""
Peer API endpoints — /api/v1/peers.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.database.session import get_db
from coordinator.peers.exceptions import (
    InvalidPeerStateError,
    OwnerNotFoundError,
    PeerNotFoundError,
)
from coordinator.peers.schemas import (
    PeerHeartbeatRequest,
    PeerRegisterRequest,
    PeerResponse,
)
from coordinator.peers.service import PeerService

router = APIRouter(prefix="/peers", tags=["Peers"])


@router.post(
    "",
    response_model=PeerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new provider peer",
)
async def register_peer(
    payload: PeerRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PeerResponse:
    """
    Register a provider peer node with its initial GPU capabilities.

    - Validates that the referenced owner user exists.
    - Persists peer and GPU capabilities atomically.
    - Sets initial registration and heartbeat timestamps to server time.
    """
    try:
        peer = await PeerService.register_peer(db, payload)
        return PeerResponse.model_validate(peer)
    except OwnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidPeerStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{peer_id}",
    response_model=PeerResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve peer details and capabilities",
)
async def get_peer(
    peer_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PeerResponse:
    """
    Retrieve current status and hardware capabilities of a registered peer.
    """
    try:
        peer = await PeerService.get_peer(db, peer_id)
        return PeerResponse.model_validate(peer)
    except PeerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{peer_id}/heartbeat",
    response_model=PeerResponse,
    status_code=status.HTTP_200_OK,
    summary="Update peer heartbeat and status",
)
async def heartbeat(
    peer_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: PeerHeartbeatRequest | None = None,
) -> PeerResponse:
    """
    Record peer heartbeat using server-controlled timestamp.

    Optionally updates the peer status (e.g. 'available', 'busy').
    """
    try:
        data = payload or PeerHeartbeatRequest()
        peer = await PeerService.heartbeat(db, peer_id, data)
        return PeerResponse.model_validate(peer)
    except PeerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{peer_id}/deregister",
    response_model=PeerResponse,
    status_code=status.HTTP_200_OK,
    summary="Deregister a peer (mark offline)",
)
async def deregister_peer(
    peer_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PeerResponse:
    """
    Mark a peer as offline without hard-deleting the database record.
    """
    try:
        peer = await PeerService.deregister_peer(db, peer_id)
        return PeerResponse.model_validate(peer)
    except PeerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
