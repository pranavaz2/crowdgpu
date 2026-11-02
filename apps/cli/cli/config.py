"""
CLI configuration.

Reads from environment variables with defaults for development and demo environments.
"""

from __future__ import annotations

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class CliSettings(BaseSettings):
    """CLI runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Coordinator Connection
    # -------------------------------------------------------------------------
    coordinator_url: str = "http://127.0.0.1:8000"

    # -------------------------------------------------------------------------
    # Development User Identity (X-User-Id header)
    # Default is the canonical deterministic demo user UUID
    # -------------------------------------------------------------------------
    user_id: str = "00000000-0000-0000-0000-000000000001"

    # -------------------------------------------------------------------------
    # Network Timeouts
    # -------------------------------------------------------------------------
    timeout_seconds: float = 10.0


def get_settings(
    coordinator_url: str | None = None,
    user_id: str | None = None,
) -> CliSettings:
    """Return a settings instance with optional explicit runtime overrides."""
    # Priority: explicit CLI arguments > environment variables > default
    env_coord = os.environ.get("COORDINATOR_URL")
    env_user = os.environ.get("CROWDGPU_USER_ID") or os.environ.get("USER_ID")

    base = CliSettings()
    target_coord = coordinator_url or env_coord or base.coordinator_url
    target_user = user_id or env_user or base.user_id

    return CliSettings(
        coordinator_url=target_coord.rstrip("/"),
        user_id=target_user.strip(),
        timeout_seconds=base.timeout_seconds,
    )


# Module-level default
settings = get_settings()
