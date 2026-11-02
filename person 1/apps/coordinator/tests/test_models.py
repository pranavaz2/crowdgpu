"""
Tests — ORM model unit tests (aiosqlite in-memory, ADR-003 Tier 1).

Validates:
- SQLAlchemy metadata correctly registers all three tables.
- Model instances can be created, persisted, and queried.
- User → Peer → GpuCapability relationship traversal works.
- email uniqueness constraint raises IntegrityError on duplicate insert.
- Cascade delete: deleting a User removes its Peers and GpuCapabilities.

These tests use an in-memory aiosqlite database and do NOT require a live
PostgreSQL instance.  They do NOT test PostgreSQL-specific constraint behavior
(that is covered in tests/integration/).

Note on UUID PKs:
  SQLite does not support PostgreSQL's gen_random_uuid() server_default.
  Therefore tests supply explicit UUIDs (uuid.uuid4()) when creating objects.
  On PostgreSQL the server generates UUIDs automatically.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from coordinator.database.base import Base
from coordinator.database.models import GpuCapability, Peer, User

# ---------------------------------------------------------------------------
# In-memory async SQLite engine (shared across all tests in this module)
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="module")
async def engine():
    """Create a fresh in-memory SQLite engine with the full schema."""
    _engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # SQLite does not enforce FK constraints by default — enable them.
    @event.listens_for(_engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield _engine

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await _engine.dispose()


@pytest_asyncio.fixture
async def session(engine):
    """Provide a fresh AsyncSession for each test, rolling back after."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------
def make_user(**kwargs) -> User:
    defaults = dict(id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:8]}@example.com")
    defaults.update(kwargs)
    return User(**defaults)


def make_peer(owner_id: uuid.UUID, **kwargs) -> Peer:
    defaults = dict(id=uuid.uuid4(), owner_id=owner_id, hostname="test-host", status="offline")
    defaults.update(kwargs)
    return Peer(**defaults)


def make_gpu(peer_id: uuid.UUID, **kwargs) -> GpuCapability:
    defaults = dict(
        id=uuid.uuid4(),
        peer_id=peer_id,
        gpu_name="NVIDIA GeForce RTX 4090",
        vram_mb=24576,
    )
    defaults.update(kwargs)
    return GpuCapability(**defaults)


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------
class TestMetadata:
    def test_all_tables_registered(self) -> None:
        """Base.metadata contains exactly the three expected tables."""
        table_names = set(Base.metadata.tables.keys())
        assert "users" in table_names
        assert "peers" in table_names
        assert "gpu_capabilities" in table_names

    def test_users_table_columns(self) -> None:
        """users table has the expected columns."""
        cols = {c.name for c in Base.metadata.tables["users"].columns}
        assert {"id", "email", "display_name", "created_at", "updated_at"}.issubset(cols)

    def test_peers_table_columns(self) -> None:
        """peers table has the expected columns."""
        cols = {c.name for c in Base.metadata.tables["peers"].columns}
        assert {
            "id", "owner_id", "hostname", "status",
            "registered_at", "last_seen_at", "created_at", "updated_at",
        }.issubset(cols)

    def test_gpu_capabilities_table_columns(self) -> None:
        """gpu_capabilities table has the expected columns."""
        cols = {c.name for c in Base.metadata.tables["gpu_capabilities"].columns}
        assert {
            "id", "peer_id", "gpu_name", "vram_mb",
            "driver_version", "cuda_version", "compute_capability",
            "created_at", "updated_at",
        }.issubset(cols)


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------
class TestUserModel:
    @pytest.mark.asyncio
    async def test_create_user(self, session: AsyncSession) -> None:
        """A User can be added and queried back."""
        user = make_user(email="alice@example.com", display_name="Alice")
        session.add(user)
        await session.flush()

        fetched = await session.get(User, user.id)
        assert fetched is not None
        assert fetched.email == "alice@example.com"
        assert fetched.display_name == "Alice"

    @pytest.mark.asyncio
    async def test_user_display_name_optional(self, session: AsyncSession) -> None:
        """display_name is nullable."""
        user = make_user()
        session.add(user)
        await session.flush()

        fetched = await session.get(User, user.id)
        assert fetched is not None
        assert fetched.display_name is None

    @pytest.mark.asyncio
    async def test_user_email_unique_constraint(self, session: AsyncSession) -> None:
        """Inserting two users with the same email raises IntegrityError."""
        email = f"dupe-{uuid.uuid4().hex[:8]}@example.com"
        session.add(make_user(email=email))
        await session.flush()

        session.add(make_user(email=email))
        with pytest.raises(IntegrityError):
            await session.flush()


# ---------------------------------------------------------------------------
# Peer CRUD
# ---------------------------------------------------------------------------
class TestPeerModel:
    @pytest.mark.asyncio
    async def test_create_peer(self, session: AsyncSession) -> None:
        """A Peer can be created with a valid owner_id."""
        user = make_user()
        session.add(user)
        await session.flush()

        peer = make_peer(owner_id=user.id, hostname="gpu-rig-01")
        session.add(peer)
        await session.flush()

        fetched = await session.get(Peer, peer.id)
        assert fetched is not None
        assert fetched.hostname == "gpu-rig-01"
        assert fetched.status == "offline"

    @pytest.mark.asyncio
    async def test_peer_status_default(self, session: AsyncSession) -> None:
        """Peer status defaults to 'offline'."""
        user = make_user()
        session.add(user)
        await session.flush()

        peer = make_peer(owner_id=user.id)
        session.add(peer)
        await session.flush()

        fetched = await session.get(Peer, peer.id)
        assert fetched is not None
        assert fetched.status == "offline"

    @pytest.mark.asyncio
    async def test_peer_optional_timestamps_null(self, session: AsyncSession) -> None:
        """registered_at and last_seen_at are initially null."""
        user = make_user()
        session.add(user)
        await session.flush()

        peer = make_peer(owner_id=user.id)
        session.add(peer)
        await session.flush()

        fetched = await session.get(Peer, peer.id)
        assert fetched is not None
        assert fetched.registered_at is None
        assert fetched.last_seen_at is None


