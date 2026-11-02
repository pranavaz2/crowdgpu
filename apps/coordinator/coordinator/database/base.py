"""
Declarative base and shared column mixins.

All SQLAlchemy ORM models inherit from Base.
TimestampMixin provides created_at / updated_at for every entity that needs audit
timestamps without repeating column definitions.
"""

import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all CrowdGPU ORM models."""


class TimestampMixin:
    """
    Adds server-managed created_at and updated_at columns.

    - created_at is set once at INSERT time via server_default.
    - updated_at is set at INSERT and must be updated by application code
      (or a DB trigger) on UPDATE.  SQLAlchemy's onupdate hook keeps it
      current when the ORM manages the flush.
    """

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=func.now(),
        nullable=False,
    )


# Convenience re-export so callers can do:
#   from coordinator.database.base import Base, TimestampMixin
__all__ = ["Base", "TimestampMixin"]
