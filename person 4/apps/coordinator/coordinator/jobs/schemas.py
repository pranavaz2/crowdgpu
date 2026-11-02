"""
Job API schemas.
"""

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class JobSubmitRequest(BaseModel):
    """Payload for submitting a new compute job."""

    owner_id: uuid.UUID = Field(
        ...,
        description="ID of the user submitting the job.",
    )
    docker_image: str = Field(
        ...,
        description="Docker image to run.",
        min_length=1,
        max_length=255,
    )
    command: str = Field(
        ...,
        description="Command to execute inside the container.",
        min_length=1,
        max_length=1024,
    )


class JobResponse(BaseModel):
    """Response schema for a compute job."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    docker_image: str
    command: str
    status: str
    assigned_peer_id: uuid.UUID | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class JobStatusUpdateRequest(BaseModel):
    """Payload for updating job status."""

    status: str = Field(
        ...,
        description="New job status (e.g. 'assigned', 'running', 'completed', 'failed')",
        min_length=1,
        max_length=32,
    )


class JobAssignRequest(BaseModel):
    """Payload for assigning a job to a specific peer."""

    peer_id: uuid.UUID = Field(
        ...,
        description="ID of the peer assigned to execute this job",
    )
