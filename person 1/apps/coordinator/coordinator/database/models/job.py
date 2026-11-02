"""
Job ORM model.

Represents a computational GPU workload submitted by a User, scheduled onto an available Peer,
and executed by a Worker.

Table: jobs
"""

import datetime
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from coordinator.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from coordinator.database.models.peer import Peer
    from coordinator.database.models.user import User


class Job(TimestampMixin, Base):
    """Job entity tracking computational tasks and their assignment."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("(gen_random_uuid())"),
    )

    # Owning user who submitted the workload
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Job name / human-readable title
    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    # Command / entrypoint string for execution on worker node
    command: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Resource requirements (e.g. required_vram_mb, cuda_version, etc.)
    requirements: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    # Current lifecycle state (QUEUED, MATCHING, ASSIGNED, RUNNING, COMPLETED, FAILED, CANCELLED)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="QUEUED",
        index=True,
    )

    # Assigned peer provider (set during scheduler assignment)
    assigned_peer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("peers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Number of scheduling/execution attempts made
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Timestamp when worker acknowledges start of workload
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamp when job reaches any terminal state
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Output metadata reported upon completion (exit code, stdout tail, artifact URI)
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    # Failure error message / reason if failed
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="jobs",
        lazy="selectin",
    )

    assigned_peer: Mapped["Peer | None"] = relationship(
        "Peer",
        back_populates="jobs",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_jobs_owner_created", "owner_id", "created_at"),
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("ix_jobs_assigned_peer_status", "assigned_peer_id", "status"),
        Index(
            "uq_jobs_assigned_peer_active",
            "assigned_peer_id",
            unique=True,
            postgresql_where=text("status IN ('ASSIGNED', 'RUNNING')"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} name={self.name!r} status={self.status!r}>"
