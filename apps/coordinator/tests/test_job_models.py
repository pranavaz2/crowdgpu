"""
Unit tests for Job ORM model (aiosqlite in-memory, ADR-003 Tier 1).

Validates:
- Job table registered in Base.metadata with all expected columns.
- Job CRUD operations.
- User -> Job relationship traversal.
- Peer -> Job relationship traversal.
- Default fields (status="QUEUED", attempt_count=0).
- Requirements and result JSON persistence.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from coordinator.database.base import Base
from coordinator.database.models import GpuCapability, Job, Peer, User

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="module")
async def engine():
    """Create a fresh in-memory SQLite engine with the full schema."""
    _engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

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


def make_user(**kwargs) -> User:
    defaults = dict(id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:8]}@example.com")
    defaults.update(kwargs)
    return User(**defaults)


def make_peer(owner_id: uuid.UUID, **kwargs) -> Peer:
    defaults = dict(id=uuid.uuid4(), owner_id=owner_id, hostname="test-host", status="available")
    defaults.update(kwargs)
    return Peer(**defaults)


def make_job(owner_id: uuid.UUID, **kwargs) -> Job:
    defaults = dict(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name="Test GPU Matrix Multiplication",
        command="python matrix_mul.py",
        requirements={"required_vram_mb": 4096},
    )
    defaults.update(kwargs)
    return Job(**defaults)


class TestJobMetadata:
    def test_jobs_table_registered(self) -> None:
        """Base.metadata includes the jobs table."""
        assert "jobs" in Base.metadata.tables

    def test_jobs_table_columns(self) -> None:
        """jobs table has all expected columns."""
        cols = {c.name for c in Base.metadata.tables["jobs"].columns}
        expected = {
            "id",
            "owner_id",
            "name",
            "command",
            "requirements",
            "status",
            "assigned_peer_id",
            "attempt_count",
            "started_at",
            "completed_at",
            "result",
            "error",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)


class TestJobCRUD:
    @pytest.mark.asyncio
    async def test_create_and_fetch_job(self, session: AsyncSession) -> None:
        """A Job can be created, persisted, and fetched."""
        user = make_user()
        session.add(user)
        await session.flush()

        job = make_job(owner_id=user.id)
        session.add(job)
        await session.flush()

        fetched = await session.get(Job, job.id)
        assert fetched is not None
        assert fetched.name == "Test GPU Matrix Multiplication"
        assert fetched.command == "python matrix_mul.py"
        assert fetched.requirements == {"required_vram_mb": 4096}
        assert fetched.status == "QUEUED"
        assert fetched.attempt_count == 0
        assert fetched.assigned_peer_id is None
        assert fetched.started_at is None
        assert fetched.completed_at is None
        assert fetched.result is None
        assert fetched.error is None

    @pytest.mark.asyncio
    async def test_job_user_relationship(self, session: AsyncSession) -> None:
        """User.jobs correctly navigates to associated jobs."""
        user = make_user()
        session.add(user)
        await session.flush()

        job1 = make_job(owner_id=user.id, name="Job 1")
        job2 = make_job(owner_id=user.id, name="Job 2")
        session.add_all([job1, job2])
        await session.flush()

        await session.refresh(user, ["jobs"])
        job_names = {j.name for j in user.jobs}
        assert job_names == {"Job 1", "Job 2"}

    @pytest.mark.asyncio
    async def test_job_peer_assignment_relationship(self, session: AsyncSession) -> None:
        """Job can be assigned to a Peer and traversed bidirectionally."""
        user = make_user()
        session.add(user)
        await session.flush()

        peer = make_peer(owner_id=user.id)
        session.add(peer)
        await session.flush()

        job = make_job(owner_id=user.id, assigned_peer_id=peer.id, status="ASSIGNED")
        session.add(job)
        await session.flush()

        # Check job -> peer
        await session.refresh(job, ["assigned_peer"])
        assert job.assigned_peer is not None
        assert job.assigned_peer.id == peer.id

        # Check peer -> jobs
        await session.refresh(peer, ["jobs"])
        assert len(peer.jobs) == 1
        assert peer.jobs[0].id == job.id

    @pytest.mark.asyncio
    async def test_job_result_and_completion_storage(self, session: AsyncSession) -> None:
        """Completed job correctly stores result JSON and completed_at."""
        import datetime

        user = make_user()
        session.add(user)
        await session.flush()

        job = make_job(owner_id=user.id)
        session.add(job)
        await session.flush()

        now = datetime.datetime.now(datetime.UTC)
        job.status = "COMPLETED"
        job.completed_at = now
        job.result = {"exit_code": 0, "stdout_tail": "Computation completed in 3.4s"}
        await session.flush()

        fetched = await session.get(Job, job.id)
        assert fetched is not None
        assert fetched.status == "COMPLETED"
        assert fetched.result["exit_code"] == 0
        assert "Computation completed" in fetched.result["stdout_tail"]
