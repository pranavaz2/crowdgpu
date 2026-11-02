"""
API Router for job management operations.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.database.session import get_db
from coordinator.jobs.schemas import (
    JobAssignRequest,
    JobResponse,
    JobStatusUpdateRequest,
    JobSubmitRequest,
)
from coordinator.jobs.service import JobService

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)

SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new job",
)
async def submit_job(
    request: JobSubmitRequest,
    db: SessionDep,
) -> JobResponse:
    """Submit a new compute job to the coordinator."""
    from fastapi import HTTPException
    from coordinator.peers.exceptions import OwnerNotFoundError
    try:
        job = await JobService.submit_job(db, request)
    except OwnerNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return JobResponse.model_validate(job)


@router.get(
    "",
    response_model=list[JobResponse],
    summary="List all jobs",
)
async def list_jobs(
    db: SessionDep,
    owner_id: uuid.UUID | None = Query(None, description="Filter jobs by owner ID"),
    status: str | None = Query(None, description="Filter jobs by status"),
    assigned_peer_id: uuid.UUID | None = Query(None, description="Filter jobs by assigned peer ID"),
) -> list[JobResponse]:
    """Retrieve all submitted jobs, optionally filtering by owner, status, or assigned peer."""
    jobs = await JobService.list_jobs(db, owner_id=owner_id, status=status, assigned_peer_id=assigned_peer_id)
    return [JobResponse.model_validate(job) for job in jobs]


@router.post(
    "/schedule",
    response_model=JobResponse | None,
    summary="Schedule oldest pending job to first available peer",
)
async def schedule_job(
    db: SessionDep,
) -> JobResponse | None:
    """Evaluate pending jobs and assign the oldest to an available peer."""
    job = await JobService.schedule_next_pending(db)
    if not job:
        return None
    return JobResponse.model_validate(job)


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get a specific job",
)
async def get_job(
    job_id: uuid.UUID,
    db: SessionDep,
) -> JobResponse:
    """Retrieve details for a specific job."""
    job = await JobService.get_job(db, job_id)
    return JobResponse.model_validate(job)


@router.post(
    "/{job_id}/assign",
    response_model=JobResponse,
    summary="Assign job to a peer",
)
async def assign_job(
    job_id: uuid.UUID,
    request: JobAssignRequest,
    db: SessionDep,
) -> JobResponse:
    """Assign a pending compute job to a specific provider peer."""
    job = await JobService.assign_job(db, job_id, request.peer_id)
    return JobResponse.model_validate(job)


@router.patch(
    "/{job_id}/status",
    response_model=JobResponse,
    summary="Update job execution status",
)
async def update_job_status(
    job_id: uuid.UUID,
    request: JobStatusUpdateRequest,
    db: SessionDep,
) -> JobResponse:
    """Update execution lifecycle status of a job."""
    job = await JobService.update_job_status(db, job_id, request.status)
    return JobResponse.model_validate(job)
