"""
Job API endpoints — /api/v1/jobs.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.core.auth import get_current_peer_id, get_current_user_id
from coordinator.database.session import get_db
from coordinator.jobs.exceptions import (
    InvalidJobTransitionError,
    JobNotFoundError,
    UnauthorizedJobAccessError,
)
from coordinator.jobs.schemas import (
    JobCreate,
    JobResponse,
    JobResultSubmit,
    JobStatusUpdate,
)
from coordinator.jobs.service import JobService
from coordinator.peers.exceptions import OwnerNotFoundError

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new computational GPU job",
)
async def submit_job(
    payload: JobCreate,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    """
    Submit a computational workload.
    The job is persisted in QUEUED state, and an immediate scheduler matching pass is triggered.
    If a suitable GPU provider peer is available, it is reserved atomically.
    """
    try:
        job = await JobService.submit_job(db, owner_id=user_id, data=payload)
        return JobResponse.model_validate(job)
    except OwnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[JobResponse],
    status_code=status.HTTP_200_OK,
    summary="List caller's submitted jobs",
)
async def list_jobs(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    job_status: Annotated[str | None, Query(alias="status", description="Filter by job status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobResponse]:
    """Retrieve all jobs submitted by the authenticated user with optional filtering."""
    jobs = await JobService.list_jobs(
        db,
        owner_id=user_id,
        status=job_status,
        limit=limit,
        offset=offset,
    )
    return [JobResponse.model_validate(j) for j in jobs]


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve job details",
)
async def get_job(
    job_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    """Retrieve status and metadata of a specific job owned by the caller."""
    try:
        job = await JobService.get_job(db, job_id=job_id, owner_id=user_id)
        return JobResponse.model_validate(job)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel a queued job",
)
async def cancel_job(
    job_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    """Cancel a job currently in QUEUED state. Rejects cancellation of active/finished jobs."""
    try:
        job = await JobService.cancel_job(db, job_id=job_id, owner_id=user_id)
        return JobResponse.model_validate(job)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidJobTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{job_id}/status",
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
    summary="Report job execution status from worker",
)
async def update_job_status(
    job_id: uuid.UUID,
    payload: JobStatusUpdate,
    peer_id: Annotated[uuid.UUID, Depends(get_current_peer_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    """Allows the assigned worker peer to update job execution state (RUNNING or FAILED)."""
    try:
        job = await JobService.worker_update_status(
            db,
            job_id=job_id,
            peer_id=peer_id,
            data=payload,
        )
        return JobResponse.model_validate(job)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedJobAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except InvalidJobTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{job_id}/result",
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit completed job result from worker",
)
async def submit_job_result(
    job_id: uuid.UUID,
    payload: JobResultSubmit,
    peer_id: Annotated[uuid.UUID, Depends(get_current_peer_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    """Allows the assigned worker peer to submit output and mark the workload COMPLETED."""
    try:
        job = await JobService.worker_submit_result(
            db,
            job_id=job_id,
            peer_id=peer_id,
            data=payload,
        )
        return JobResponse.model_validate(job)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnauthorizedJobAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except InvalidJobTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
