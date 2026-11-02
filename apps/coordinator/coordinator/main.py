"""
CrowdGPU Coordinator — FastAPI application factory.

Bootstrap phase: only the health endpoint is registered.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from coordinator.api import api_router
from coordinator.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    logging.basicConfig(level=settings.coordinator_log_level.upper())
    logger.info("CrowdGPU Coordinator starting up")

    # Seed deterministic demo user in development mode
    if settings.demo_auth_enabled:
        try:
            import uuid
            from coordinator.database.models.user import User
            from coordinator.database.session import async_session_factory

            async with async_session_factory() as session:
                demo_uid = uuid.UUID(settings.demo_user_id)
                user = await session.get(User, demo_uid)
                if not user:
                    session.add(
                        User(
                            id=demo_uid,
                            email=settings.demo_user_email,
                            display_name="Demo User",
                        )
                    )
                    await session.commit()
                    logger.info(
                        "Deterministic demo user verified: %s (%s)",
                        demo_uid,
                        settings.demo_user_email,
                    )
        except Exception as exc:
            logger.debug("Demo user initialization skipped: %s", exc)

    yield
    # Dispose the SQLAlchemy connection pool on shutdown.
    from coordinator.database.session import async_engine

    await async_engine.dispose()
    logger.info("CrowdGPU Coordinator shut down cleanly")



def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from fastapi.middleware.cors import CORSMiddleware

    application = FastAPI(
        title="CrowdGPU Coordinator",
        description=(
            "Central coordinator for the CrowdGPU peer-to-peer GPU resource sharing platform."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router)

    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from fastapi import Response

    @application.get("/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return application


# WSGI/ASGI entry point — used by uvicorn and tests.
app = create_app()
