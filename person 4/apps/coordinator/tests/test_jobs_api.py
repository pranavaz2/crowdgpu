import uuid
import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event

from coordinator.database.base import Base
from coordinator.database.models import User
from coordinator.database.session import get_db
from coordinator.main import app

pytestmark = pytest.mark.asyncio

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
async def seeded_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"provider-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Test Provider",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_submit_job_success(
    test_client: AsyncClient,
    seeded_user,
) -> None:
    payload = {
        "owner_id": str(seeded_user.id),
        "docker_image": "ubuntu:latest",
        "command": "echo hello",
    }
    response = await test_client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["owner_id"] == str(seeded_user.id)
    assert data["docker_image"] == "ubuntu:latest"
    assert data["command"] == "echo hello"
    assert data["status"] == "pending"
    assert "id" in data


async def test_submit_job_owner_not_found(
    test_client: AsyncClient,
) -> None:
    payload = {
        "owner_id": str(uuid.uuid4()),
        "docker_image": "ubuntu:latest",
        "command": "echo hello",
    }
    response = await test_client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_list_jobs(
    test_client: AsyncClient,
    seeded_user,
) -> None:
    payload = {
        "owner_id": str(seeded_user.id),
        "docker_image": "ubuntu:latest",
        "command": "echo hello",
    }
    await test_client.post("/api/v1/jobs", json=payload)
    
    response = await test_client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(job["owner_id"] == str(seeded_user.id) for job in data)

    # Test filtering
    response2 = await test_client.get(f"/api/v1/jobs?owner_id={seeded_user.id}")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2) >= 1

    ghost_id = str(uuid.uuid4())
    response3 = await test_client.get(f"/api/v1/jobs?owner_id={ghost_id}")
    assert response3.status_code == 200
    assert len(response3.json()) == 0


async def test_get_job(
    test_client: AsyncClient,
    seeded_user,
) -> None:
    payload = {
        "owner_id": str(seeded_user.id),
        "docker_image": "ubuntu:latest",
        "command": "echo hello",
    }
    create_res = await test_client.post("/api/v1/jobs", json=payload)
    job_id = create_res.json()["id"]

    response = await test_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["id"] == job_id


async def test_get_job_not_found(
    test_client: AsyncClient,
) -> None:
    response = await test_client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_assign_job_and_status_lifecycle(
    test_client: AsyncClient,
    seeded_user: User,
) -> None:
    """Test full job lifecycle: submit -> assign to peer -> running -> completed."""
    # 1. Register a peer
    peer_res = await test_client.post("/api/v1/peers", json={
        "owner_id": str(seeded_user.id),
        "hostname": "worker-rig-lifecycle",
        "initial_status": "available",
        "gpu_capabilities": [{"gpu_name": "NVIDIA RTX 4090", "vram_mb": 24576}],
    })
    assert peer_res.status_code == 201
    peer_id = peer_res.json()["id"]

    # 2. Submit job
    job_res = await test_client.post("/api/v1/jobs", json={
        "owner_id": str(seeded_user.id),
        "docker_image": "ubuntu:latest",
        "command": "python train.py",
    })
    assert job_res.status_code == 201
    job_id = job_res.json()["id"]
    assert job_res.json()["status"] == "pending"

    # 3. Assign job to peer
    assign_res = await test_client.post(f"/api/v1/jobs/{job_id}/assign", json={
        "peer_id": peer_id,
    })
    assert assign_res.status_code == 200
    assert assign_res.json()["status"] == "assigned"
    assert assign_res.json()["assigned_peer_id"] == peer_id

    # Verify peer is now busy
    peer_check = await test_client.get(f"/api/v1/peers/{peer_id}")
    assert peer_check.json()["status"] == "busy"

    # 4. Worker transitions job to running
    running_res = await test_client.patch(f"/api/v1/jobs/{job_id}/status", json={
        "status": "running",
    })
    assert running_res.status_code == 200
    assert running_res.json()["status"] == "running"

    # 5. Worker completes job
    completed_res = await test_client.patch(f"/api/v1/jobs/{job_id}/status", json={
        "status": "completed",
    })
    assert completed_res.status_code == 200
    assert completed_res.json()["status"] == "completed"

    # Verify peer is released back to available
    peer_freed = await test_client.get(f"/api/v1/peers/{peer_id}")
    assert peer_freed.json()["status"] == "available"


async def test_schedule_pending_job(
    test_client: AsyncClient,
    seeded_user: User,
) -> None:
    """Test scheduler endpoint assigns oldest pending job to first available peer."""
    # 1. Register available peer
    peer_res = await test_client.post("/api/v1/peers", json={
        "owner_id": str(seeded_user.id),
        "hostname": "worker-rig-scheduler",
        "initial_status": "available",
        "gpu_capabilities": [{"gpu_name": "NVIDIA RTX 4080", "vram_mb": 16384}],
    })
    assert peer_res.status_code == 201
    peer_id = peer_res.json()["id"]

    # 2. Submit pending job
    job_res = await test_client.post("/api/v1/jobs", json={
        "owner_id": str(seeded_user.id),
        "docker_image": "pytorch/pytorch:latest",
        "command": "python benchmark.py",
    })
    assert job_res.status_code == 201
    job_id = job_res.json()["id"]

    # 3. Trigger scheduler dispatch
    sched_res = await test_client.post("/api/v1/jobs/schedule")
    assert sched_res.status_code == 200
    scheduled_job = sched_res.json()
    assert scheduled_job is not None
    assert scheduled_job["status"] == "assigned"
    assert scheduled_job["assigned_peer_id"] == peer_id
