"""
Coordinator configuration.

Reads from environment variables (with defaults for development).
In production, variables are populated from the .env file or the deployment
environment. Do not read os.environ directly — use this Settings object.
"""

from typing import Any

from pydantic import model_validator
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

    # -------------------------------------------------------------------------
    # Authentication & Environment Mode
    # -------------------------------------------------------------------------
    environment: str = "development"
    dev_mode: bool = False
    demo_auth_enabled: bool = False
    demo_user_id: str = "00000000-0000-0000-0000-000000000001"
    demo_user_email: str = "demo@crowdgpu.local"

    # -------------------------------------------------------------------------
    # CORS Configuration
    # -------------------------------------------------------------------------
    cors_allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://10.131.126.15:5173",
        "http://10.131.126.15:8000",
    ]

    @model_validator(mode="before")
    @classmethod
    def normalize_cors_origins(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw = data.get("cors_allowed_origins")
            if isinstance(raw, str):
                raw = raw.strip()
                if raw.startswith("[") and raw.endswith("]"):
                    import json
                    try:
                        data["cors_allowed_origins"] = json.loads(raw)
                    except Exception:
                        data["cors_allowed_origins"] = [s.strip() for s in raw[1:-1].split(",") if s.strip()]
                else:
                    data["cors_allowed_origins"] = [s.strip() for s in raw.split(",") if s.strip()]
        return data

    # -------------------------------------------------------------------------
    # WebRTC / ICE Servers & Signaling Hardening
    # -------------------------------------------------------------------------
    stun_servers: list[str] = ["stun:stun.l.google.com:19302"]
    turn_server: str | None = None
    turn_username: str | None = None
    turn_credential: str | None = None
    turn_realm: str = "crowdgpu.local"
    turn_secret: str | None = None
    signaling_require_token: bool = False
    signaling_rate_limit_per_minute: int = 180

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Strictly enforce security invariants in production mode."""
        if self.environment.lower() == "production":
            if self.demo_auth_enabled:
                raise ValueError(
                    "Security violation: demo_auth_enabled cannot be enabled in production"
                )
            if "changeme" in self.secret_key.lower():
                raise ValueError(
                    "Security violation: default secret_key cannot be used in production. Set SECRET_KEY."
                )
            if "changeme" in self.database_url.lower():
                raise ValueError(
                    "Security violation: default database credentials cannot be used in production. Set DATABASE_URL."
                )
        return self


# Module-level singleton — import this everywhere in the coordinator.
settings = Settings()
