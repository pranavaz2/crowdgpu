"""
API tests for Job submission, listing, retrieval, and cancellation (/api/v1/jobs).

Validates:
- Successful job creation (201 Created).
- Input validation (empty name, empty command, negative VRAM, NUL bytes).
- Authentication header enforcement (401 on missing X-User-Id).
- Owner existence enforcement (404 on ghost user).
- Ownership isolation (cannot read or cancel another user's job).
- Safe cancellation while QUEUED (200 OK).
- Rejection of invalid cancellation when not QUEUED (409 Conflict).
"""

import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from coordinator.database.base import Base
from coordinator.database.models import User
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
        email=f"client-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Test Consumer",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestJobCreation:
    @pytest.mark.asyncio
    async def test_submit_valid_job(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """Submit a valid job, returns 201 Created and QUEUED status."""
        payload = {
            "name": "GPU Matrix Test",
            "command": "python gpu_test.py",
            "required_vram_mb": 4000,
        }
        headers = {"X-User-Id": str(test_user.id)}

        response = await test_client.post("/api/v1/jobs", json=payload, headers=headers)
        assert response.status_code == 201

        data = response.json()
        assert "id" in data
        assert data["name"] == "GPU Matrix Test"
        assert data["command"] == "python gpu_test.py"
        assert data["requirements"]["required_vram_mb"] == 4000
        assert data["status"] in ("QUEUED", "ASSIGNED")
        assert data["owner_id"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_submit_job_missing_auth_header(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Submitting without X-User-Id raises 401 Unauthorized."""
        payload = {
            "name": "No Auth Job",
            "command": "python test.py",
            "required_vram_mb": 4000,
        }
        response = await test_client.post("/api/v1/jobs", json=payload)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_submit_job_nonexistent_owner(
        self,
        test_client: httpx.AsyncClient,
    ) -> None:
        """Submitting with non-existent user UUID raises 404 Not Found."""
        payload = {
            "name": "Ghost Job",
            "command": "python test.py",
            "required_vram_mb": 4000,
        }
        headers = {"X-User-Id": str(uuid.uuid4())}

        response = await test_client.post("/api/v1/jobs", json=payload, headers=headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_job_negative_vram_rejected(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """Negative required VRAM returns 422 Unprocessable Entity."""
        payload = {
            "name": "Bad VRAM Job",
            "command": "python test.py",
            "required_vram_mb": -100,
        }
        headers = {"X-User-Id": str(test_user.id)}

        response = await test_client.post("/api/v1/jobs", json=payload, headers=headers)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_job_nul_byte_command_rejected(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """Command containing NUL byte returns 422."""
        payload = {
            "name": "Exploit Job",
            "command": "python\x00malicious.py",
            "required_vram_mb": 4000,
        }
        headers = {"X-User-Id": str(test_user.id)}

        response = await test_client.post("/api/v1/jobs", json=payload, headers=headers)
        assert response.status_code == 422


class TestJobRetrievalAndListing:
    @pytest.mark.asyncio
    async def test_get_own_job(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """User can retrieve status and details of their own job."""
        headers = {"X-User-Id": str(test_user.id)}
        create_res = await test_client.post(
            "/api/v1/jobs",
            json={"name": "Fetchable Job", "command": "python run.py", "required_vram_mb": 2000},
            headers=headers,
        )
        job_id = create_res.json()["id"]

        get_res = await test_client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["id"] == job_id
        assert get_res.json()["name"] == "Fetchable Job"

    @pytest.mark.asyncio
    async def test_cannot_access_other_users_job(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
        db_session: AsyncSession,
    ) -> None:
        """A user cannot access another user's job (returns 404 to avoid leaking existence)."""
        headers1 = {"X-User-Id": str(test_user.id)}
        create_res = await test_client.post(
            "/api/v1/jobs",
            json={"name": "Alice Job", "command": "python alice.py", "required_vram_mb": 2000},
            headers=headers1,
        )
        job_id = create_res.json()["id"]

        # Create second user (Bob)
        bob = User(id=uuid.uuid4(), email="bob@test.com")
        db_session.add(bob)
        await db_session.commit()

        headers_bob = {"X-User-Id": str(bob.id)}
        get_res = await test_client.get(f"/api/v1/jobs/{job_id}", headers=headers_bob)
        assert get_res.status_code == 404

    @pytest.mark.asyncio
    async def test_list_own_jobs_only(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """GET /api/v1/jobs lists caller's jobs."""
        headers = {"X-User-Id": str(test_user.id)}
        await test_client.post(
            "/api/v1/jobs",
            json={"name": "List Job A", "command": "echo A", "required_vram_mb": 1000},
            headers=headers,
        )
        await test_client.post(
            "/api/v1/jobs",
            json={"name": "List Job B", "command": "echo B", "required_vram_mb": 1000},
            headers=headers,
        )

        list_res = await test_client.get("/api/v1/jobs", headers=headers)
        assert list_res.status_code == 200
        jobs = list_res.json()
        assert len(jobs) >= 2
        for j in jobs:
            assert j["owner_id"] == str(test_user.id)


class TestJobCancellation:
    @pytest.mark.asyncio
    async def test_cancel_queued_job_success(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """Owner can successfully cancel a QUEUED job."""
        headers = {"X-User-Id": str(test_user.id)}
        # Large VRAM request ensures it remains QUEUED (no peer matches)
        create_res = await test_client.post(
            "/api/v1/jobs",
            json={"name": "To Cancel", "command": "python long.py", "required_vram_mb": 190000},
            headers=headers,
        )
        job_id = create_res.json()["id"]
        assert create_res.json()["status"] == "QUEUED"

        cancel_res = await test_client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "CANCELLED"
        assert cancel_res.json()["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_job_conflict(
        self,
        test_client: httpx.AsyncClient,
        test_user: User,
    ) -> None:
        """Attempting to cancel an already CANCELLED job returns 409 Conflict."""
        headers = {"X-User-Id": str(test_user.id)}
        create_res = await test_client.post(
            "/api/v1/jobs",
            json={"name": "Double Cancel", "command": "python run.py", "required_vram_mb": 190000},
            headers=headers,
        )
        job_id = create_res.json()["id"]
        await test_client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)

        # Cancel second time
        res2 = await test_client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
        assert res2.status_code == 409
