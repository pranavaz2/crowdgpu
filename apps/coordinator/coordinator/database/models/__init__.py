"""
coordinator.database.models — ORM model registry.

Importing this package ensures every model is registered with Base.metadata,
which is required for:
  - Alembic autogenerate (env.py imports this module)
  - SQLAlchemy schema creation in tests (Base.metadata.create_all)

All public model classes are re-exported here for convenience.
"""

from coordinator.database.models.gpu_capability import GpuCapability
from coordinator.database.models.job import Job
from coordinator.database.models.peer import Peer
from coordinator.database.models.user import User

__all__ = ["User", "Peer", "GpuCapability", "Job"]
