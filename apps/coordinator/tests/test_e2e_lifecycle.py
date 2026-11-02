"""
End-to-End Job Lifecycle Integration Tests.

Validates the full control-plane lifecycle:
1. Peer registration with GPU hardware capabilities.
2. Heartbeat keeping peer in 'available' status.
3. Client submitting computational workload.
4. Scheduler matching requirements to peer and reserving peer (ASSIGNED state).
5. Worker pulling assignment via /workers/{peer_id}/jobs/next.
6. Worker reporting execution start (RUNNING state).
7. Worker completing workload and returning output/exit code (COMPLETED state).
8. Automatic peer resource release back to 'available'.
9. Resource insufficiency handling and cancellation.
10. Failure reporting and peer release.
"""

import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from coordinator.database.base import Base
from coordinator.database.models import Peer, User
from coordinator.database.session import get_db
from coordinator.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="module")
async def test_engine():
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
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestEndToEndLifecycle:
    @pytest.mark.asyncio
    async def test_complete_successful_lifecycle(
        self,
        client: httpx.AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Full happy path: Register -> Heartbeat -> Submit -> Match -> Ack -> Result -> Completed."""
        # 1. Create provider user and consumer user
        provider_user = User(id=uuid.uuid4(), email="provider@example.com")
        consumer_user = User(id=uuid.uuid4(), email="consumer@example.com")
        db_session.add_all([provider_user, consumer_user])
        await db_session.commit()

        # 2. Register GPU provider peer (24GB RTX 4090)
        reg_payload = {
            "owner_id": str(provider_user.id),
            "hostname": "alpha-rig-4090",
            "initial_status": "available",
            "gpu_capabilities": [
                {
                    "gpu_name": "NVIDIA GeForce RTX 4090",
                    "vram_mb": 24576,
                    "driver_version": "550.54.14",
                    "cuda_version": "12.4",
                    "compute_capability": "8.9",
                }
            ],
        }
        reg_res = await client.post("/api/v1/peers", json=reg_payload)
        assert reg_res.status_code == 201
        peer_id = reg_res.json()["id"]

        # 3. Provider sends heartbeat
        hb_res = await client.patch(f"/api/v1/peers/{peer_id}/heartbeat")
        assert hb_res.status_code == 200
        assert hb_res.json()["status"] == "available"

        # 4. Consumer submits GPU job requiring 4000 MB VRAM
        job_payload = {
            "name": "GPU Matrix Multiplication Benchmark",
            "command": "python benchmark_matmul.py --size 8192",
            "required_vram_mb": 4000,
        }
        consumer_headers = {"X-User-Id": str(consumer_user.id)}
        submit_res = await client.post("/api/v1/jobs", json=job_payload, headers=consumer_headers)
        assert submit_res.status_code == 201
        job_data = submit_res.json()
        job_id = job_data["id"]

        # The scheduler immediately assigned the available peer
        assert job_data["status"] == "ASSIGNED"
        assert job_data["assigned_peer_id"] == peer_id

        # 5. Worker polls for next assigned job
        next_job_res = await client.get(f"/api/v1/workers/{peer_id}/jobs/next")
        assert next_job_res.status_code == 200
        assert next_job_res.json()["id"] == job_id

        # 6. Worker acknowledges start (RUNNING)
        worker_headers = {"X-Peer-Id": str(peer_id)}
        ack_res = await client.post(
            f"/api/v1/jobs/{job_id}/status",
            json={"status": "RUNNING"},
            headers=worker_headers,
        )
        assert ack_res.status_code == 200
        assert ack_res.json()["status"] == "RUNNING"
        assert ack_res.json()["started_at"] is not None

        # 7. Worker completes workload and submits result
        result_payload = {
            "exit_code": 0,
            "stdout_tail": "Matrix multiplication completed in 2.14s. Peak VRAM: 3.8GB",
            "artifact_uri": "s3://crowdgpu-results/matmul-output.npy",
        }
        done_res = await client.post(
            f"/api/v1/jobs/{job_id}/result",
            json=result_payload,
            headers=worker_headers,
        )
        assert done_res.status_code == 200
        assert done_res.json()["status"] == "COMPLETED"
        assert done_res.json()["completed_at"] is not None
        assert done_res.json()["result"]["exit_code"] == 0

        # 8. Consumer checks job details
        final_job_res = await client.get(f"/api/v1/jobs/{job_id}", headers=consumer_headers)
        assert final_job_res.status_code == 200
        final_data = final_job_res.json()
        assert final_data["status"] == "COMPLETED"
        assert "Matrix multiplication completed" in final_data["result"]["stdout_tail"]

        # 9. Verify provider peer is freed back to 'available'
        peer_check = await client.get(f"/api/v1/peers/{peer_id}")
        assert peer_check.status_code == 200
        assert peer_check.json()["status"] == "available"

    @pytest.mark.asyncio
    async def test_resource_shortage_and_cancellation(
        self,
        client: httpx.AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Job with unmet requirements remains QUEUED and can be cancelled."""
        consumer_user = User(id=uuid.uuid4(), email="consumer-shortage@example.com")
        db_session.add(consumer_user)
        await db_session.commit()

        # Submit job requesting 180,000 MB VRAM (no peer has this much)
        job_payload = {
            "name": "Massive LLM Finetune",
            "command": "python finetune.py",
            "required_vram_mb": 180000,
        }
        headers = {"X-User-Id": str(consumer_user.id)}
        submit_res = await client.post("/api/v1/jobs", json=job_payload, headers=headers)
        assert submit_res.status_code == 201
        job_data = submit_res.json()
        assert job_data["status"] == "QUEUED"
        assert job_data["assigned_peer_id"] is None

        # Cancel the queued job
        cancel_res = await client.post(f"/api/v1/jobs/{job_data['id']}/cancel", headers=headers)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "CANCELLED"

    @pytest.mark.asyncio
    async def test_worker_failure_releases_peer(
        self,
        client: httpx.AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Worker failure marks job FAILED and frees peer."""
        provider_user = User(id=uuid.uuid4(), email="fail-prov@example.com")
        consumer_user = User(id=uuid.uuid4(), email="fail-cons@example.com")
        db_session.add_all([provider_user, consumer_user])
        await db_session.commit()

        reg_res = await client.post(
            "/api/v1/peers",
            json={
                "owner_id": str(provider_user.id),
                "hostname": "fail-rig",
                "initial_status": "available",
                "gpu_capabilities": [{"gpu_name": "RTX 3090", "vram_mb": 24576}],
            },
        )
        peer_id = reg_res.json()["id"]

        # Submit job
        submit_res = await client.post(
            "/api/v1/jobs",
            json={"name": "Will Fail", "command": "python crash.py", "required_vram_mb": 8000},
            headers={"X-User-Id": str(consumer_user.id)},
        )
        job_id = submit_res.json()["id"]
        assert submit_res.json()["status"] == "ASSIGNED"

        # Worker reports failure
        worker_headers = {"X-Peer-Id": str(peer_id)}
        fail_res = await client.post(
            f"/api/v1/jobs/{job_id}/status",
            json={"status": "FAILED", "error": "Process terminated with signal SIGSEGV"},
            headers=worker_headers,
        )
        assert fail_res.status_code == 200
        assert fail_res.json()["status"] == "FAILED"
        assert "SIGSEGV" in fail_res.json()["error"]

        # Peer is freed
        peer_check = await client.get(f"/api/v1/peers/{peer_id}")
        assert peer_check.json()["status"] == "available"
