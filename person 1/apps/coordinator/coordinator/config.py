"""
Coordinator configuration.

Reads from environment variables (with defaults for development).
In production, variables are populated from the .env file or the deployment
environment. Do not read os.environ directly — use this Settings object.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Server
    # -------------------------------------------------------------------------
    coordinator_host: str = "0.0.0.0"
    coordinator_port: int = 8000
    coordinator_debug: bool = False
    coordinator_log_level: str = "INFO"

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    # Primary async database URL (asyncpg driver).
    # In development, defaults to the Docker Compose PostgreSQL instance.
    # Override via DATABASE_URL environment variable or .env file.
    database_url: str = "postgresql+asyncpg://crowdgpu:changeme@localhost:5432/crowdgpu"

    # Optional separate test database URL for integration tests (ADR-003 Tier 2).
    # Set TEST_DATABASE_URL to run tests/integration/ against a real PostgreSQL instance.
    test_database_url: str | None = None

    # -------------------------------------------------------------------------
    # Redis (not connected in bootstrap)
    # -------------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # -------------------------------------------------------------------------
    # Security (placeholder — not used in bootstrap)
    # -------------------------------------------------------------------------
    secret_key: str = "changeme-replace-with-a-secure-random-key-in-production"

    # -------------------------------------------------------------------------
    # Scheduler & Timeouts (Person 1)
    # -------------------------------------------------------------------------
    heartbeat_timeout_seconds: int = 30
    ack_timeout_seconds: int = 60
    max_job_attempts: int = 3
    scheduler_weight_vram: float = 0.5
    scheduler_weight_availability: float = 0.3
    scheduler_weight_latency: float = 0.2


# Module-level singleton — import this everywhere in the coordinator.
settings = Settings()
