"""
Job service layer.

Encapsulates business logic and database persistence for job submission,
retrieval, and listing.
"""

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.database.models import Job, Peer, User
from coordinator.jobs.exceptions import JobNotFoundError
from coordinator.jobs.schemas import JobSubmitRequest
from coordinator.peers.exceptions import OwnerNotFoundError, PeerNotFoundError


class JobService:
    """Service handling job lifecycle and database operations."""

    @staticmethod
    async def submit_job(
        session: AsyncSession,
        data: JobSubmitRequest,
    ) -> Job:
        """
        Submit a new compute job.
        
        Verifies the owner exists before creation.
        """
        owner = await session.get(User, data.owner_id)
        if not owner:
            raise OwnerNotFoundError(data.owner_id)

        job = Job(
            id=uuid.uuid4(),
            owner_id=data.owner_id,
            docker_image=data.docker_image,
            command=data.command,
            status="pending",
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job

    @staticmethod
    async def list_jobs(
        session: AsyncSession,
        owner_id: uuid.UUID | None = None,
        status: str | None = None,
        assigned_peer_id: uuid.UUID | None = None,
    ) -> Sequence[Job]:
        """
        List all jobs, optionally filtered by owner_id, status, or assigned_peer_id.
        """
        stmt = select(Job).order_by(Job.created_at.desc())
        
        if owner_id:
            stmt = stmt.where(Job.owner_id == owner_id)
        if status:
            stmt = stmt.where(Job.status == status)
        if assigned_peer_id:
            stmt = stmt.where(Job.assigned_peer_id == assigned_peer_id)
            
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_job(
        session: AsyncSession,
        job_id: uuid.UUID,
    ) -> Job:
        """
        Retrieve a job by its ID.
        """
        job = await session.get(Job, job_id)
        if not job:
            raise JobNotFoundError(job_id)
        return job

    @staticmethod
    async def assign_job(
        session: AsyncSession,
        job_id: uuid.UUID,
        peer_id: uuid.UUID,
    ) -> Job:
        """
        Assign a pending job to a specific peer and set peer status to busy.
        """
        job = await JobService.get_job(session, job_id)
        peer = await session.get(Peer, peer_id)
        if not peer:
            raise PeerNotFoundError(peer_id)

        job.assigned_peer_id = peer_id
        job.status = "assigned"
        peer.status = "busy"

        await session.commit()
        await session.refresh(job)
        return job

    @staticmethod
    async def update_job_status(
        session: AsyncSession,
        job_id: uuid.UUID,
        new_status: str,
    ) -> Job:
        """
        Update a job's execution status (e.g. running, completed, failed).
        Frees assigned peer back to available when job finishes.
        """
        job = await JobService.get_job(session, job_id)
        job.status = new_status

        if new_status in ("completed", "failed") and job.assigned_peer_id:
            peer = await session.get(Peer, job.assigned_peer_id)
            if peer:
                peer.status = "available"

        await session.commit()
        await session.refresh(job)
        return job

    @staticmethod
    async def schedule_next_pending(
        session: AsyncSession,
    ) -> Job | None:
        """
        Scheduler loop iteration: find oldest pending job and assign to first available peer.
        """
        # Find oldest pending job
        stmt_job = (
            select(Job)
            .where(Job.status == "pending")
            .order_by(Job.created_at.asc())
            .limit(1)
        )
        res_job = await session.execute(stmt_job)
        job = res_job.scalar_one_or_none()
        if not job:
            return None

        # Find first available peer
        stmt_peer = (
            select(Peer)
            .where(Peer.status == "available")
            .order_by(Peer.last_seen_at.desc())
            .limit(1)
        )
        res_peer = await session.execute(stmt_peer)
        peer = res_peer.scalar_one_or_none()
        if not peer:
            return None

        job.assigned_peer_id = peer.id
        job.status = "assigned"
        peer.status = "busy"

        await session.commit()
        await session.refresh(job)
        return job
