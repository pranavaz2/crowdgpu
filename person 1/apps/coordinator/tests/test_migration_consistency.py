"""
Tests — Alembic migration chain consistency.

Validates:
1. The Alembic revision chain has no gaps (all revisions are reachable from head).
2. The migration head revision ID is known and matches the expected initial migration.
3. The migration script for the initial revision exists and is importable.

These tests do NOT run against a live database.
They validate that the migration files themselves are consistent.

Full autogenerate comparison (Base.metadata vs database schema) requires a
live PostgreSQL connection — that is covered by tests/integration/.
"""

from alembic.config import Config
from alembic.script import ScriptDirectory


def get_alembic_config() -> Config:
    """Return an Alembic Config pointing at the project alembic.ini."""
    import os

    # alembic.ini is in apps/coordinator/
    ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    cfg = Config(ini_path)
    return cfg


class TestMigrationChain:
    def test_alembic_config_is_loadable(self) -> None:
        """alembic.ini can be parsed without error."""
        cfg = get_alembic_config()
        assert cfg is not None

    def test_script_directory_is_accessible(self) -> None:
        """Alembic script directory (alembic/versions/) is accessible."""
        cfg = get_alembic_config()
        script = ScriptDirectory.from_config(cfg)
        assert script is not None

    def test_migration_head_exists(self) -> None:
        """At least one migration head revision exists."""
        cfg = get_alembic_config()
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        assert len(heads) >= 1, "Expected at least one migration head"

    def test_migration_head_is_latest(self) -> None:
        """The latest migration (0002) is the current head."""
        cfg = get_alembic_config()
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        assert "0002" in heads, f"Expected '0002' in heads, got: {heads}"

    def test_no_revision_gaps(self) -> None:
        """Every revision in the chain is reachable from the head (no orphans)."""
        cfg = get_alembic_config()
        script = ScriptDirectory.from_config(cfg)

        # Walk the full revision graph — raises if there are gaps or missing parents.
        revisions = list(script.walk_revisions())
        assert len(revisions) >= 1

        # Collect all revision IDs
        revision_ids = {r.revision for r in revisions}
        # All down_revision parents must exist (None is allowed for the base)
        for rev in revisions:
            if rev.down_revision is not None:
                down = (
                    rev.down_revision
                    if isinstance(rev.down_revision, str)
                    else rev.down_revision
                )
                parents = {down} if isinstance(down, str) else set(down)
                for parent in parents:
                    assert parent in revision_ids, (
                        f"Revision {rev.revision} references missing parent {parent}"
                    )

    def test_initial_migration_has_upgrade(self) -> None:
        """The initial migration script defines an upgrade() function."""
        cfg = get_alembic_config()
        script = ScriptDirectory.from_config(cfg)
        rev = script.get_revision("0001")
        assert rev is not None
        module = rev.module
        assert hasattr(module, "upgrade"), "Migration 0001 is missing upgrade()"
        assert hasattr(module, "downgrade"), "Migration 0001 is missing downgrade()"

    def test_initial_migration_targets_correct_tables(self) -> None:
        """The initial migration module references the expected table names."""
        import inspect

        from alembic.script import ScriptDirectory

        cfg = get_alembic_config()
        script = ScriptDirectory.from_config(cfg)
        rev = script.get_revision("0001")
        assert rev is not None

        source = inspect.getsource(rev.module)
        for table in ("users", "peers", "gpu_capabilities"):
            assert table in source, (
                f"Expected table name {table!r} in migration 0001 source"
            )

    def test_jobs_migration_targets_correct_tables(self) -> None:
        """The jobs migration module (0002) references the jobs table."""
        import inspect

        from alembic.script import ScriptDirectory

        cfg = get_alembic_config()
        script = ScriptDirectory.from_config(cfg)
        rev = script.get_revision("0002")
        assert rev is not None
        assert rev.down_revision == "0001"

        source = inspect.getsource(rev.module)
        assert "jobs" in source, "Expected table name 'jobs' in migration 0002 source"
