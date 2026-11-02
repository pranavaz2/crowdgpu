"""
Stale Peer and Job Timeout Reaper.

Periodically detects unresponsive peers, marks them offline, and requeues
or fails their assigned workloads to prevent orphan jobs.
"""

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from coordinator.config import settings
from coordinator.database.models import Job, Peer
from coordinator.jobs.state_machine import JobStatus, transition_job_status

logger = logging.getLogger(__name__)


async def reap_stale_peers_and_jobs(session: AsyncSession) -> dict[str, int]:
    """
    Detect stale peers and unacknowledged jobs, cleaning up resources.

    Returns:
        Summary dict of {"peers_marked_offline": int, "jobs_requeued": int, "jobs_failed": int}
    """
    now = datetime.datetime.now(datetime.UTC)
    heartbeat_cutoff = now - datetime.timedelta(seconds=settings.heartbeat_timeout_seconds)
    ack_cutoff = now - datetime.timedelta(seconds=settings.ack_timeout_seconds)

    peers_offline_count = 0
    jobs_requeued_count = 0
    jobs_failed_count = 0

    # 1. Identify and mark stale peers offline
    stale_peers_stmt = select(Peer).where(
        Peer.status != "offline",
        Peer.last_seen_at.is_not(None),
        Peer.last_seen_at < heartbeat_cutoff,
    )
    result = await session.execute(stale_peers_stmt)
    stale_peers = result.scalars().all()

    for peer in stale_peers:
        peer.status = "offline"
        peers_offline_count += 1
        logger.warning(
            "Peer %s (%s) heartbeat timed out. Marked offline.",
            peer.id,
            peer.hostname,
        )

        # Handle active jobs on this now-offline peer
        active_jobs_stmt = select(Job).where(
            Job.assigned_peer_id == peer.id,
            Job.status.in_([JobStatus.ASSIGNED.value, JobStatus.RUNNING.value]),
        )
        jobs_res = await session.execute(active_jobs_stmt)
        for job in jobs_res.scalars().all():
            if (
                job.status == JobStatus.ASSIGNED.value
                and job.attempt_count < settings.max_job_attempts
            ):
                job.assigned_peer_id = None
                transition_job_status(job, JobStatus.QUEUED, actor="reaper")
                jobs_requeued_count += 1
                logger.info("Job %s requeued after unacknowledged peer %s timed out", job.id, peer.id)
            else:
                transition_job_status(
                    job,
                    JobStatus.FAILED,
                    actor="reaper",
                    error="Assigned peer became unresponsive / heartbeat timed out",
                )
                jobs_failed_count += 1
                logger.warning("Job %s failed: peer %s unresponsive", job.id, peer.id)

    # 2. Requeue or fail unacknowledged ASSIGNED jobs that exceeded ACK_TIMEOUT
    unack_jobs_stmt = select(Job).where(
        Job.status == JobStatus.ASSIGNED.value,
        Job.updated_at < ack_cutoff,
    )
    unack_res = await session.execute(unack_jobs_stmt)
    for job in unack_res.scalars().all():
        if job.attempt_count < settings.max_job_attempts:
            job.assigned_peer_id = None
            transition_job_status(job, JobStatus.QUEUED, actor="reaper")
            jobs_requeued_count += 1
            logger.info("Job %s requeued due to acknowledgment timeout", job.id)
        else:
            transition_job_status(
                job,
                JobStatus.FAILED,
                actor="reaper",
                error="Worker acknowledgment timed out",
            )
            jobs_failed_count += 1

    await session.commit()
    return {
        "peers_marked_offline": peers_offline_count,
        "jobs_requeued": jobs_requeued_count,
        "jobs_failed": jobs_failed_count,
    }
