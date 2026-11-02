"""
Coordinator Scheduler Engine.

Responsible for matching queued computational jobs to available GPU provider peers
based on VRAM compatibility, availability, and heuristic scoring.
"""

import datetime
import uuid
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from coordinator.config import settings
from coordinator.database.models import GpuCapability, Job, Peer
from coordinator.jobs.state_machine import JobStatus, transition_job_status
from coordinator.scheduler.scoring import (
    DefaultScoringStrategy,
    PeerCandidate,
    ScoringStrategy,
)

logger = logging.getLogger(__name__)


class Scheduler:
    """Intelligent GPU job matching and reservation engine."""

    def __init__(self, scoring_strategy: ScoringStrategy | None = None) -> None:
        self.scoring_strategy = scoring_strategy or DefaultScoringStrategy()

    async def discover_candidates(
        self,
        session: AsyncSession,
        required_vram_mb: int,
    ) -> list[PeerCandidate]:
        """
        Discover eligible provider peers that:
        1. Have lifecycle status 'available'.
        2. Have reported a heartbeat within HEARTBEAT_TIMEOUT_SECONDS.
        3. Do NOT currently hold an active job (ASSIGNED or RUNNING).
        4. Expose at least one GPU with vram_mb >= required_vram_mb.
        """
        now = datetime.datetime.now(datetime.UTC)
        cutoff = now - datetime.timedelta(seconds=settings.heartbeat_timeout_seconds)

        # Active jobs subquery to exclude busy peers
        active_jobs_subquery = (
            select(Job.assigned_peer_id)
            .where(
                Job.assigned_peer_id.is_not(None),
                Job.status.in_([JobStatus.ASSIGNED.value, JobStatus.RUNNING.value]),
            )
            .scalar_subquery()
        )

        stmt = (
            select(Peer)
            .options(selectinload(Peer.gpu_capabilities))
            .where(
                Peer.status == "available",
                Peer.last_seen_at >= cutoff,
                Peer.id.not_in(active_jobs_subquery),
            )
        )

        result = await session.execute(stmt)
        peers = result.scalars().all()

        candidates: list[PeerCandidate] = []
        for peer in peers:
            # Find the highest VRAM among this peer's GPUs
            matching_gpus = [g for g in peer.gpu_capabilities if g.vram_mb >= required_vram_mb]
            if not matching_gpus:
                continue

            best_gpu = max(matching_gpus, key=lambda g: g.vram_mb)
            candidates.append(
                PeerCandidate(
                    peer_id=peer.id,
                    hostname=peer.hostname,
                    status=peer.status,
                    last_seen_at=peer.last_seen_at,
                    max_vram_mb=best_gpu.vram_mb,
                    available_vram_mb=best_gpu.vram_mb,
                    compute_capability=best_gpu.compute_capability,
                )
            )

        return candidates

    def rank_candidates(
        self,
        candidates: list[PeerCandidate],
        required_vram_mb: int,
    ) -> list[tuple[PeerCandidate, float]]:
        """
        Score and rank candidate peers.
        Sorts descending by score; ties broken deterministically by peer UUID string.
        """
        scored = [
            (
                c,
                self.scoring_strategy.score(
                    c,
                    required_vram_mb,
                    settings.heartbeat_timeout_seconds,
                ),
            )
            for c in candidates
        ]
        # Sort by (-score, peer_id str)
        scored.sort(key=lambda item: (-item[1], str(item[0].peer_id)))
        return scored

    async def schedule_job(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
    ) -> Job | None:
        """
        Attempt to match and assign a specific QUEUED job.

        Atomic transaction:
        1. Lock Job row and transition QUEUED -> MATCHING.
        2. Discover compatible, available peer candidates.
        3. Score and rank candidates.
        4. Lock best peer row with FOR UPDATE SKIP LOCKED.
        5. Set peer.status = 'busy', assign to job, transition to ASSIGNED.
        6. If no candidates, requeue or fail job after max attempts.
        """
        job = await session.get(Job, job_id, with_for_update=True)
        if job is None or job.status != JobStatus.QUEUED.value:
            return job

        # 1. QUEUED -> MATCHING
        transition_job_status(job, JobStatus.MATCHING, actor="scheduler")
        await session.flush()

        req_vram = job.requirements.get("required_vram_mb", 0)
        candidates = await self.discover_candidates(session, req_vram)
        ranked = self.rank_candidates(candidates, req_vram)

        if not ranked:
            job.attempt_count += 1
            if job.attempt_count >= settings.max_job_attempts:
                transition_job_status(
                    job,
                    JobStatus.FAILED,
                    actor="scheduler",
                    error=f"No suitable GPU provider available with at least {req_vram} MB VRAM (after {job.attempt_count} attempts)",
                )
                logger.warning(
                    "Job %s failed scheduling: insufficient resources or no active peers",
                    job.id,
                )
            else:
                # Requeue to retry on next loop or peer heartbeat
                transition_job_status(job, JobStatus.QUEUED, actor="scheduler")
                logger.info("Job %s requeued for later scheduling attempt", job.id)

            await session.commit()
            return job

        # 2. Try reserving candidate peers in order of suitability
        assigned_peer: Peer | None = None
        for candidate, score in ranked:
            stmt = (
                select(Peer)
                .where(Peer.id == candidate.peer_id, Peer.status == "available")
                .with_for_update(skip_locked=True)
            )
            res = await session.execute(stmt)
            peer = res.scalar_one_or_none()
            if peer is not None:
                assigned_peer = peer
                break

        if assigned_peer is None:
            # Candidates were locked concurrently by other schedulers
            transition_job_status(job, JobStatus.QUEUED, actor="scheduler")
            await session.commit()
            return job

        # 3. Reserve peer atomically and assign job
        assigned_peer.status = "busy"
        job.assigned_peer_id = assigned_peer.id
        job.attempt_count += 1
        transition_job_status(job, JobStatus.ASSIGNED, actor="scheduler")
        await session.commit()

        logger.info(
            "Job %s successfully assigned to peer %s (%s)",
            job.id,
            assigned_peer.id,
            assigned_peer.hostname,
        )
        return job
