"""
Job State Machine.

Enforces unambiguous, deterministic lifecycle transitions for jobs:
QUEUED -> MATCHING -> ASSIGNED -> RUNNING -> COMPLETED / FAILED
and cancellation: QUEUED -> CANCELLED.
"""

import datetime
from enum import StrEnum

from coordinator.database.models.job import Job
from coordinator.jobs.exceptions import InvalidJobTransitionError


class JobStatus(StrEnum):
    """Lifecycle states of a CrowdGPU job."""

    QUEUED = "QUEUED"
    MATCHING = "MATCHING"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Allowed state transitions
ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.MATCHING, JobStatus.CANCELLED},
    JobStatus.MATCHING: {JobStatus.ASSIGNED, JobStatus.QUEUED, JobStatus.FAILED},
    JobStatus.ASSIGNED: {JobStatus.RUNNING, JobStatus.FAILED, JobStatus.QUEUED},
    JobStatus.RUNNING: {JobStatus.COMPLETED, JobStatus.FAILED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
}

# Terminal states
TERMINAL_STATES: set[JobStatus] = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}

# Permitted actors per transition (from_status, to_status) -> set of allowed actors
# Actors: 'client', 'scheduler', 'worker', 'coordinator', 'reaper'
ALLOWED_ACTORS: dict[tuple[JobStatus, JobStatus], set[str]] = {
    (JobStatus.QUEUED, JobStatus.MATCHING): {"scheduler", "coordinator"},
    (JobStatus.QUEUED, JobStatus.CANCELLED): {"client", "coordinator"},
    (JobStatus.MATCHING, JobStatus.ASSIGNED): {"scheduler", "coordinator"},
    (JobStatus.MATCHING, JobStatus.QUEUED): {"scheduler", "coordinator"},
    (JobStatus.MATCHING, JobStatus.FAILED): {"scheduler", "coordinator"},
    (JobStatus.ASSIGNED, JobStatus.RUNNING): {"worker", "coordinator"},
    (JobStatus.ASSIGNED, JobStatus.FAILED): {"worker", "coordinator", "reaper"},
    (JobStatus.ASSIGNED, JobStatus.QUEUED): {"coordinator", "reaper", "scheduler"},
    (JobStatus.RUNNING, JobStatus.COMPLETED): {"worker", "coordinator"},
    (JobStatus.RUNNING, JobStatus.FAILED): {"worker", "coordinator", "reaper"},
}


def transition_job_status(
    job: Job,
    target_status: JobStatus | str,
    actor: str,
    error: str | None = None,
) -> Job:
    """
    Transition a job to a target status with validation and audit timestamps.

    Args:
        job: The Job ORM model instance.
        target_status: The intended next JobStatus.
        actor: Identifier of who is initiating the change ('client', 'scheduler', 'worker', etc.)
        error: Optional error description (for FAILED transitions).

    Returns:
        The updated Job instance.

    Raises:
        InvalidJobTransitionError: If the transition is illegal or the actor is unauthorized.
    """
    current_status = JobStatus(job.status)
    if isinstance(target_status, str):
        target_status = JobStatus(target_status)

    # Idempotent no-op if already in the target status
    if current_status == target_status:
        if error and not job.error:
            job.error = error
        return job

    # Validate transition path
    valid_targets = ALLOWED_TRANSITIONS.get(current_status, set())
    if target_status not in valid_targets:
        raise InvalidJobTransitionError(
            current_status=current_status.value,
            target_status=target_status.value,
            reason=f"Transition from {current_status.value} to {target_status.value} is not allowed",
        )

    # Validate actor authorization for this transition
    allowed_actors = ALLOWED_ACTORS.get((current_status, target_status), set())
    if actor not in allowed_actors:
        raise InvalidJobTransitionError(
            current_status=current_status.value,
            target_status=target_status.value,
            reason=f"Actor '{actor}' is not permitted to perform transition {current_status.value} -> {target_status.value}",
        )

    now = datetime.datetime.now(datetime.UTC)
    job.status = target_status.value

    # Update lifecycle timestamps
    if target_status == JobStatus.RUNNING and job.started_at is None:
        job.started_at = now

    if target_status in TERMINAL_STATES and job.completed_at is None:
        job.completed_at = now

    if target_status == JobStatus.FAILED and error:
        job.error = error

    return job
