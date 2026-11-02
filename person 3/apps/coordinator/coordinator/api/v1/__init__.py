"""
Coordinator API v1 Router.
"""

from fastapi import APIRouter

from coordinator.api.v1.peers import router as peers_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(peers_router)

__all__ = ["v1_router"]
