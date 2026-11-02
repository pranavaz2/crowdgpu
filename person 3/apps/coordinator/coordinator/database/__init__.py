"""
coordinator.database — async SQLAlchemy database layer.

Public exports:
    Base          — declarative base shared by all models
    TimestampMixin — created_at / updated_at columns
    get_db        — FastAPI dependency that yields an AsyncSession
    async_engine  — module-level engine (used for lifespan disposal)
    async_session_factory — sessionmaker (used by get_db and tests)
"""

from coordinator.database.base import Base, TimestampMixin
from coordinator.database.session import async_engine, async_session_factory, get_db

__all__ = [
    "Base",
    "TimestampMixin",
    "async_engine",
    "async_session_factory",
    "get_db",
]
