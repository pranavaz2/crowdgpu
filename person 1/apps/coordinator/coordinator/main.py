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
    yield
    # Dispose the SQLAlchemy connection pool on shutdown.
    from coordinator.database.session import async_engine

    await async_engine.dispose()
    logger.info("CrowdGPU Coordinator shut down cleanly")



def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
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

    application.include_router(api_router)

    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from fastapi import Response

    @application.get("/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return application


# WSGI/ASGI entry point — used by uvicorn and tests.
app = create_app()
