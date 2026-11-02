"""
Peer ORM model.

A Peer represents a CrowdGPU provider node — a machine running the Worker Daemon.

Each Peer is owned by a User and may expose one or more GPU capabilities.

Table: peers
"""

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coordinator.database.base import Base, TimestampMixin


class Peer(TimestampMixin, Base):
    """Provider peer node entity."""

    __tablename__ = "peers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("(gen_random_uuid())"),
    )

    # Foreign key to the owning user.
    # ON DELETE CASCADE: removing a user removes all their peers.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Human-readable identifier for the peer (machine hostname or alias).
    hostname: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Peer lifecycle status.
    # Possible values: "offline" | "online" | "busy"
    # Business logic for transitions belongs to the Peer Registry module (later phase).
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="offline",
    )

    # Timestamp of first successful registration.
    registered_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamp of the most recent heartbeat — updated by the Worker Daemon (later phase).
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    owner: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User",
        back_populates="peers",
        lazy="selectin",
    )

    gpu_capabilities: Mapped[list["GpuCapability"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "GpuCapability",
        back_populates="peer",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    jobs: Mapped[list["Job"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Job",
        back_populates="assigned_peer",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Peer id={self.id} hostname={self.hostname!r} status={self.status!r}>"
