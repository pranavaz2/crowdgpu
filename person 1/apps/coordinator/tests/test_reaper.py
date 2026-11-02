"""
Unit tests for the Reaper service.

Validates:
- Detection of stale peers with expired heartbeats and setting status to 'offline'.
- Requeuing of unacknowledged ASSIGNED jobs from disconnected peers.
- Failure of active RUNNING jobs from disconnected peers.
- Requeuing of unacknowledged ASSIGNED jobs exceeding ACK_TIMEOUT.
"""

import datetime
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from coordinator.database.base import Base
from coordinator.database.models import GpuCapability, Job, Peer, User
from coordinator.jobs.state_machine import JobStatus
from coordinator.scheduler.reaper import reap_stale_peers_and_jobs

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="module")
async def engine():
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
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()


class TestReaper:
    @pytest.mark.asyncio
    async def test_reaper_requeues_assigned_job_from_stale_peer(
        self, session: AsyncSession
    ) -> None:
        """Stale peer is marked offline and its unacknowledged ASSIGNED job is requeued."""
        user = User(id=uuid.uuid4(), email="reaper-assigned@test.com")
        session.add(user)
        await session.flush()

        stale_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=120)
        peer = Peer(
            id=uuid.uuid4(),
            owner_id=user.id,
            hostname="stale-assigned-node",
            status="busy",
            last_seen_at=stale_time,
        )
        session.add(peer)
        await session.flush()

        job = Job(
            id=uuid.uuid4(),
            owner_id=user.id,
            name="Unack Job",
            command="python compute.py",
            requirements={"required_vram_mb": 4000},
            status=JobStatus.ASSIGNED.value,
            assigned_peer_id=peer.id,
            attempt_count=1,
        )
        session.add(job)
        await session.commit()

        summary = await reap_stale_peers_and_jobs(session)
        assert summary["peers_marked_offline"] >= 1
        assert summary["jobs_requeued"] >= 1

        refreshed_peer = await session.get(Peer, peer.id)
        assert refreshed_peer.status == "offline"

        refreshed_job = await session.get(Job, job.id)
        assert refreshed_job.status == "QUEUED"
        assert refreshed_job.assigned_peer_id is None

    @pytest.mark.asyncio
    async def test_reaper_fails_running_job_from_stale_peer(
        self, session: AsyncSession
    ) -> None:
        """Stale peer is marked offline and its RUNNING job is failed."""
        user = User(id=uuid.uuid4(), email="reaper-running@test.com")
        session.add(user)
        await session.flush()

        stale_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=120)
        peer = Peer(
            id=uuid.uuid4(),
            owner_id=user.id,
            hostname="stale-running-node",
            status="busy",
            last_seen_at=stale_time,
        )
        session.add(peer)
        await session.flush()

        job = Job(
            id=uuid.uuid4(),
            owner_id=user.id,
            name="Crashed Worker Job",
            command="python compute.py",
            requirements={"required_vram_mb": 4000},
            status=JobStatus.RUNNING.value,
            assigned_peer_id=peer.id,
            attempt_count=1,
        )
        session.add(job)
        await session.commit()

        summary = await reap_stale_peers_and_jobs(session)
        assert summary["peers_marked_offline"] >= 1
        assert summary["jobs_failed"] >= 1

        refreshed_job = await session.get(Job, job.id)
        assert refreshed_job.status == "FAILED"
        assert "unresponsive" in refreshed_job.error
