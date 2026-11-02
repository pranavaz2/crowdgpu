"""
Pydantic schemas for the Job domain.

Defines request and response contracts for job submission, querying,
worker status reporting, and result submissions.
"""

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
        default=0,
        ge=0,
        le=200000,
        description="Minimum GPU VRAM required in mebibytes (MiB)",
    )
    vram_required_mb: int | None = Field(
        default=None,
        description="Frontend alias for required_vram_mb",
    )
    docker_image: str | None = Field(
        default=None,
        description="Optional container image (e.g. 'pytorch/pytorch:latest')",
    )
    workload_type: str | None = Field(
        default="batch",
        description="Workload type (e.g. 'batch')",
    )
    requirements: dict[str, Any] | None = Field(
        default=None,
        description="Optional additional requirements (e.g. cuda_version, compute_capability)",
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize vram_required_mb from either field name
            vram = data.get("required_vram_mb")
            if vram is None:
                vram = data.get("vram_required_mb", 0)
            data["required_vram_mb"] = int(vram)
            data["vram_required_mb"] = int(vram)
        return data

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
    peer_id: uuid.UUID | None = None
    peer_hostname: str | None = None
    gpu_name: str | None = None
    docker_image: str | None = None
    workload_type: str | None = None
    vram_required_mb: int | None = None
    attempt_count: int = 0
    submitted_at: datetime.datetime | None = None
    matching_at: datetime.datetime | None = None
    assigned_at: datetime.datetime | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    result: Any | None = None
    error: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_computed_fields(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            reqs = getattr(data, "requirements", None) or {}
            peer = getattr(data, "assigned_peer", None)
            assigned_id = getattr(data, "assigned_peer_id", None)

            peer_hostname = None
            gpu_name = None
            if peer:
                peer_hostname = getattr(peer, "hostname", None)
                caps = getattr(peer, "gpu_capabilities", None)
                if caps and len(caps) > 0:
                    gpu_name = getattr(caps[0], "gpu_name", None)

            created = getattr(data, "created_at", None)
            started = getattr(data, "started_at", None)
            completed = getattr(data, "completed_at", None)
            st = getattr(data, "status", None)

            return {
                "id": getattr(data, "id", None),
                "owner_id": getattr(data, "owner_id", None),
                "name": getattr(data, "name", None),
                "command": getattr(data, "command", None),
                "requirements": reqs,
                "status": st,
                "assigned_peer_id": assigned_id,
                "peer_id": assigned_id,
                "peer_hostname": peer_hostname,
                "gpu_name": gpu_name,
                "docker_image": reqs.get("docker_image"),
                "workload_type": reqs.get("workload_type", "batch"),
                "vram_required_mb": reqs.get("required_vram_mb") or reqs.get("vram_required_mb", 0),
                "attempt_count": getattr(data, "attempt_count", 0),
                "submitted_at": created,
                "matching_at": created if st in ("MATCHING", "ASSIGNED", "RUNNING", "COMPLETED", "FAILED") else None,
                "assigned_at": created if st in ("ASSIGNED", "RUNNING", "COMPLETED") and assigned_id else None,
                "started_at": started,
                "completed_at": completed,
                "result": getattr(data, "result", None),
                "error": getattr(data, "error", None),
                "created_at": created,
                "updated_at": getattr(data, "updated_at", None),
            }
        return data


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
    """Payload sent by a worker upon workload completion or failure."""

    exit_code: int = Field(
        default=0,
        description="Process exit code from execution (0 = success)",
    )
    status: str | None = Field(
        default=None,
        description="Result status string: 'success' or 'failed'",
    )
    stdout_tail: str | None = Field(
        default=None,
        max_length=20000,
        description="Trailing stdout/stderr output lines",
    )
    output: Any | None = Field(
        default=None,
        description="Structured execution output dictionary or result string",
    )
    execution_time_s: float | None = Field(
        default=None,
        description="Execution duration in seconds",
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
    error: str | None = Field(
        default=None,
        description="Error description if status is failed",
    )

    model_config = ConfigDict(extra="allow")
