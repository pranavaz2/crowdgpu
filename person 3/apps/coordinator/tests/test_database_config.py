"""
Tests — database configuration.

Validates that coordinator.config.Settings loads database_url correctly
and that the value is usable for engine construction.
These tests do NOT open a real database connection.
"""


from coordinator.config import Settings


class TestDatabaseConfig:
    """Settings correctly exposes database configuration."""

    def test_settings_has_database_url(self) -> None:
        """database_url field is present on the Settings model."""
        s = Settings()
        assert hasattr(s, "database_url")

    def test_database_url_is_non_empty_string(self) -> None:
        """database_url default is a non-empty string."""
        s = Settings()
        assert isinstance(s.database_url, str)
        assert len(s.database_url) > 0

    def test_database_url_uses_asyncpg_driver(self) -> None:
        """Default database_url targets the asyncpg async driver."""
        s = Settings()
        assert "asyncpg" in s.database_url, (
            f"Expected asyncpg in DATABASE_URL, got: {s.database_url!r}"
        )

    def test_database_url_targets_postgresql(self) -> None:
        """Default database_url targets PostgreSQL."""
        s = Settings()
        assert s.database_url.startswith("postgresql"), (
            f"Expected postgresql scheme, got: {s.database_url!r}"
        )

    def test_settings_has_test_database_url(self) -> None:
        """test_database_url field is present (may be None)."""
        s = Settings()
        assert hasattr(s, "test_database_url")

    def test_test_database_url_defaults_to_none(self) -> None:
        """test_database_url defaults to None when env var not set."""
        import os

        # Only check if the env var is definitely absent
        if "TEST_DATABASE_URL" not in os.environ:
            s = Settings()
            assert s.test_database_url is None

    def test_engine_can_be_created_from_url(self) -> None:
        """AsyncEngine can be instantiated from the default database_url (no connection made)."""
        from sqlalchemy.ext.asyncio import create_async_engine

        s = Settings()
        engine = create_async_engine(s.database_url)
        # No connection is made — this just verifies the URL is parseable.
        assert engine is not None
        assert str(engine.url).startswith("postgresql")
