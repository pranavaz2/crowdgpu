"""
Async SQLAlchemy engine and session management.

The engine and session factory are module-level singletons created once at
import time from the application configuration.

FastAPI route handlers obtain a database session via the get_db() dependency,
which handles commit/rollback automatically.

Usage in route handlers:
    from typing import Annotated
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from coordinator.database import get_db

    async def my_route(db: Annotated[AsyncSession, Depends(get_db)]):
        ...
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from coordinator.config import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# echo=False in production; can be set to True for SQL query logging in dev
# by setting COORDINATOR_DEBUG=true (wired up in main.py lifespan).
async_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,  # Detects stale connections before use
    pool_size=5,
    max_overflow=10,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Prevents lazy-load errors after commit
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an AsyncSession for the duration of a request.

    Commits on success, rolls back on any exception, always closes the session.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Annotated shorthand for route signatures:
#   async def route(db: DbSession): ...
DbSession = Annotated[AsyncSession, Depends(get_db)]

__all__ = [
    "async_engine",
    "async_session_factory",
    "get_db",
    "DbSession",
]
