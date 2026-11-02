"""
Worker API endpoints — /api/v1/workers.

Provides worker-specific polling and alias routes for peer worker nodes.
Reuses the existing PeerService for registration and heartbeat without duplicating models.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.database.session import get_db
from coordinator.jobs.schemas import JobResponse
from coordinator.jobs.service import JobService
from coordinator.peers.exceptions import OwnerNotFoundError, PeerNotFoundError
from coordinator.peers.schemas import (
    PeerHeartbeatRequest,
    PeerRegisterRequest,
    PeerResponse,
)
from coordinator.peers.service import PeerService

router = APIRouter(prefix="/workers", tags=["Workers"])


@router.get(
    "/{peer_id}/jobs/next",
    response_model=JobResponse | None,
    status_code=status.HTTP_200_OK,
    summary="Worker poll for assigned job",
)
async def get_next_job_for_worker(
    peer_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse | Response:
    """
    Called by a worker daemon to fetch its next pending ASSIGNED workload.
    Returns HTTP 200 with Job details if an assigned workload is ready,
    or HTTP 204 No Content if no jobs are currently pending.
    """
    try:
        job = await JobService.get_next_job_for_peer(db, peer_id=peer_id)
        if job is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return JobResponse.model_validate(job)
    except PeerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/register",
    response_model=PeerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register worker (alias to peer registration)",
)
async def register_worker(
    payload: PeerRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PeerResponse:
    """Alias to POST /api/v1/peers reusing existing registration logic."""
    try:
        peer = await PeerService.register_peer(db, payload)
        return PeerResponse.model_validate(peer)
    except OwnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{peer_id}/heartbeat",
    response_model=PeerResponse,
    status_code=status.HTTP_200_OK,
    summary="Worker heartbeat (alias to peer heartbeat)",
)
async def worker_heartbeat(
    peer_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: PeerHeartbeatRequest | None = None,
) -> PeerResponse:
    """Alias to PATCH /api/v1/peers/{peer_id}/heartbeat."""
    try:
        data = payload or PeerHeartbeatRequest()
        peer = await PeerService.heartbeat(db, peer_id, data)
        return PeerResponse.model_validate(peer)
    except PeerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
