"""
Coordinator API v1 Router.
"""

from fastapi import APIRouter

from coordinator.api.v1.jobs import router as jobs_router
from coordinator.api.v1.peers import router as peers_router
from coordinator.api.v1.workers import router as workers_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(peers_router)
v1_router.include_router(jobs_router)
v1_router.include_router(workers_router)

__all__ = ["v1_router"]
