"""
Pydantic schemas for Peer domain.

Defines request and response data contracts for peer registration,
heartbeat, peer status, and GPU hardware capabilities.
"""

import datetime
import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PeerStatus(StrEnum):
    """Lifecycle status of a provider peer node."""

    OFFLINE = "offline"
    AVAILABLE = "available"
    BUSY = "busy"


# ---------------------------------------------------------------------------
# GPU Capability Schemas
# ---------------------------------------------------------------------------
class GpuCapabilityBase(BaseModel):
    """Base attributes for a GPU capability record."""

    gpu_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="GPU model name (e.g. 'NVIDIA GeForce RTX 4090')",
    )
    vram_mb: int = Field(
        ...,
        gt=0,
        description="Total GPU VRAM in mebibytes (MiB)",
    )
    driver_version: str | None = Field(
        default=None,
        max_length=64,
        description="Driver version string (e.g. '535.104.05')",
    )
    cuda_version: str | None = Field(
        default=None,
        max_length=32,
        description="CUDA toolkit version (e.g. '12.2')",
    )
    compute_capability: str | None = Field(
        default=None,
        max_length=16,
        description="CUDA compute capability (e.g. '8.9')",
    )


class GpuCapabilityCreate(GpuCapabilityBase):
    """Payload to register a GPU capability during peer registration."""

    pass


class GpuCapabilityResponse(GpuCapabilityBase):
    """Representation of a persisted GPU capability record."""

    id: uuid.UUID
    peer_id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Peer Schemas
# ---------------------------------------------------------------------------
class PeerRegisterRequest(BaseModel):
    """Payload to register a new peer with one or more GPU capabilities."""

    owner_id: uuid.UUID = Field(
        ...,
        description="UUID of the owning user (must already exist)",
    )
    hostname: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Machine hostname or provider alias",
    )
    initial_status: PeerStatus = Field(
        default=PeerStatus.AVAILABLE,
        description="Initial lifecycle status upon registration",
    )
    gpu_capabilities: list[GpuCapabilityCreate] = Field(
        ...,
        min_length=1,
        description="List of GPU devices exposed by this peer (at least one required)",
    )


class PeerHeartbeatRequest(BaseModel):
    """Payload sent by a worker to update heartbeat and optional status."""

    status: PeerStatus | None = Field(
        default=None,
        description="Optional status update (e.g. 'available', 'busy')",
    )


class PeerResponse(BaseModel):
    """Application-level representation of a peer node and its capabilities."""

    id: uuid.UUID
    owner_id: uuid.UUID
    hostname: str
    status: str
    registered_at: datetime.datetime | None = None
    last_seen_at: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    gpu_capabilities: list[GpuCapabilityResponse] = []

    model_config = ConfigDict(from_attributes=True)
