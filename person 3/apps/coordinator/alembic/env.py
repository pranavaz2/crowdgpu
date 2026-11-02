"""
Alembic environment for CrowdGPU Coordinator.

Supports both offline mode (generate SQL scripts) and online async mode
(apply migrations directly against a live PostgreSQL instance).

Credentials are read from coordinator.config.settings — never hardcoded.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

import coordinator.database.models  # noqa: F401 — side-effect: registers all models
from alembic import context

# ---------------------------------------------------------------------------
# Load application config & register all models with Base.metadata
# ---------------------------------------------------------------------------
# Import models so that Base.metadata is fully populated before autogenerate
# inspects it.  The order matters: models must be imported before target_metadata
# is referenced below.
from coordinator.config import settings
from coordinator.database.base import Base

# ---------------------------------------------------------------------------
# Alembic Config object (alembic.ini)
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging (if present).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url with the value from application settings if not already set
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.database_url)

# Metadata for autogenerate support.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode — produce SQL script without a live connection
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine — calls to
    context.execute() emit the given SQL to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online async mode — apply migrations against a live database
# ---------------------------------------------------------------------------
def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations within a connection."""
    target_url = config.get_main_option("sqlalchemy.url") or settings.database_url
    connectable = create_async_engine(target_url)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online mode — drives the async migration coroutine."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(asyncio.run, run_async_migrations()).result()
    else:
        asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
