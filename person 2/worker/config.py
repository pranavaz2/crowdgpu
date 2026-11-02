"""
TASK 2 — Worker configuration loaded from environment variables.

Required env vars (with defaults):
  WORKER_ID           — unique identifier for this worker instance
  COORDINATOR_URL     — base URL of the Coordinator REST API
  GPU_ID              — index of the GPU to use (default 0)
  HEARTBEAT_INTERVAL  — seconds between heartbeat posts (default 30)
"""

from __future__ import annotations

import logging
import os
import uuid as _uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """All configuration needed by the worker, sourced from env vars."""

    worker_id: str
    coordinator_url: str
    gpu_id: int
    heartbeat_interval: int

    # HTTP timeouts (seconds)
    http_connect_timeout: int = 5
    http_read_timeout: int = 30

    # Retry policy
    max_registration_retries: int = 5
    retry_backoff_base: float = 2.0  # exponential backoff factor

    # VRAM safety margin kept free for system use (MiB)
    vram_safety_margin_mib: int = 256

    def __post_init__(self) -> None:
        if not self.coordinator_url:
            raise ValueError("COORDINATOR_URL must not be empty.")
        # Strip trailing slash for consistent URL construction
        self.coordinator_url = self.coordinator_url.rstrip("/")
        if self.gpu_id < 0:
            raise ValueError("GPU_ID must be >= 0.")
        if self.heartbeat_interval < 1:
            raise ValueError("HEARTBEAT_INTERVAL must be >= 1 second.")

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        """
        Build a WorkerConfig from environment variables.

        Raises ``ValueError`` if required variables are missing or invalid.
        """
        worker_id = os.environ.get("WORKER_ID") or f"worker-{_uuid.uuid4().hex[:8]}"

        coordinator_url = os.environ.get("COORDINATOR_URL", "").strip()
        if not coordinator_url:
            raise ValueError(
                "Environment variable COORDINATOR_URL is not set. "
                "Example: COORDINATOR_URL=http://localhost:8000"
            )

        try:
            gpu_id = int(os.environ.get("GPU_ID", "0"))
        except ValueError:
            raise ValueError("GPU_ID must be an integer (e.g. GPU_ID=0).")

        try:
            heartbeat_interval = int(os.environ.get("HEARTBEAT_INTERVAL", "30"))
        except ValueError:
            raise ValueError(
                "HEARTBEAT_INTERVAL must be an integer (seconds, e.g. HEARTBEAT_INTERVAL=30)."
            )

        cfg = cls(
            worker_id=worker_id,
            coordinator_url=coordinator_url,
            gpu_id=gpu_id,
            heartbeat_interval=heartbeat_interval,
        )
        logger.info(
            "Config loaded — worker_id=%s coordinator=%s gpu=%d interval=%ds",
            cfg.worker_id,
            cfg.coordinator_url,
            cfg.gpu_id,
            cfg.heartbeat_interval,
        )
        return cfg

    def api_url(self, path: str) -> str:
        """Return the full URL for a Coordinator API path."""
        return f"{self.coordinator_url}/{path.lstrip('/')}"

    def __repr__(self) -> str:
        return (
            f"WorkerConfig(worker_id={self.worker_id!r}, "
            f"coordinator_url={self.coordinator_url!r}, "
            f"gpu_id={self.gpu_id}, "
            f"heartbeat_interval={self.heartbeat_interval}s)"
        )
