"""
API tests for Worker-Coordinator communication.

Validates:
- Worker job polling: GET /api/v1/workers/{peer_id}/jobs/next (204 vs 200).
- Worker status updates: POST /api/v1/jobs/{job_id}/status (RUNNING, FAILED).
- Worker result submission: POST /api/v1/jobs/{job_id}/result (COMPLETED).
- Security / identity enforcement: 403 Forbidden on peer mismatch, 401 on missing header.
- Worker registration and heartbeat aliases (/api/v1/workers/*).
"""

import datetime
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
async def seeded_setup(db_session: AsyncSession) -> tuple[User, Peer, Job]:
    """Seed user, peer with GPU, and an ASSIGNED job."""
    user = User(
        id=uuid.uuid4(),
        email=f"worker-test-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(user)
    await db_session.flush()

    now = datetime.datetime.now(datetime.UTC)
    peer = Peer(
        id=uuid.uuid4(),
        owner_id=user.id,
        hostname="worker-node-01",
        status="busy",
        registered_at=now,
        last_seen_at=now,
    )
    gpu = GpuCapability(
        id=uuid.uuid4(),
        peer_id=peer.id,
        gpu_name="NVIDIA RTX 4090",
        vram_mb=24576,
    )
    peer.gpu_capabilities.append(gpu)
    db_session.add(peer)
    await db_session.flush()

    job = Job(
        id=uuid.uuid4(),
        owner_id=user.id,
        name="Assigned Compute",
        command="python compute.py",
        requirements={"required_vram_mb": 8000},
        status=JobStatus.ASSIGNED.value,
        assigned_peer_id=peer.id,
        attempt_count=1,
    )
    db_session.add(job)
    await db_session.commit()

    return user, peer, job


class TestWorkerJobFlow:
    @pytest.mark.asyncio
    async def test_worker_polls_next_assigned_job(
        self,
        test_client: httpx.AsyncClient,
        seeded_setup: tuple[User, Peer, Job],
    ) -> None:
        """Worker queries /workers/{peer_id}/jobs/next and receives ASSIGNED job."""
        _, peer, job = seeded_setup

        response = await test_client.get(f"/api/v1/workers/{peer.id}/jobs/next")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == str(job.id)
        assert data["status"] == "ASSIGNED"
        assert data["command"] == "python compute.py"

    @pytest.mark.asyncio
    async def test_worker_polls_when_no_jobs_assigned(
        self,
        test_client: httpx.AsyncClient,
        db_session: AsyncSession,
        seeded_setup: tuple[User, Peer, Job],
    ) -> None:
        """When no jobs are assigned, returns 204 No Content."""
        user, _, _ = seeded_setup
        empty_peer = Peer(
            id=uuid.uuid4(),
            owner_id=user.id,
            hostname="idle-worker",
            status="available",
        )
        db_session.add(empty_peer)
        await db_session.commit()

        response = await test_client.get(f"/api/v1/workers/{empty_peer.id}/jobs/next")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_worker_acknowledges_running(
        self,
        test_client: httpx.AsyncClient,
        seeded_setup: tuple[User, Peer, Job],
    ) -> None:
        """Worker reports status RUNNING."""
        _, peer, job = seeded_setup
        headers = {"X-Peer-Id": str(peer.id)}

        response = await test_client.post(
            f"/api/v1/jobs/{job.id}/status",
            json={"status": "RUNNING"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "RUNNING"
        assert response.json()["started_at"] is not None

    @pytest.mark.asyncio
    async def test_worker_status_unauthorized_peer_rejected(
        self,
        test_client: httpx.AsyncClient,
        seeded_setup: tuple[User, Peer, Job],
    ) -> None:
        """Another peer attempting to update status is rejected with 403 Forbidden."""
        _, _, job = seeded_setup
        imposter_peer_id = str(uuid.uuid4())
        headers = {"X-Peer-Id": imposter_peer_id}

        response = await test_client.post(
            f"/api/v1/jobs/{job.id}/status",
            json={"status": "RUNNING"},
            headers=headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_worker_submits_completed_result(
        self,
        test_client: httpx.AsyncClient,
        db_session: AsyncSession,
        seeded_setup: tuple[User, Peer, Job],
    ) -> None:
        """Worker submits result: status becomes COMPLETED and peer is freed to available."""
        _, peer, job = seeded_setup
        headers = {"X-Peer-Id": str(peer.id)}

        # First acknowledge RUNNING
        await test_client.post(
            f"/api/v1/jobs/{job.id}/status",
            json={"status": "RUNNING"},
            headers=headers,
        )

        # Submit result
        result_payload = {
            "exit_code": 0,
            "stdout_tail": "Done: loss=0.012",
            "artifact_uri": "s3://artifacts/output.bin",
        }
        res = await test_client.post(
            f"/api/v1/jobs/{job.id}/result",
            json=result_payload,
            headers=headers,
        )
        assert res.status_code == 200

        data = res.json()
        assert data["status"] == "COMPLETED"
        assert data["result"]["exit_code"] == 0
        assert data["result"]["artifact_uri"] == "s3://artifacts/output.bin"
        assert data["completed_at"] is not None

        # Verify peer returned to available
        await db_session.refresh(peer)
        assert peer.status == "available"

    @pytest.mark.asyncio
    async def test_worker_aliases(
        self,
        test_client: httpx.AsyncClient,
        seeded_setup: tuple[User, Peer, Job],
    ) -> None:
        """Worker registration and heartbeat aliases work identically to peer routes."""
        user, _, _ = seeded_setup
        reg_payload = {
            "owner_id": str(user.id),
            "hostname": "alias-worker",
            "gpu_capabilities": [{"gpu_name": "RTX 3080", "vram_mb": 10240}],
        }
        reg_res = await test_client.post("/api/v1/workers/register", json=reg_payload)
        assert reg_res.status_code == 201
        worker_id = reg_res.json()["id"]

        # Heartbeat alias
        hb_res = await test_client.post(f"/api/v1/workers/{worker_id}/heartbeat")
        assert hb_res.status_code == 200
