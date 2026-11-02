"""
Job exceptions.
"""

import uuid

from fastapi import HTTPException, status


class JobNotFoundError(HTTPException):
    """Exception raised when a requested job does not exist."""

    def __init__(self, job_id: uuid.UUID) -> None:
        self.job_id = job_id
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
