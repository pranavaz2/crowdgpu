"""
Unit tests for Peer Registration & Discovery API — ADR-003 Tier 1.

Uses an in-memory SQLite database via aiosqlite to validate:
- Peer registration with single and multiple GPUs
- Owner existence validation (404 on unknown owner)
- Payload validation (422 on invalid input)
- Peer retrieval and 404 handling
- Heartbeat timestamp update (server-controlled) and status transitions
- Soft-deregistration (offline state, record preserved)
- Atomic transactional rollback on failure
"""

import datetime
import uuid
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from coordinator.database.base import Base
from coordinator.database.models import GpuCapability, Peer, User
from coordinator.database.session import get_db
from coordinator.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Database and client fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="module")
async def test_engine():
    """Create in-memory SQLite engine with foreign key enforcement."""
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(test_engine):
    """Return an async sessionmaker for the test engine."""
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory):
    """Provide a direct AsyncSession for test assertions/seeding."""
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_client(session_factory):
    """Provide an AsyncClient configured with test database dependency overrides."""
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_user(db_session: AsyncSession) -> User:
    """Seed a valid user in the database."""
    user = User(
        id=uuid.uuid4(),
        email=f"provider-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Test Provider",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Test Cases: Registration
# ---------------------------------------------------------------------------
class TestPeerRegistration:
    @pytest.mark.asyncio
    async def test_register_peer_success_single_gpu(
        self,
        test_client: httpx.AsyncClient,
        seeded_user: User,
    ) -> None:
        """Registering a peer with one GPU persists both peer and capability."""
        payload = {
            "owner_id": str(seeded_user.id),
            "hostname": "rig-alpha-01",
            "initial_status": "available",
            "gpu_capabilities": [
                {
                    "gpu_name": "NVIDIA GeForce RTX 4090",
                    "vram_mb": 24576,
                    "driver_version": "535.104.05",
                    "cuda_version": "12.2",
                    "compute_capability": "8.9",
                }
            ],
        }

        response = await test_client.post("/api/v1/peers", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert "id" in data
        assert data["owner_id"] == str(seeded_user.id)
        assert data["hostname"] == "rig-alpha-01"
        assert data["status"] == "available"
        assert data["registered_at"] is not None
        assert data["last_seen_at"] is not None
        assert len(data["gpu_capabilities"]) == 1

        gpu = data["gpu_capabilities"][0]
        assert gpu["gpu_name"] == "NVIDIA GeForce RTX 4090"
        assert gpu["vram_mb"] == 24576
        assert gpu["driver_version"] == "535.104.05"
        assert gpu["cuda_version"] == "12.2"
        assert gpu["compute_capability"] == "8.9"
        assert gpu["peer_id"] == data["id"]

    @pytest.mark.asyncio
    async def test_register_peer_success_multiple_gpus(
        self,
        test_client: httpx.AsyncClient,
        seeded_user: User,
    ) -> None:
        """Registering a peer with multiple GPUs persists all capability records."""
        payload = {
            "owner_id": str(seeded_user.id),
            "hostname": "multi-rig-02",
            "gpu_capabilities": [
                {"gpu_name": "NVIDIA RTX 4090", "vram_mb": 24576},
                {"gpu_name": "NVIDIA RTX 3080", "vram_mb": 10240},
            ],
        }

        response = await test_client.post("/api/v1/peers", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert len(data["gpu_capabilities"]) == 2
        gpu_names = [g["gpu_name"] for g in data["gpu_capabilities"]]
        assert "NVIDIA RTX 4090" in gpu_names
        assert "NVIDIA RTX 3080" in gpu_names

    @pytest.mark.asyncio
    async def test_register_peer_owner_not_found(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Registration fails with 404 when owner user does not exist."""
        ghost_user_id = str(uuid.uuid4())
        payload = {
            "owner_id": ghost_user_id,
            "hostname": "orphan-rig",
            "gpu_capabilities": [{"gpu_name": "RTX 4090", "vram_mb": 24576}],
        }

        response = await test_client.post("/api/v1/peers", json=payload)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_peer_validation_missing_hostname(
        self,
        test_client: httpx.AsyncClient,
        seeded_user: User,
    ) -> None:
        """Registration fails with 422 if hostname is empty or missing."""
        payload = {
            "owner_id": str(seeded_user.id),
            "hostname": "",
            "gpu_capabilities": [{"gpu_name": "RTX 4090", "vram_mb": 24576}],
        }
        response = await test_client.post("/api/v1/peers", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_peer_validation_empty_gpus(
        self,
        test_client: httpx.AsyncClient,
        seeded_user: User,
    ) -> None:
        """Registration fails with 422 if no GPU capabilities are provided."""
        payload = {
            "owner_id": str(seeded_user.id),
            "hostname": "nogpu-rig",
            "gpu_capabilities": [],
        }
        response = await test_client.post("/api/v1/peers", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_peer_validation_negative_vram(
        self,
        test_client: httpx.AsyncClient,
        seeded_user: User,
    ) -> None:
        """Registration fails with 422 if vram_mb is <= 0."""
        payload = {
            "owner_id": str(seeded_user.id),
            "hostname": "bad-vram-rig",
            "gpu_capabilities": [{"gpu_name": "RTX 4090", "vram_mb": -100}],
        }
        response = await test_client.post("/api/v1/peers", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test Cases: Retrieval
# ---------------------------------------------------------------------------
class TestPeerRetrieval:
    @pytest.mark.asyncio
    async def test_get_peer_success(
        self,
        test_client: httpx.AsyncClient,
        seeded_user: User,
    ) -> None:
        """GET /api/v1/peers/{id} returns full peer and GPU details."""
        # First register
        reg_payload = {
            "owner_id": str(seeded_user.id),
            "hostname": "fetch-rig",
            "gpu_capabilities": [{"gpu_name": "RTX 4090", "vram_mb": 24576}],
        }
        reg_res = await test_client.post("/api/v1/peers", json=reg_payload)
        peer_id = reg_res.json()["id"]

        # Fetch
        get_res = await test_client.get(f"/api/v1/peers/{peer_id}")
        assert get_res.status_code == 200

        data = get_res.json()
        assert data["id"] == peer_id
        assert data["hostname"] == "fetch-rig"
        assert len(data["gpu_capabilities"]) == 1

    @pytest.mark.asyncio
    async def test_get_peer_not_found(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """GET /api/v1/peers/{id} returns 404 for non-existent peer."""
        unknown_id = str(uuid.uuid4())
        response = await test_client.get(f"/api/v1/peers/{unknown_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_peer_invalid_uuid(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """GET /api/v1/peers/{id} returns 422 for malformed UUID."""
        response = await test_client.get("/api/v1/peers/not-a-valid-uuid")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test Cases: Heartbeat
# ---------------------------------------------------------------------------
class TestPeerHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_updates_server_timestamp(
        self,
        test_client: httpx.AsyncClient,
        seeded_user: User,
    ) -> None:
        """Heartbeat updates last_seen_at using server UTC time."""
        reg_payload = {
            "owner_id": str(seeded_user.id),
            "hostname": "heartbeat-rig",
            "gpu_capabilities": [{"gpu_name": "RTX 4090", "vram_mb": 24576}],
        }
        reg_res = await test_client.post("/api/v1/peers", json=reg_payload)
        peer_id = reg_res.json()["id"]
        initial_seen = reg_res.json()["last_seen_at"]

        # Send heartbeat
        hb_res = await test_client.patch(f"/api/v1/peers/{peer_id}/heartbeat")
        assert hb_res.status_code == 200

        updated_data = hb_res.json()
        assert updated_data["last_seen_at"] is not None
        # Verify it's a valid ISO timestamp
        new_seen = datetime.datetime.fromisoformat(updated_data["last_seen_at"])
        old_seen = datetime.datetime.fromisoformat(initial_seen)
        assert new_seen >= old_seen

    @pytest.mark.asyncio
    async def test_heartbeat_status_transition(
        self,
        test_client: httpx.AsyncClient,
        seeded_user: User,
    ) -> None:
        """Heartbeat can transition status to busy and back to available."""
        reg_payload = {
            "owner_id": str(seeded_user.id),
            "hostname": "status-rig",
            "gpu_capabilities": [{"gpu_name": "RTX 4090", "vram_mb": 24576}],
        }
        reg_res = await test_client.post("/api/v1/peers", json=reg_payload)
        peer_id = reg_res.json()["id"]
        assert reg_res.json()["status"] == "available"

        # Update to busy
        busy_res = await test_client.patch(
            f"/api/v1/peers/{peer_id}/heartbeat",
            json={"status": "busy"},
        )
        assert busy_res.status_code == 200
        assert busy_res.json()["status"] == "busy"

        # Update back to available
        avail_res = await test_client.patch(
            f"/api/v1/peers/{peer_id}/heartbeat",
            json={"status": "available"},
        )
        assert avail_res.status_code == 200
        assert avail_res.json()["status"] == "available"

    @pytest.mark.asyncio
    async def test_heartbeat_unknown_peer(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Heartbeat on unknown peer returns 404."""
        unknown_id = str(uuid.uuid4())
        response = await test_client.patch(f"/api/v1/peers/{unknown_id}/heartbeat")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test Cases: Deregistration
# ---------------------------------------------------------------------------
class TestPeerDeregistration:
    @pytest.mark.asyncio
    async def test_deregister_peer_marks_offline_and_preserves_record(
        self,
        test_client: httpx.AsyncClient,
        db_session: AsyncSession,
        seeded_user: User,
    ) -> None:
        """Deregistration sets status to offline and does NOT delete DB row."""
        reg_payload = {
            "owner_id": str(seeded_user.id),
            "hostname": "dereg-rig",
            "gpu_capabilities": [{"gpu_name": "RTX 4090", "vram_mb": 24576}],
        }
        reg_res = await test_client.post("/api/v1/peers", json=reg_payload)
        peer_id = uuid.UUID(reg_res.json()["id"])

        # Deregister
        dereg_res = await test_client.post(f"/api/v1/peers/{peer_id}/deregister")
        assert dereg_res.status_code == 200
        assert dereg_res.json()["status"] == "offline"

        # Verify peer record still exists in DB
        db_peer = await db_session.get(Peer, peer_id)
        assert db_peer is not None
        assert db_peer.status == "offline"
        assert db_peer.hostname == "dereg-rig"

        # Verify GPU capability record still exists in DB
        stmt = select(GpuCapability).where(GpuCapability.peer_id == peer_id)
        result = await db_session.execute(stmt)
        gpus = result.scalars().all()
        assert len(gpus) == 1

    @pytest.mark.asyncio
    async def test_deregister_unknown_peer(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Deregistration on unknown peer returns 404."""
        unknown_id = str(uuid.uuid4())
        response = await test_client.post(f"/api/v1/peers/{unknown_id}/deregister")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test Cases: Transactional Atomicity
# ---------------------------------------------------------------------------
class TestAtomicRegistration:
    @pytest.mark.asyncio
    async def test_registration_rolls_back_on_capability_failure(
        self,
        db_session: AsyncSession,
        seeded_user: User,
    ) -> None:
        """If GPU capability creation fails, the Peer record must NOT be persisted."""
        from coordinator.peers.schemas import GpuCapabilityCreate, PeerRegisterRequest
        from coordinator.peers.service import PeerService

        payload = PeerRegisterRequest(
            owner_id=seeded_user.id,
            hostname="atomic-fail-rig",
            gpu_capabilities=[
                GpuCapabilityCreate(gpu_name="RTX 4090", vram_mb=24576),
            ],
        )

        # Force an error during commit
        with (
            patch.object(
                AsyncSession,
                "commit",
                side_effect=RuntimeError("Simulated DB error during commit"),
            ),
            pytest.raises(RuntimeError),
        ):
            await PeerService.register_peer(db_session, payload)

        # Verify peer was NOT persisted
        stmt = select(Peer).where(Peer.hostname == "atomic-fail-rig")
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None
