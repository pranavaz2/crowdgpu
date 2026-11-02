"""
CLI configuration.

Reads from environment variables (with defaults for development).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class CliSettings(BaseSettings):
    """CLI configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Coordinator connection
    # -------------------------------------------------------------------------
    coordinator_url: str = "http://localhost:8000"


# Module-level singleton
settings = CliSettings()