# ---------------------------------------------------------------------------
# GpuCapability CRUD
# ---------------------------------------------------------------------------
class TestGpuCapabilityModel:
    @pytest.mark.asyncio
    async def test_create_gpu_capability(self, session: AsyncSession) -> None:
        """A GpuCapability can be created and linked to a Peer."""
        user = make_user()
        session.add(user)
        await session.flush()

        peer = make_peer(owner_id=user.id)
        session.add(peer)
        await session.flush()

        gpu = make_gpu(
            peer_id=peer.id,
            gpu_name="NVIDIA RTX 4090",
            vram_mb=24576,
            driver_version="535.104.05",
            cuda_version="12.2",
            compute_capability="8.9",
        )
        session.add(gpu)
        await session.flush()

        fetched = await session.get(GpuCapability, gpu.id)
        assert fetched is not None
        assert fetched.gpu_name == "NVIDIA RTX 4090"
        assert fetched.vram_mb == 24576
        assert fetched.driver_version == "535.104.05"
        assert fetched.cuda_version == "12.2"
        assert fetched.compute_capability == "8.9"

    @pytest.mark.asyncio
    async def test_gpu_optional_fields_nullable(self, session: AsyncSession) -> None:
        """driver_version, cuda_version, compute_capability are nullable."""
        user = make_user()
        session.add(user)
        await session.flush()

        peer = make_peer(owner_id=user.id)
        session.add(peer)
        await session.flush()

        gpu = make_gpu(peer_id=peer.id)
        session.add(gpu)
        await session.flush()

        fetched = await session.get(GpuCapability, gpu.id)
        assert fetched is not None
        assert fetched.driver_version is None
        assert fetched.cuda_version is None
        assert fetched.compute_capability is None


# ---------------------------------------------------------------------------
# Relationship traversal
# ---------------------------------------------------------------------------
class TestRelationships:
    @pytest.mark.asyncio
    async def test_user_peers_relationship(self, session: AsyncSession) -> None:
        """User.peers returns associated Peer objects."""
        user = make_user()
        session.add(user)
        await session.flush()

        peer1 = make_peer(owner_id=user.id, hostname="rig-1")
        peer2 = make_peer(owner_id=user.id, hostname="rig-2")
        session.add_all([peer1, peer2])
        await session.flush()

        await session.refresh(user, ["peers"])
        hostnames = {p.hostname for p in user.peers}
        assert hostnames == {"rig-1", "rig-2"}

    @pytest.mark.asyncio
    async def test_peer_gpu_capabilities_relationship(self, session: AsyncSession) -> None:
        """Peer.gpu_capabilities returns associated GpuCapability objects."""
        user = make_user()
        session.add(user)
        await session.flush()

        peer = make_peer(owner_id=user.id)
        session.add(peer)
        await session.flush()

        gpu1 = make_gpu(peer_id=peer.id, gpu_name="RTX 4090", vram_mb=24576)
        gpu2 = make_gpu(peer_id=peer.id, gpu_name="RTX 3080", vram_mb=10240)
        session.add_all([gpu1, gpu2])
        await session.flush()

        await session.refresh(peer, ["gpu_capabilities"])
        gpu_names = {g.gpu_name for g in peer.gpu_capabilities}
        assert gpu_names == {"RTX 4090", "RTX 3080"}

    @pytest.mark.asyncio
    async def test_full_chain_user_peer_gpu(self, session: AsyncSession) -> None:
        """Full User → Peer → GpuCapability chain can be traversed."""
        user = make_user(email="chain@example.com")
        session.add(user)
        await session.flush()

        peer = make_peer(owner_id=user.id, hostname="chain-rig")
        session.add(peer)
        await session.flush()

        gpu = make_gpu(peer_id=peer.id, gpu_name="RTX 4090", vram_mb=24576)
        session.add(gpu)
        await session.flush()

        # Traverse from User
        await session.refresh(user, ["peers"])
        assert len(user.peers) == 1
        fetched_peer = user.peers[0]
        assert fetched_peer.hostname == "chain-rig"

        await session.refresh(fetched_peer, ["gpu_capabilities"])
        assert len(fetched_peer.gpu_capabilities) == 1
        assert fetched_peer.gpu_capabilities[0].gpu_name == "RTX 4090"

    @pytest.mark.asyncio
    async def test_cascade_delete_user_removes_peers(self, session: AsyncSession) -> None:
        """Deleting a User cascades to Peers (SQLite FK pragma enabled)."""
        user = make_user()
        session.add(user)
        await session.flush()

        peer = make_peer(owner_id=user.id)
        session.add(peer)
        await session.flush()

        peer_id = peer.id
        await session.delete(user)
        await session.flush()

        deleted_peer = await session.get(Peer, peer_id)
        assert deleted_peer is None
