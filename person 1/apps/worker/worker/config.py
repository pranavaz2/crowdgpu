"""
Worker configuration.

Reads from environment variables (with development defaults).
Do not read os.environ directly in worker modules — use this Settings object.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Worker daemon configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Worker identity
    # -------------------------------------------------------------------------
    worker_id: str = "worker-dev-001"

    # -------------------------------------------------------------------------
    # Operation mode
    # development — no GPU hardware required; mock responses
    # production  — expects NVIDIA GPU + NVML
    # -------------------------------------------------------------------------
    worker_mode: str = "development"

    # -------------------------------------------------------------------------
    # Coordinator connection (not used in bootstrap)
    # -------------------------------------------------------------------------
    worker_coordinator_url: str = "http://localhost:8000"

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    worker_log_level: str = "INFO"


# Module-level singleton — import this everywhere in the worker.
settings = WorkerSettings()
