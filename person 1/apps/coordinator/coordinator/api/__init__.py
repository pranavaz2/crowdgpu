"""API router package."""

from fastapi import APIRouter

from coordinator.api.health import router as health_router
from coordinator.api.v1 import v1_router

# Root API router — sub-routers are registered here.
api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(v1_router, prefix="/api")

__all__ = ["api_router"]
