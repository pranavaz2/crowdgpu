"""
Job Service layer.

Encapsulates all business logic for job submission, query, cancellation,
scheduler integration, and worker status/result updates.
"""

import uuid
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.core.metrics import (
    JOBS_COMPLETED_TOTAL,
    JOBS_FAILED_TOTAL,
    JOBS_SUBMITTED_TOTAL,
    QUEUED_JOBS,
    RUNNING_JOBS,
    SCHEDULER_ASSIGNMENTS_TOTAL,
)
from coordinator.database.models import Job, Peer, User
from coordinator.jobs.exceptions import (
    InvalidJobTransitionError,
    JobNotFoundError,
    UnauthorizedJobAccessError,
)
from coordinator.jobs.schemas import JobCreate, JobResultSubmit, JobStatusUpdate
from coordinator.jobs.state_machine import JobStatus, transition_job_status
from coordinator.peers.exceptions import OwnerNotFoundError, PeerNotFoundError
from coordinator.scheduler.scheduler import Scheduler

logger = logging.getLogger(__name__)


class JobService:
    """Service handling job lifecycle, scheduling orchestration, and database operations."""

    @staticmethod
    async def submit_job(
        session: AsyncSession,
        owner_id: uuid.UUID,
        data: JobCreate,
    ) -> Job:
        """
        Submit a new job, validate owner, record initial QUEUED state,
        and trigger an immediate scheduling pass.
        """
        owner = await session.get(User, owner_id)
        if owner is None:
            raise OwnerNotFoundError(owner_id)

        reqs = dict(data.requirements or {})
        reqs["required_vram_mb"] = data.required_vram_mb

        job = Job(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name=data.name,
            command=data.command,
            requirements=reqs,
            status=JobStatus.QUEUED.value,
        )
        session.add(job)
        await session.commit()

        JOBS_SUBMITTED_TOTAL.inc()
        QUEUED_JOBS.inc()
        logger.info("Job %s (%s) submitted by owner %s", job.id, job.name, owner_id)

        # Trigger scheduler
        scheduler = Scheduler()
        scheduled_job = await scheduler.schedule_job(session, job.id)
        if scheduled_job and scheduled_job.status == JobStatus.ASSIGNED.value:
            QUEUED_JOBS.dec()
            SCHEDULER_ASSIGNMENTS_TOTAL.inc()

        # Re-fetch fresh state
        return await JobService.get_job(session, job.id)

    @staticmethod
    async def get_job(
        session: AsyncSession,
        job_id: uuid.UUID,
        owner_id: uuid.UUID | None = None,
    ) -> Job:
        """
        Retrieve a job by ID.
        If owner_id is specified, strictly verifies ownership (returns 404 if mismatch
        to avoid leaking job existence).
        """
        stmt = select(Job).where(Job.id == job_id)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job is None:
            raise JobNotFoundError(job_id)

        if owner_id is not None and job.owner_id != owner_id:
            # Ownership mismatch: treat as not found
            raise JobNotFoundError(job_id)

        return job

    @staticmethod
    async def list_jobs(
        session: AsyncSession,
        owner_id: uuid.UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        """List jobs belonging to the specified owner, with optional status filter."""
        stmt = select(Job).where(Job.owner_id == owner_id)
        if status:
            stmt = stmt.where(Job.status == status.upper())
        stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def cancel_job(
        session: AsyncSession,
        job_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Job:
        """
        Cancel a QUEUED job.
        Raises InvalidJobTransitionError if already matching, running, or finished.
        """
        job = await JobService.get_job(session, job_id, owner_id=owner_id)

        if job.status != JobStatus.QUEUED.value:
            raise InvalidJobTransitionError(
                current_status=job.status,
                target_status=JobStatus.CANCELLED.value,
                reason="Only jobs in QUEUED status can be cancelled",
            )

        transition_job_status(job, JobStatus.CANCELLED, actor="client")
        QUEUED_JOBS.dec()
        await session.commit()

        logger.info("Job %s cancelled by owner %s", job.id, owner_id)
        return await JobService.get_job(session, job.id)

    @staticmethod
    async def get_next_job_for_peer(
        session: AsyncSession,
        peer_id: uuid.UUID,
    ) -> Job | None:
        """
        Retrieve the next pending ASSIGNED job for a worker peer.
        """
        peer = await session.get(Peer, peer_id)
        if peer is None:
            raise PeerNotFoundError(peer_id)

        stmt = (
            select(Job)
            .where(
                Job.assigned_peer_id == peer_id,
                Job.status == JobStatus.ASSIGNED.value,
            )
            .order_by(Job.created_at.asc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def worker_update_status(
        session: AsyncSession,
        job_id: uuid.UUID,
        peer_id: uuid.UUID,
        data: JobStatusUpdate,
    ) -> Job:
        """
        Update execution status from worker (RUNNING or FAILED).
        Verifies that caller is the assigned peer node.
        """
        job = await session.get(Job, job_id)
        if job is None:
            raise JobNotFoundError(job_id)

        if job.assigned_peer_id != peer_id:
            raise UnauthorizedJobAccessError(
                f"Peer '{peer_id}' is not the assigned provider for job '{job_id}'"
            )

        target = JobStatus(data.status.upper())
        prev_status = job.status
        transition_job_status(job, target, actor="worker", error=data.error)

        if target == JobStatus.RUNNING and prev_status != JobStatus.RUNNING.value:
            RUNNING_JOBS.inc()
        elif target == JobStatus.FAILED:
            if prev_status == JobStatus.RUNNING.value:
                RUNNING_JOBS.dec()
            JOBS_FAILED_TOTAL.inc()
            # Free peer
            peer = await session.get(Peer, peer_id)
            if peer:
                peer.status = "available"

        await session.commit()
        logger.info("Job %s status updated to %s by peer %s", job.id, target.value, peer_id)
        return await JobService.get_job(session, job.id)

    @staticmethod
    async def worker_submit_result(
        session: AsyncSession,
        job_id: uuid.UUID,
        peer_id: uuid.UUID,
        data: JobResultSubmit,
    ) -> Job:
        """
        Submit completed workload result from worker.
        Transitions job to COMPLETED, stores result metadata, and frees peer.
        """
        job = await session.get(Job, job_id)
        if job is None:
            raise JobNotFoundError(job_id)

        if job.assigned_peer_id != peer_id:
            raise UnauthorizedJobAccessError(
                f"Peer '{peer_id}' is not the assigned provider for job '{job_id}'"
            )

        prev_status = job.status
        transition_job_status(job, JobStatus.COMPLETED, actor="worker")
        job.result = data.model_dump()

        if prev_status == JobStatus.RUNNING.value:
            RUNNING_JOBS.dec()
        JOBS_COMPLETED_TOTAL.inc()

        # Free peer back to available
        peer = await session.get(Peer, peer_id)
        if peer:
            peer.status = "available"

        await session.commit()
        logger.info("Job %s completed successfully by peer %s", job.id, peer_id)
        return await JobService.get_job(session, job.id)
