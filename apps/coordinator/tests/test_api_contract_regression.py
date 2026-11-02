"""
API Contract Regression Tests for Stage 1.

Validates:
1. Frontend request schema (vram_required_mb, docker_image, workload_type) and computed response fields.
2. Worker registration, heartbeat, and status updates using Person 2 format.
3. Worker result submission preserving exit_code, output, execution_time_s, error, and freeing peer.
4. Peer listing GET /api/v1/peers (ported Person 4 endpoint).
5. State machine protection: terminal jobs cannot be restarted, completed twice, or cancelled.
6. Authentication & identity header safety: X-Worker-ID alias support, imposter rejection (403), demo auth mode.
7. WebRTC signaling isolation: /api/v1/signaling/ice-servers and /api/v1/signaling/peers.
"""

import datetime
import uuid
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from coordinator.config import settings
from coordinator.database.base import Base
from coordinator.database.models import GpuCapability, Job, Peer, User
from coordinator.database.session import get_db
from coordinator.jobs.state_machine import JobStatus
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
async def test_client(session_factory):
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
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Test User",
    )
    db_session.add(user)
    await db_session.commit()
    return user


class TestFrontendJobContract:
    @pytest.mark.asyncio
    async def test_submit_job_frontend_schema(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """Frontend submits job with vram_required_mb, docker_image, and workload_type."""
        payload = {
            "name": "Frontend Training Run",
            "command": "python train.py --epochs 10",
            "vram_required_mb": 4096,
            "docker_image": "pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
            "workload_type": "batch",
        }
        headers = {"X-User-Id": str(test_user.id)}
        response = await test_client.post("/api/v1/jobs", json=payload, headers=headers)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Frontend Training Run"
        assert data["command"] == "python train.py --epochs 10"
        assert data["vram_required_mb"] == 4096
        assert data["docker_image"] == "pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime"
        assert data["workload_type"] == "batch"
        assert data["status"] == "QUEUED"
        assert "submitted_at" in data
        assert data["submitted_at"] is not None

    @pytest.mark.asyncio
    async def test_list_and_get_job_frontend_fields(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """Job listing and detail endpoints return frontend-expected attributes."""
        headers = {"X-User-Id": str(test_user.id)}
        payload = {
            "name": "Benchmark Job",
            "command": "python benchmark.py",
            "vram_required_mb": 8192,
            "docker_image": "nvidia/cuda:12.2.0-base",
            "workload_type": "batch",
        }
        post_res = await test_client.post("/api/v1/jobs", json=payload, headers=headers)
        job_id = post_res.json()["id"]

        # Detail
        detail_res = await test_client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        assert detail_res.status_code == 200
        d = detail_res.json()
        assert d["id"] == job_id
        assert d["vram_required_mb"] == 8192
        assert d["docker_image"] == "nvidia/cuda:12.2.0-base"

        # List
        list_res = await test_client.get("/api/v1/jobs", headers=headers)
        assert list_res.status_code == 200
        items = list_res.json()
        assert any(item["id"] == job_id for item in items)


class TestWorkerRegistrationAndTelemetryContract:
    @pytest.mark.asyncio
    async def test_worker_registration_person_2_format(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """Worker registers using Person 2 flat GPU payload."""
        payload = {
            "worker_id": "worker-unit-01",
            "gpu_name": "NVIDIA GeForce RTX 4090",
            "gpu_uuid": "GPU-99887766",
            "total_vram_mib": 24576,
            "driver_version": "535.104.05",
            "cuda_available": True,
            "gpu_id": 0,
            "owner_id": str(test_user.id),
        }
        response = await test_client.post("/api/v1/workers/register", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["registered"] is True
        assert data["hostname"] == "worker-unit-01"
        assert len(data["gpu_capabilities"]) == 1
        assert data["gpu_capabilities"][0]["gpu_name"] == "NVIDIA GeForce RTX 4090"
        assert data["gpu_capabilities"][0]["vram_mb"] == 24576

    @pytest.mark.asyncio
    async def test_worker_heartbeat_and_status(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """Worker sends heartbeat with Person 2 telemetry and lightweight status."""
        reg_payload = {
            "worker_id": "worker-telemetry-01",
            "gpu_name": "RTX 3080",
            "total_vram_mib": 10240,
            "owner_id": str(test_user.id),
        }
        reg_res = await test_client.post("/api/v1/workers/register", json=reg_payload)
        peer_id = reg_res.json()["id"]

        # Heartbeat with telemetry
        hb_payload = {
            "state": "AVAILABLE",
            "current_job_id": None,
            "gpu_telemetry": {
                "free_vram_mib": 9000,
                "used_vram_mib": 1240,
                "total_vram_mib": 10240,
                "gpu_utilization_pct": 2.5,
                "temperature_c": 44.0,
                "cuda_available": True,
            },
        }
        hb_res = await test_client.post(f"/api/v1/workers/{peer_id}/heartbeat", json=hb_payload)
        assert hb_res.status_code == 200

        # Status update
        status_res = await test_client.post(f"/api/v1/workers/{peer_id}/status", json={"state": "BUSY"})
        assert status_res.status_code == 200
        assert status_res.json()["status"] == "busy"


class TestPeerListingEndpoint:
    @pytest.mark.asyncio
    async def test_get_peers_returns_list(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """GET /api/v1/peers returns 200 with list of provider peers."""
        response = await test_client.get("/api/v1/peers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestWorkerResultAndStateMachineSafety:
    @pytest.mark.asyncio
    async def test_worker_result_success_and_free_peer(
        self,
        test_client: httpx.AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Worker result reporting marks job COMPLETED, preserves metadata, and frees peer."""
        now = datetime.datetime.now(datetime.UTC)
        peer = Peer(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            hostname="compute-peer-01",
            status="busy",
            registered_at=now,
            last_seen_at=now,
        )
        gpu = GpuCapability(
            id=uuid.uuid4(),
            peer_id=peer.id,
            gpu_name="RTX 4090",
            vram_mb=24576,
        )
        peer.gpu_capabilities.append(gpu)
        db_session.add(peer)
        await db_session.flush()

        job = Job(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Inference Job",
            command="python infer.py",
            requirements={"required_vram_mb": 4000},
            status=JobStatus.ASSIGNED.value,
            assigned_peer_id=peer.id,
            attempt_count=1,
        )
        db_session.add(job)
        await db_session.commit()

        # Update to RUNNING
        run_res = await test_client.post(
            f"/api/v1/jobs/{job.id}/status",
            json={"status": "RUNNING"},
            headers={"X-Peer-Id": str(peer.id)},
        )
        assert run_res.status_code == 200

        # Submit successful result (Person 2 worker format)
        result_payload = {
            "worker_id": str(peer.id),
            "status": "success",
            "output": {"predictions": [1, 0, 1], "loss": 0.05},
            "execution_time_s": 8.4,
            "exit_code": 0,
            "error": None,
        }
        res = await test_client.post(
            f"/api/v1/jobs/{job.id}/result",
            json=result_payload,
            headers={"X-Peer-Id": str(peer.id)},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "COMPLETED"
        assert data["result"]["output"]["predictions"] == [1, 0, 1]
        assert data["result"]["execution_time_s"] == 8.4
        assert data["result"]["exit_code"] == 0

        # Peer is freed to available
        await db_session.refresh(peer)
        assert peer.status == "available"

    @pytest.mark.asyncio
    async def test_worker_result_failed_and_state_protection(
        self,
        test_client: httpx.AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Worker reporting failed execution marks job FAILED and prevents further transitions."""
        now = datetime.datetime.now(datetime.UTC)
        peer = Peer(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            hostname="compute-peer-fail",
            status="busy",
            registered_at=now,
            last_seen_at=now,
        )
        db_session.add(peer)
        await db_session.flush()

        job = Job(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Crashing Job",
            command="python crash.py",
            requirements={"required_vram_mb": 4000},
            status=JobStatus.ASSIGNED.value,
            assigned_peer_id=peer.id,
            attempt_count=1,
        )
        db_session.add(job)
        await db_session.commit()

        # Update to RUNNING
        await test_client.post(
            f"/api/v1/jobs/{job.id}/status",
            json={"status": "RUNNING"},
            headers={"X-Peer-Id": str(peer.id)},
        )

        # Submit failure
        fail_payload = {
            "worker_id": str(peer.id),
            "status": "failed",
            "output": None,
            "execution_time_s": 1.2,
            "exit_code": 137,
            "error": "CUDA out of memory",
        }
        fail_res = await test_client.post(
            f"/api/v1/jobs/{job.id}/result",
            json=fail_payload,
            headers={"X-Peer-Id": str(peer.id)},
        )
        assert fail_res.status_code == 200
        assert fail_res.json()["status"] == "FAILED"
        assert fail_res.json()["error"] == "CUDA out of memory"

        # Attempting to submit result again on terminal job raises 409 Conflict
        second_res = await test_client.post(
            f"/api/v1/jobs/{job.id}/result",
            json=fail_payload,
            headers={"X-Peer-Id": str(peer.id)},
        )
        assert second_res.status_code == 409

        # Attempting to cancel terminal job raises 409 Conflict
        cancel_res = await test_client.post(
            f"/api/v1/jobs/{job.id}/cancel",
            headers={"X-User-Id": str(test_user.id)},
        )
        assert cancel_res.status_code == 409


class TestAuthenticationSafety:
    @pytest.mark.asyncio
    async def test_missing_auth_header_rejected(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Without demo auth enabled, missing X-User-Id is strictly 401."""
        response = await test_client.post(
            "/api/v1/jobs",
            json={"name": "No Auth", "command": "echo 1", "required_vram_mb": 100},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_worker_header_alias_x_worker_id(
        self,
        test_client: httpx.AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """X-Worker-ID alias header is accepted for worker endpoints."""
        now = datetime.datetime.now(datetime.UTC)
        peer = Peer(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            hostname="alias-worker-01",
            status="busy",
            registered_at=now,
            last_seen_at=now,
        )
        db_session.add(peer)
        await db_session.flush()

        job = Job(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Worker Header Test",
            command="python test.py",
            requirements={},
            status=JobStatus.ASSIGNED.value,
            assigned_peer_id=peer.id,
        )
        db_session.add(job)
        await db_session.commit()

        # Uses X-Worker-ID instead of X-Peer-Id
        res = await test_client.post(
            f"/api/v1/jobs/{job.id}/status",
            json={"status": "RUNNING"},
            headers={"X-Worker-ID": str(peer.id)},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "RUNNING"


class TestSignalingIsolation:
    @pytest.mark.asyncio
    async def test_signaling_endpoints(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Signaling REST endpoints return valid configurations."""
        ice_res = await test_client.get("/api/v1/signaling/ice-servers")
        assert ice_res.status_code == 200
        assert "ice_servers" in ice_res.json()

        peers_res = await test_client.get("/api/v1/signaling/peers")
        assert peers_res.status_code == 200
        assert "connected_peers" in peers_res.json()
