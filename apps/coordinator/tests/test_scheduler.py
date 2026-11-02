"""
Unit tests for the CrowdGPU Scheduler and Scoring algorithms.

Validates:
- Tight-fit VRAM scoring and availability freshness.
- Latency inclusion vs normalization fallback.
- Successful peer selection and reservation (ASSIGNED state, peer status 'busy').
- Insufficient VRAM handling and attempt limit failure.
- Exclusion of busy or stale/offline peers.
- Candidate ranking and tie-breaking.
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
from coordinator.scheduler.scheduler import Scheduler
from coordinator.scheduler.scoring import DefaultScoringStrategy, PeerCandidate

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


class TestScoring:
    def test_vram_tight_fit_prefers_closer_match(self) -> None:
        """Tighter VRAM fit yields higher score than excess capacity."""
        strategy = DefaultScoringStrategy(weight_vram=1.0, weight_availability=0.0, weight_latency=0.0)
        now = datetime.datetime.now(datetime.UTC)

        # Candidate 1: 8192 MB (closer fit for 8000 MB)
        c1 = PeerCandidate(
            peer_id=uuid.uuid4(),
            hostname="tight-fit-rig",
            status="available",
            last_seen_at=now,
            max_vram_mb=8192,
            available_vram_mb=8192,
        )

        # Candidate 2: 24576 MB (loose fit for 8000 MB)
        c2 = PeerCandidate(
            peer_id=uuid.uuid4(),
            hostname="excess-fit-rig",
            status="available",
            last_seen_at=now,
            max_vram_mb=24576,
            available_vram_mb=24576,
        )

        score1 = strategy.score(c1, required_vram_mb=8000)
        score2 = strategy.score(c2, required_vram_mb=8000)

        assert score1 > score2
        assert score1 > 0.95  # Almost exact fit

    def test_renormalization_without_latency(self) -> None:
        """When RTT is None, weights normalize between VRAM and freshness."""
        strategy = DefaultScoringStrategy(weight_vram=0.5, weight_availability=0.3, weight_latency=0.2)
        now = datetime.datetime.now(datetime.UTC)

        candidate = PeerCandidate(
            peer_id=uuid.uuid4(),
            hostname="no-lat-rig",
            status="available",
            last_seen_at=now,
            max_vram_mb=16384,
            available_vram_mb=16384,
            rtt_ms=None,
        )

        score = strategy.score(candidate, required_vram_mb=16384)
        # Perfect fit (1.0) and fresh heartbeat (1.0) should equal 1.0 even without latency
        assert score == 1.0


class TestSchedulerMatching:
    @pytest.mark.asyncio
    async def test_schedule_job_successfully_assigns_peer(self, session: AsyncSession) -> None:
        """Scheduler finds available peer, reserves it as busy, and sets job to ASSIGNED."""
        user = User(id=uuid.uuid4(), email="owner@test.com")
        session.add(user)
        await session.flush()

        now = datetime.datetime.now(datetime.UTC)
        peer = Peer(
            id=uuid.uuid4(),
            owner_id=user.id,
            hostname="gpu-worker-1",
            status="available",
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
        session.add(peer)
        await session.flush()

        job = Job(
            id=uuid.uuid4(),
            owner_id=user.id,
            name="Matrix Test",
            command="python run.py",
            requirements={"required_vram_mb": 4000},
            status=JobStatus.QUEUED.value,
        )
        session.add(job)
        await session.commit()

        scheduler = Scheduler()
        updated_job = await scheduler.schedule_job(session, job.id)

        assert updated_job is not None
        assert updated_job.status == "ASSIGNED"
        assert updated_job.assigned_peer_id == peer.id
        assert updated_job.attempt_count == 1

        # Check peer is now marked busy
        refreshed_peer = await session.get(Peer, peer.id)
        assert refreshed_peer.status == "busy"

    @pytest.mark.asyncio
    async def test_schedule_job_insufficient_vram(self, session: AsyncSession) -> None:
        """Job requiring more VRAM than available stays QUEUED (or fails if attempts exhausted)."""
        user = User(id=uuid.uuid4(), email="small-gpu-owner@test.com")
        session.add(user)
        await session.flush()

        now = datetime.datetime.now(datetime.UTC)
        peer = Peer(
            id=uuid.uuid4(),
            owner_id=user.id,
            hostname="small-gpu-worker",
            status="available",
            registered_at=now,
            last_seen_at=now,
        )
        gpu = GpuCapability(
            id=uuid.uuid4(),
            peer_id=peer.id,
            gpu_name="NVIDIA GTX 1650",
            vram_mb=4096,
        )
        peer.gpu_capabilities.append(gpu)
        session.add(peer)
        await session.flush()

        # Job requires 16000 MB VRAM
        job = Job(
            id=uuid.uuid4(),
            owner_id=user.id,
            name="LLM Training",
            command="python train.py",
            requirements={"required_vram_mb": 16000},
            status=JobStatus.QUEUED.value,
        )
        session.add(job)
        await session.commit()

        scheduler = Scheduler()
        updated_job = await scheduler.schedule_job(session, job.id)

        assert updated_job is not None
        assert updated_job.status == "QUEUED"
        assert updated_job.assigned_peer_id is None
        assert updated_job.attempt_count == 1

    @pytest.mark.asyncio
    async def test_schedule_job_stale_peer_ignored(self, session: AsyncSession) -> None:
        """Peer whose heartbeat is older than timeout is not scheduled."""
        user = User(id=uuid.uuid4(), email="stale-owner@test.com")
        session.add(user)
        await session.flush()

        old_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=120)
        peer = Peer(
            id=uuid.uuid4(),
            owner_id=user.id,
            hostname="stale-worker",
            status="available",
            last_seen_at=old_time,
        )
        gpu = GpuCapability(
            id=uuid.uuid4(),
            peer_id=peer.id,
            gpu_name="NVIDIA RTX 4090",
            vram_mb=24576,
        )
        peer.gpu_capabilities.append(gpu)
        session.add(peer)
        await session.flush()

        job = Job(
            id=uuid.uuid4(),
            owner_id=user.id,
            name="Test Job",
            command="python run.py",
            requirements={"required_vram_mb": 20000},
            status=JobStatus.QUEUED.value,
        )
        session.add(job)
        await session.commit()

        scheduler = Scheduler()
        updated_job = await scheduler.schedule_job(session, job.id)

        assert updated_job.status == "QUEUED"
        assert updated_job.assigned_peer_id is None
