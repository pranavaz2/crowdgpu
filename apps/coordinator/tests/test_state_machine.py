"""
Unit tests for the Job State Machine.

Validates:
- Every valid lifecycle transition and actor authorization.
- Rejection of invalid transitions with InvalidJobTransitionError.
- Rejection of unauthorized actors for transitions.
- Idempotent no-op behavior when transitioning to the current state.
- Lifecycle timestamp updates (started_at, completed_at).
"""

import uuid

import pytest

from coordinator.database.models.job import Job
from coordinator.jobs.exceptions import InvalidJobTransitionError
from coordinator.jobs.state_machine import (
    JobStatus,
    transition_job_status,
)


def make_dummy_job(status: JobStatus = JobStatus.QUEUED) -> Job:
    return Job(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        name="Dummy Job",
        command="echo 1",
        requirements={"required_vram_mb": 1000},
        status=status.value,
    )


class TestJobStateMachine:
    def test_happy_path_lifecycle(self) -> None:
        """QUEUED -> MATCHING -> ASSIGNED -> RUNNING -> COMPLETED."""
        job = make_dummy_job(JobStatus.QUEUED)

        # 1. QUEUED -> MATCHING by scheduler
        transition_job_status(job, JobStatus.MATCHING, actor="scheduler")
        assert job.status == "MATCHING"

        # 2. MATCHING -> ASSIGNED by scheduler
        transition_job_status(job, JobStatus.ASSIGNED, actor="scheduler")
        assert job.status == "ASSIGNED"

        # 3. ASSIGNED -> RUNNING by worker
        transition_job_status(job, JobStatus.RUNNING, actor="worker")
        assert job.status == "RUNNING"
        assert job.started_at is not None

        # 4. RUNNING -> COMPLETED by worker
        transition_job_status(job, JobStatus.COMPLETED, actor="worker")
        assert job.status == "COMPLETED"
        assert job.completed_at is not None

    def test_cancellation_from_queued(self) -> None:
        """Client can cancel a QUEUED job."""
        job = make_dummy_job(JobStatus.QUEUED)
        transition_job_status(job, JobStatus.CANCELLED, actor="client")
        assert job.status == "CANCELLED"
        assert job.completed_at is not None

    def test_scheduler_retry_flow(self) -> None:
        """MATCHING -> QUEUED retry transition."""
        job = make_dummy_job(JobStatus.QUEUED)
        transition_job_status(job, JobStatus.MATCHING, actor="scheduler")
        transition_job_status(job, JobStatus.QUEUED, actor="scheduler")
        assert job.status == "QUEUED"

    def test_worker_failure(self) -> None:
        """Worker can report failure from RUNNING."""
        job = make_dummy_job(JobStatus.QUEUED)
        transition_job_status(job, JobStatus.MATCHING, actor="scheduler")
        transition_job_status(job, JobStatus.ASSIGNED, actor="scheduler")
        transition_job_status(job, JobStatus.RUNNING, actor="worker")
        transition_job_status(
            job,
            JobStatus.FAILED,
            actor="worker",
            error="CUDA out of memory error",
        )
        assert job.status == "FAILED"
        assert job.error == "CUDA out of memory error"
        assert job.completed_at is not None

    def test_reaper_failure_on_lost_heartbeat(self) -> None:
        """Reaper can fail a RUNNING job if peer heartbeat dies."""
        job = make_dummy_job(JobStatus.QUEUED)
        transition_job_status(job, JobStatus.MATCHING, actor="scheduler")
        transition_job_status(job, JobStatus.ASSIGNED, actor="scheduler")
        transition_job_status(job, JobStatus.RUNNING, actor="worker")
        transition_job_status(
            job,
            JobStatus.FAILED,
            actor="reaper",
            error="Peer worker unresponsive",
        )
        assert job.status == "FAILED"
        assert "unresponsive" in job.error

    def test_invalid_transitions_rejected(self) -> None:
        """Disallowed transitions raise InvalidJobTransitionError."""
        # Cannot jump from QUEUED to RUNNING
        job = make_dummy_job(JobStatus.QUEUED)
        with pytest.raises(InvalidJobTransitionError):
            transition_job_status(job, JobStatus.RUNNING, actor="worker")

        # Cannot cancel RUNNING job
        job_running = make_dummy_job(JobStatus.RUNNING)
        with pytest.raises(InvalidJobTransitionError):
            transition_job_status(job_running, JobStatus.CANCELLED, actor="client")

        # Terminal state COMPLETED cannot be changed
        job_done = make_dummy_job(JobStatus.COMPLETED)
        with pytest.raises(InvalidJobTransitionError):
            transition_job_status(job_done, JobStatus.RUNNING, actor="worker")

    def test_unauthorized_actor_rejected(self) -> None:
        """Valid transition path but unauthorized actor raises InvalidJobTransitionError."""
        # Worker cannot cancel a QUEUED job
        job = make_dummy_job(JobStatus.QUEUED)
        with pytest.raises(InvalidJobTransitionError) as exc_info:
            transition_job_status(job, JobStatus.CANCELLED, actor="worker")
        assert "not permitted" in str(exc_info.value)

        # Client cannot acknowledge RUNNING
        job_assigned = make_dummy_job(JobStatus.ASSIGNED)
        with pytest.raises(InvalidJobTransitionError) as exc_info:
            transition_job_status(job_assigned, JobStatus.RUNNING, actor="client")
        assert "not permitted" in str(exc_info.value)

    def test_idempotent_no_op(self) -> None:
        """Transitioning to same status is an idempotent no-op."""
        job = make_dummy_job(JobStatus.QUEUED)
        res = transition_job_status(job, JobStatus.QUEUED, actor="client")
        assert res.status == "QUEUED"
