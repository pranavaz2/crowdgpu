"""
Pydantic schemas for Peer domain.

Defines request and response data contracts for peer registration,
heartbeat, peer status, and GPU hardware capabilities.
"""

import datetime
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    worker_id: str | None = Field(
        default=None,
        description="Optional worker identifier alias (Person 2 worker)",
    )

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def normalize_worker_registration(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Worker format (Person 2): flat gpu fields instead of gpu_capabilities array
            if "gpu_name" in data and "gpu_capabilities" not in data:
                vram = data.get("total_vram_mib") or data.get("vram_mb") or 8192
                gpu_cap = {
                    "gpu_name": data.get("gpu_name", "NVIDIA GPU"),
                    "vram_mb": int(vram),
                    "driver_version": data.get("driver_version"),
                    "cuda_version": data.get("cuda_version"),
                    "compute_capability": data.get("compute_capability"),
                }
                data["gpu_capabilities"] = [gpu_cap]
                if "hostname" not in data:
                    data["hostname"] = data.get("worker_id") or "worker-node"
                if "owner_id" not in data:
                    from coordinator.config import settings
                    data["owner_id"] = uuid.UUID(settings.demo_user_id)
        return data


class PeerHeartbeatRequest(BaseModel):
    """Payload sent by a worker to update heartbeat and optional status."""

    status: PeerStatus | None = Field(
        default=None,
        description="Optional status update (e.g. 'available', 'busy')",
    )
    state: str | None = Field(
        default=None,
        description="Worker state alias (e.g. 'AVAILABLE', 'BUSY')",
    )
    current_job_id: str | None = Field(
        default=None,
        description="Current active job ID if worker is executing",
    )
    gpu_telemetry: dict[str, Any] | None = Field(
        default=None,
        description="Optional GPU telemetry metrics reported by worker",
    )

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def normalize_heartbeat(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "status" not in data and "state" in data:
                raw_state = data.get("state")
                if raw_state:
                    data["status"] = raw_state.lower()
        return data


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
    registered: bool = True
    worker_id: str | None = None
    peer_token: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_peer_computed(cls, data: Any) -> Any:
        from coordinator.core.auth import generate_worker_token

        if hasattr(data, "__dict__"):
            peer_id = getattr(data, "id", None)
            token = generate_worker_token(peer_id) if peer_id else None
            return {
                "id": peer_id,
                "owner_id": getattr(data, "owner_id", None),
                "hostname": getattr(data, "hostname", None),
                "status": getattr(data, "status", None),
                "registered_at": getattr(data, "registered_at", None),
                "last_seen_at": getattr(data, "last_seen_at", None),
                "created_at": getattr(data, "created_at", None),
                "updated_at": getattr(data, "updated_at", None),
                "gpu_capabilities": getattr(data, "gpu_capabilities", []),
                "registered": True,
                "worker_id": str(peer_id) if peer_id else None,
                "peer_token": token,
            }
        elif isinstance(data, dict):
            peer_id = data.get("id")
            if "registered" not in data:
                data["registered"] = True
            if "worker_id" not in data and peer_id:
                data["worker_id"] = str(peer_id)
            if "peer_token" not in data and peer_id:
                try:
                    p_uuid = uuid.UUID(str(peer_id))
                    data["peer_token"] = generate_worker_token(p_uuid)
                except Exception:
                    pass
        return data
