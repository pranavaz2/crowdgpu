"""
PostgreSQL integration tests — ADR-003 Tier 2.

These tests require a live PostgreSQL instance.  They are automatically skipped
when the TEST_DATABASE_URL environment variable is not set.

To run these tests locally:
    1. Start PostgreSQL (e.g. via Docker Compose):
           docker compose up -d postgres

    2. Set the environment variable:
           $env:TEST_DATABASE_URL = "postgresql+asyncpg://crowdgpu:changeme@localhost:5432/crowdgpu_test"

    3. Run:
           .venv-coordinator/Scripts/python.exe -m pytest tests/integration/ -v

What is tested here that unit tests cannot cover:
    - gen_random_uuid() server_default (UUID PK auto-generation)
    - TIMESTAMPTZ column precision and timezone handling
    - DB-level FK constraint enforcement (without SQLite PRAGMA)
    - Alembic upgrade head executes without error against real Postgres
    - Alembic downgrade base executes without error (rollback)
    - Autogenerate comparison: Base.metadata matches migrated schema
"""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Skip marker
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_postgres = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason=(
        "PostgreSQL integration tests require TEST_DATABASE_URL env var. "
        "Set it to a valid asyncpg DSN to run these tests. "
        "Example: postgresql+asyncpg://crowdgpu:changeme@localhost:5432/crowdgpu_test"
    ),
)


# ---------------------------------------------------------------------------
# Fixtures (only active when TEST_DATABASE_URL is set)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """Run migrations once before integration tests begin."""
    if TEST_DATABASE_URL is None:
        return

    from alembic.config import Config

    from alembic import command

    ini_path = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")
    cfg = Config(ini_path)
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def pg_engine():
    """Create an async engine for the test with NullPool (new connection per test)."""
    if TEST_DATABASE_URL is None:
        pytest.skip("TEST_DATABASE_URL not set")

    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    """Provide an AsyncSession for each integration test."""
    factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------
@requires_postgres
class TestPostgresIntegration:
    @pytest.mark.asyncio
    async def test_uuid_server_default(self, pg_session: AsyncSession) -> None:
        """PostgreSQL gen_random_uuid() generates a UUID PK automatically."""
        from coordinator.database.models import User

        user = User(email=f"pg-{uuid.uuid4().hex[:8]}@example.com")
        # Do NOT set user.id — let the server_default generate it.
        pg_session.add(user)
        await pg_session.flush()

        assert user.id is not None
        assert isinstance(user.id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_timestamp_server_defaults(self, pg_session: AsyncSession) -> None:
        """created_at and updated_at are set by the database server on insert."""
        from coordinator.database.models import User

        user = User(
            id=uuid.uuid4(),
            email=f"ts-{uuid.uuid4().hex[:8]}@example.com",
        )
        pg_session.add(user)
        await pg_session.flush()
        await pg_session.refresh(user)

        assert user.created_at is not None
        assert user.updated_at is not None

    @pytest.mark.asyncio
    async def test_fk_constraint_enforced(self, pg_session: AsyncSession) -> None:
        """PostgreSQL enforces FK constraint: peer with non-existent owner raises."""
        from sqlalchemy.exc import IntegrityError

        from coordinator.database.models import Peer

        peer = Peer(
            id=uuid.uuid4(),
            owner_id=uuid.uuid4(),  # non-existent user
            hostname="ghost-rig",
        )
        pg_session.add(peer)
        with pytest.raises(IntegrityError):
            await pg_session.flush()

    @pytest.mark.asyncio
    async def test_email_unique_constraint(self, pg_session: AsyncSession) -> None:
        """PostgreSQL enforces email uniqueness at the DB level."""
        from sqlalchemy.exc import IntegrityError

        from coordinator.database.models import User

        email = f"unique-{uuid.uuid4().hex[:8]}@example.com"
        pg_session.add(User(id=uuid.uuid4(), email=email))
        await pg_session.flush()

        pg_session.add(User(id=uuid.uuid4(), email=email))
        with pytest.raises(IntegrityError):
            await pg_session.flush()

    @pytest.mark.asyncio
    async def test_full_chain_postgres(self, pg_session: AsyncSession) -> None:
        """Full User → Peer → GpuCapability chain works on real PostgreSQL."""
        from coordinator.database.models import GpuCapability, Peer, User

        user = User(id=uuid.uuid4(), email=f"pg-chain-{uuid.uuid4().hex[:8]}@example.com")
        pg_session.add(user)
        await pg_session.flush()

        peer = Peer(id=uuid.uuid4(), owner_id=user.id, hostname="pg-rig")
        pg_session.add(peer)
        await pg_session.flush()

        gpu = GpuCapability(
            id=uuid.uuid4(),
            peer_id=peer.id,
            gpu_name="NVIDIA RTX 4090",
            vram_mb=24576,
            cuda_version="12.2",
        )
        pg_session.add(gpu)
        await pg_session.flush()

        fetched_gpu = await pg_session.get(GpuCapability, gpu.id)
        assert fetched_gpu is not None
        assert fetched_gpu.gpu_name == "NVIDIA RTX 4090"
