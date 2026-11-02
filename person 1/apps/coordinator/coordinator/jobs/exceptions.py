"""
Exceptions for the Job domain.
"""

import uuid


class JobDomainError(Exception):
    """Base exception for job domain errors."""

    pass


class JobNotFoundError(JobDomainError):
    """Raised when a requested job ID does not exist."""

    def __init__(self, job_id: uuid.UUID) -> None:
        self.job_id = job_id
        super().__init__(f"Job '{job_id}' not found")


class InvalidJobTransitionError(JobDomainError):
    """Raised when an invalid state transition is attempted on a job."""

    def __init__(self, current_status: str, target_status: str, reason: str | None = None) -> None:
        self.current_status = current_status
        self.target_status = target_status
        msg = f"Cannot transition job from '{current_status}' to '{target_status}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class UnauthorizedJobAccessError(JobDomainError):
    """Raised when an actor attempts an action on a job they do not own or are not assigned to."""

    def __init__(self, message: str = "Unauthorized access to job") -> None:
        super().__init__(message)


class NoSuitablePeerError(JobDomainError):
    """Raised by the scheduler when no candidate peer meets job requirements."""

    def __init__(self, job_id: uuid.UUID, reason: str = "No suitable peer found") -> None:
        self.job_id = job_id
        super().__init__(f"Scheduling failed for job '{job_id}': {reason}")
