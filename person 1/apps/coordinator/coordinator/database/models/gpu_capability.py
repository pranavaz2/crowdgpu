"""
GPU Capability ORM model.

Records the static hardware capabilities of one GPU device on a Peer.

A single Peer may expose multiple GPUs (multi-GPU systems), each with its own
GpuCapability record.

This entity is deliberately minimal — it records what the GPU *is*, not what it
is currently *doing*. Telemetry history (utilisation, temperature, etc.) belongs
to a separate table in a later phase.

Table: gpu_capabilities
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coordinator.database.base import Base, TimestampMixin


class GpuCapability(TimestampMixin, Base):
    """Static GPU hardware capability record for a Peer."""

    __tablename__ = "gpu_capabilities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("(gen_random_uuid())"),
    )

    # Foreign key to the owning peer.
    # ON DELETE CASCADE: removing a peer removes its GPU capability records.
    peer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("peers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # GPU model name as reported by the driver (e.g. "NVIDIA GeForce RTX 4090").
    gpu_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Total GPU VRAM in mebibytes (MiB).
    vram_mb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Driver version string (e.g. "535.104.05").  Null if not yet reported.
    driver_version: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # CUDA toolkit version (e.g. "12.2").  Null for non-CUDA GPUs.
    cuda_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    # CUDA compute capability (e.g. "8.9" for Ada Lovelace).  Null for non-CUDA GPUs.
    compute_capability: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    peer: Mapped["Peer"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Peer",
        back_populates="gpu_capabilities",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<GpuCapability id={self.id} gpu_name={self.gpu_name!r}"
            f" vram_mb={self.vram_mb}>"
        )
