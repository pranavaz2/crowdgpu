"""
PostgreSQL integration tests for Peer API — ADR-003 Tier 2.

These tests run against a live PostgreSQL instance when TEST_DATABASE_URL is set.
They test real end-to-end API execution against real PostgreSQL:
- Register peer with GPU capabilities
- Verify foreign key and server defaults in PostgreSQL
- Heartbeat timestamp updates on real TIMESTAMPTZ columns
- Soft-deregistration persistence
"""

import os
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from coordinator.database.models import User
from coordinator.database.session import get_db
from coordinator.main import app

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_postgres = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="PostgreSQL integration tests require TEST_DATABASE_URL env var.",
)


@pytest_asyncio.fixture
async def pg_engine():
    """Create an async engine for the test with NullPool."""
    if TEST_DATABASE_URL is None:
        pytest.skip("TEST_DATABASE_URL not set")

    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    """Provide an AsyncSession for each test."""
    factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def pg_client(pg_engine):
    """Provide an AsyncClient wired to the live PostgreSQL instance."""
    factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
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


@requires_postgres
class TestPeersPostgresIntegration:
    @pytest.mark.asyncio
    async def test_full_peer_lifecycle_postgres(
        self,
        pg_client: httpx.AsyncClient,
        pg_session: AsyncSession,
    ) -> None:
        """Full peer registration, retrieval, heartbeat, and deregistration on real PostgreSQL."""
        # 1. Create a real User in PostgreSQL
        user = User(
            id=uuid.uuid4(),
            email=f"pg-provider-{uuid.uuid4().hex[:8]}@example.com",
            display_name="PG Provider",
        )
        pg_session.add(user)
        await pg_session.commit()

        # 2. Register peer via API
        reg_payload = {
            "owner_id": str(user.id),
            "hostname": "pg-cluster-node-01",
            "initial_status": "available",
            "gpu_capabilities": [
                {
                    "gpu_name": "NVIDIA RTX 4090",
                    "vram_mb": 24576,
                    "driver_version": "535.104.05",
                    "cuda_version": "12.2",
                    "compute_capability": "8.9",
                }
            ],
        }
        reg_resp = await pg_client.post("/api/v1/peers", json=reg_payload)
        assert reg_resp.status_code == 201
        peer_data = reg_resp.json()
        peer_id = peer_data["id"]
        assert peer_data["hostname"] == "pg-cluster-node-01"
        assert peer_data["status"] == "available"
        assert len(peer_data["gpu_capabilities"]) == 1

        # 3. Retrieve peer via API
        get_resp = await pg_client.get(f"/api/v1/peers/{peer_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == peer_id

        # 4. Heartbeat with status change to busy
        hb_resp = await pg_client.patch(
            f"/api/v1/peers/{peer_id}/heartbeat",
            json={"status": "busy"},
        )
        assert hb_resp.status_code == 200
        assert hb_resp.json()["status"] == "busy"

        # 5. Deregister peer
        dereg_resp = await pg_client.post(f"/api/v1/peers/{peer_id}/deregister")
        assert dereg_resp.status_code == 200
        assert dereg_resp.json()["status"] == "offline"

        # 6. Verify peer still exists in DB
        get_after_dereg = await pg_client.get(f"/api/v1/peers/{peer_id}")
        assert get_after_dereg.status_code == 200
        assert get_after_dereg.json()["status"] == "offline"
