"""
Health check API router.

Provides a minimal liveness endpoint. No business logic.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the coordinator liveness status.",
    tags=["health"],
)
async def health() -> HealthResponse:
    """Return coordinator health status."""
    from coordinator import __version__

    return HealthResponse(status="ok", version=__version__)
