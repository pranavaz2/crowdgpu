"""
Job ORM model.

Represents a compute job submitted by a user.
"""

import uuid
from sqlalchemy import String, text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coordinator.database.base import Base, TimestampMixin


class Job(TimestampMixin, Base):
    """Compute job entity."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    docker_image: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    command: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )

    assigned_peer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("peers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    owner = relationship(
        "User",
        back_populates="jobs",
    )

    assigned_peer = relationship(
        "Peer",
        back_populates="jobs",
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} status={self.status} image={self.docker_image}>"
