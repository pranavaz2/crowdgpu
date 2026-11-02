"""
Pydantic schemas for the Job domain.

Defines request and response contracts for job submission, querying,
worker status reporting, and result submissions.
"""

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobCreate(BaseModel):
    """Payload to submit a new GPU job."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Human-readable job name or description",
    )
    command: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Command / script to be executed inside worker sandbox",
    )
    required_vram_mb: int = Field(
        ...,
        gt=0,
        le=200000,
        description="Minimum GPU VRAM required in mebibytes (MiB)",
    )
    requirements: dict[str, Any] | None = Field(
        default=None,
        description="Optional additional requirements (e.g. cuda_version, compute_capability)",
    )

    @field_validator("command")
    @classmethod
    def validate_command_no_nul(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Command contains invalid NUL byte")
        if not v.strip():
            raise ValueError("Command cannot be whitespace-only")
        return v


class JobResponse(BaseModel):
    """Representation of a CrowdGPU job record."""

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    command: str
    requirements: dict[str, Any]
    status: str
    assigned_peer_id: uuid.UUID | None = None
    attempt_count: int = 0
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class JobStatusUpdate(BaseModel):
    """Payload sent by a worker to update execution status (RUNNING or FAILED)."""

    status: str = Field(
        ...,
        description="Target status: 'RUNNING' or 'FAILED'",
    )
    error: str | None = Field(
        default=None,
        description="Error message if reporting failure",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in ("RUNNING", "FAILED"):
            raise ValueError("Status update from worker must be 'RUNNING' or 'FAILED'")
        return v_upper


class JobResultSubmit(BaseModel):
    """Payload sent by a worker upon successful workload completion."""

    exit_code: int = Field(
        default=0,
        description="Process exit code from execution",
    )
    stdout_tail: str | None = Field(
        default=None,
        max_length=10000,
        description="Trailing stdout/stderr output lines",
    )
    artifact_uri: str | None = Field(
        default=None,
        max_length=512,
        description="Optional URI or storage path to generated output artifacts",
    )
    metrics: dict[str, Any] | None = Field(
        default=None,
        description="Optional execution telemetry metrics (duration_seconds, peak_vram_mb, etc.)",
    )
