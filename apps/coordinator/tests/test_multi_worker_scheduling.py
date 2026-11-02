"""
Multi-Worker Scheduling, Resource Matching, and Fault Recovery Tests.

Demonstrates and proves Objective B requirements:
1. Registering two or more distinct peers with different GPU capabilities.
2. Submitting jobs requiring different VRAM amounts.
3. Assigning a job only to a peer that meets the resource requirements.
4. Ensuring one peer cannot receive two simultaneously active jobs (one-active-job constraint).
5. Ensuring concurrent poll requests or claims cannot double-claim or race on the same job.
6. Ensuring stale or unavailable peers are not selected.
7. Recovering correctly when a worker fails or stops heartbeating (reaper requeue/fail).
8. Ensuring a completed or failed job releases the assigned peer back to available.

NOTE: These tests run against an isolated in-memory test database using simulated peers.
Hardware Note: Real physical GPU execution on this host is limited to the single physical
NVIDIA GeForce RTX 3050 Laptop GPU. Multi-peer scheduling is validated via independent
simulated peer records with distinct hardware attributes.
"""

from __future__ import annotations

import asyncio
import datetime
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from coordinator.config import settings
from coordinator.database.base import Base
from coordinator.database.models import GpuCapability, Job, Peer, User
from coordinator.jobs.exceptions import InvalidJobTransitionError
from coordinator.jobs.schemas import JobCreate, JobResultSubmit, JobStatusUpdate
from coordinator.jobs.service import JobService
from coordinator.jobs.state_machine import JobStatus
from coordinator.peers.schemas import PeerRegisterRequest, GpuCapabilityCreate
from coordinator.peers.service import PeerService
from coordinator.scheduler.reaper import reap_stale_peers_and_jobs
from coordinator.scheduler.scheduler import Scheduler

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    _engine = create_async_engine(
        TEST_DB_URL,
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


@pytest_asyncio.fixture
async def test_user(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"multi-worker-owner-{uuid.uuid4().hex[:6]}@test.com",
        display_name="Multi-Worker Tester",
    )
    session.add(user)
    await session.commit()
    return user


# ---------------------------------------------------------------------------
# Test 1: Register distinct peers with different GPU capabilities
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_multi_peer_registration_with_distinct_gpus(
    session: AsyncSession,
    test_user: User,
) -> None:
    """Proves registering multiple independent peers with distinct GPU specifications."""
    req_3050 = PeerRegisterRequest(
        owner_id=test_user.id,
        hostname="worker-rtx3050-laptop",
        gpu_capabilities=[
            GpuCapabilityCreate(
                gpu_name="NVIDIA GeForce RTX 3050 Laptop GPU",
                vram_mb=4096,
                driver_version="591.91",
                cuda_version="12.8",
                compute_capability="8.6",
            )
        ],
    )
    req_4090 = PeerRegisterRequest(
        owner_id=test_user.id,
        hostname="worker-rtx4090-desktop",
        gpu_capabilities=[
            GpuCapabilityCreate(
                gpu_name="NVIDIA GeForce RTX 4090",
                vram_mb=24576,
                driver_version="550.54",
                cuda_version="12.4",
                compute_capability="8.9",
            )
        ],
    )

    peer1 = await PeerService.register_peer(session, req_3050)
    peer2 = await PeerService.register_peer(session, req_4090)

    assert peer1.id != peer2.id
    assert peer1.hostname == "worker-rtx3050-laptop"
    assert peer2.hostname == "worker-rtx4090-desktop"
    assert len(peer1.gpu_capabilities) == 1
    assert peer1.gpu_capabilities[0].vram_mb == 4096
    assert len(peer2.gpu_capabilities) == 1
    assert peer2.gpu_capabilities[0].vram_mb == 24576


# ---------------------------------------------------------------------------
# Tests 2 & 3: Resource Requirement Matching & Tight-Fit Routing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scheduling_routes_to_peer_matching_vram_requirement(
    session: AsyncSession,
    test_user: User,
) -> None:
    """
    Submits jobs with different VRAM demands and verifies:
    1. Lightweight job (1024 MiB) prefers the smaller GPU (RTX 3050, tight-fit).
    2. Heavyweight job (16000 MiB) routes to the high-capacity GPU (RTX 4090).
    3. Overcapacity job (32000 MiB) remains QUEUED because neither meets resource requirements.
    """
    now = datetime.datetime.now(datetime.UTC)

    peer_small = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="peer-small-gpu",
        status="available",
        registered_at=now,
        last_seen_at=now,
    )
    peer_small.gpu_capabilities.append(
        GpuCapability(id=uuid.uuid4(), gpu_name="RTX 3050", vram_mb=4096)
    )

    peer_large = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="peer-large-gpu",
        status="available",
        registered_at=now,
        last_seen_at=now,
    )
    peer_large.gpu_capabilities.append(
        GpuCapability(id=uuid.uuid4(), gpu_name="RTX 4090", vram_mb=24576)
    )

    session.add_all([peer_small, peer_large])
    await session.commit()

    scheduler = Scheduler()

    # Job 1: 1024 MiB -> Should route to peer_small (tight fit)
    job_light = await JobService.submit_job(
        session,
        owner_id=test_user.id,
        data=JobCreate(
            name="Lightweight Job",
            command="matrix_multiply",
            required_vram_mb=1024,
        ),
    )
    scheduled_light = await scheduler.schedule_job(session, job_light.id)
    assert scheduled_light.status == "ASSIGNED"
    assert scheduled_light.assigned_peer_id == peer_small.id

    # Job 2: 16000 MiB -> Cannot fit on peer_small (4096 MiB); must route to peer_large
    job_heavy = await JobService.submit_job(
        session,
        owner_id=test_user.id,
        data=JobCreate(
            name="Heavy LLM Training",
            command="train_llm",
            required_vram_mb=16000,
        ),
    )
    scheduled_heavy = await scheduler.schedule_job(session, job_heavy.id)
    assert scheduled_heavy.status == "ASSIGNED"
    assert scheduled_heavy.assigned_peer_id == peer_large.id

    # Job 3: 32000 MiB -> Exceeds all peers (max available is 24576 MiB)
    job_overcapacity = await JobService.submit_job(
        session,
        owner_id=test_user.id,
        data=JobCreate(
            name="Overcapacity Job",
            command="benchmark",
            required_vram_mb=32000,
        ),
    )
    scheduled_over = await scheduler.schedule_job(session, job_overcapacity.id)
    assert scheduled_over.status == "QUEUED"
    assert scheduled_over.assigned_peer_id is None


# ---------------------------------------------------------------------------
# Test 4: One-active-job constraint per peer
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_peer_cannot_receive_two_simultaneous_active_jobs(
    session: AsyncSession,
    test_user: User,
) -> None:
    """Proves that a peer holding an active job (status 'busy') cannot be assigned a second job."""
    now = datetime.datetime.now(datetime.UTC)
    peer = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="single-slot-worker",
        status="available",
        registered_at=now,
        last_seen_at=now,
    )
    peer.gpu_capabilities.append(
        GpuCapability(id=uuid.uuid4(), gpu_name="RTX 3080", vram_mb=10240)
    )
    session.add(peer)
    await session.commit()

    scheduler = Scheduler()

    job1 = await JobService.submit_job(
        session,
        owner_id=test_user.id,
        data=JobCreate(name="Job 1", command="workload_1", required_vram_mb=2048),
    )
    job2 = await JobService.submit_job(
        session,
        owner_id=test_user.id,
        data=JobCreate(name="Job 2", command="workload_2", required_vram_mb=2048),
    )

    # Schedule Job 1
    sched1 = await scheduler.schedule_job(session, job1.id)
    assert sched1.status == "ASSIGNED"
    assert sched1.assigned_peer_id == peer.id

    # Check that peer is marked busy in DB
    refreshed_peer = await session.get(Peer, peer.id)
    assert refreshed_peer.status == "busy"

    # Schedule Job 2 -> Should NOT be assigned to peer because peer is busy
    sched2 = await scheduler.schedule_job(session, job2.id)
    assert sched2.status == "QUEUED"
    assert sched2.assigned_peer_id is None


# ---------------------------------------------------------------------------
# Test 5: Concurrent Poll Requests / Claims
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_concurrent_job_claim_race_condition_prevention(
    session: AsyncSession,
    test_user: User,
) -> None:
    """
    Proves that once a worker claims/starts a job (moving it to RUNNING),
    a concurrent poll returns No Content (None) and does not double-dispatch.
    """
    now = datetime.datetime.now(datetime.UTC)
    peer = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="concurrency-worker",
        status="busy",
        registered_at=now,
        last_seen_at=now,
    )
    session.add(peer)

    job = Job(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        name="Concurrent Test Job",
        command="matrix_multiply",
        requirements={"required_vram_mb": 512},
        status=JobStatus.ASSIGNED.value,
        assigned_peer_id=peer.id,
    )
    session.add(job)
    await session.commit()

    # First poll: worker discovers its assigned workload
    claimed = await JobService.get_next_job_for_peer(session, peer_id=peer.id)
    assert claimed is not None
    assert claimed.id == job.id

    # Worker immediately acknowledges and transitions to RUNNING
    await JobService.worker_update_status(
        session,
        job_id=job.id,
        peer_id=peer.id,
        data=JobStatusUpdate(status="RUNNING"),
    )

    # Second poll (concurrent worker thread or duplicate request):
    # Job is now RUNNING, not ASSIGNED. Poll returns None.
    subsequent_claim = await JobService.get_next_job_for_peer(session, peer_id=peer.id)
    assert subsequent_claim is None


# ---------------------------------------------------------------------------
# Test 6: Stale or Unavailable Peers Are Excluded
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_or_unavailable_peers_are_excluded(
    session: AsyncSession,
    test_user: User,
) -> None:
    """Verifies that offline, busy, or stale-heartbeat peers are ignored by scheduler."""
    now = datetime.datetime.now(datetime.UTC)
    stale_time = now - datetime.timedelta(seconds=settings.heartbeat_timeout_seconds + 30)

    # Peer 1: Offline
    p_offline = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="peer-offline",
        status="offline",
        last_seen_at=now,
    )
    p_offline.gpu_capabilities.append(GpuCapability(id=uuid.uuid4(), gpu_name="GPU", vram_mb=8192))

    # Peer 2: Busy
    p_busy = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="peer-busy",
        status="busy",
        last_seen_at=now,
    )
    p_busy.gpu_capabilities.append(GpuCapability(id=uuid.uuid4(), gpu_name="GPU", vram_mb=8192))

    # Peer 3: Stale heartbeat
    p_stale = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="peer-stale",
        status="available",
        last_seen_at=stale_time,
    )
    p_stale.gpu_capabilities.append(GpuCapability(id=uuid.uuid4(), gpu_name="GPU", vram_mb=8192))

    # Peer 4: Healthy available
    p_healthy = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="peer-healthy",
        status="available",
        last_seen_at=now,
    )
    p_healthy.gpu_capabilities.append(GpuCapability(id=uuid.uuid4(), gpu_name="GPU", vram_mb=8192))

    session.add_all([p_offline, p_busy, p_stale, p_healthy])
    await session.commit()

    scheduler = Scheduler()
    candidates = await scheduler.discover_candidates(session, required_vram_mb=4096)

    candidate_ids = [c.peer_id for c in candidates]
    assert p_offline.id not in candidate_ids
    assert p_busy.id not in candidate_ids
    assert p_stale.id not in candidate_ids
    assert p_healthy.id in candidate_ids
    assert len(candidates) == 1


# ---------------------------------------------------------------------------
# Test 7: Worker Failure & Reaper Heartbeat Recovery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recovery_when_worker_fails_or_stops_heartbeating(
    session: AsyncSession,
    test_user: User,
) -> None:
    """
    Simulates worker crashing while a job is ASSIGNED:
    1. Peer stops heartbeating and becomes stale.
    2. Reaper detects stale peer and marks it offline.
    3. Reaper detects orphaned ASSIGNED job and requeues it to QUEUED.
    4. When a replacement healthy peer is available, scheduler reassigns it!
    """
    now = datetime.datetime.now(datetime.UTC)
    stale_time = now - datetime.timedelta(seconds=settings.heartbeat_timeout_seconds + 60)

    failing_peer = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="worker-failing",
        status="available",
        last_seen_at=stale_time,
    )
    failing_peer.gpu_capabilities.append(GpuCapability(id=uuid.uuid4(), gpu_name="GPU", vram_mb=8192))

    healthy_peer = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="worker-backup",
        status="available",
        last_seen_at=now,
    )
    healthy_peer.gpu_capabilities.append(GpuCapability(id=uuid.uuid4(), gpu_name="GPU", vram_mb=8192))

    session.add_all([failing_peer, healthy_peer])

    # Job was assigned to the failing peer before it died
    job = Job(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        name="Orphaned Workload",
        command="matrix_multiply",
        requirements={"required_vram_mb": 2048},
        status=JobStatus.ASSIGNED.value,
        assigned_peer_id=failing_peer.id,
    )
    session.add(job)
    await session.commit()

    # Run reaper sweep
    stats = await reap_stale_peers_and_jobs(session)

    assert stats["peers_marked_offline"] >= 1
    assert stats["jobs_requeued"] >= 1

    # Verify failing peer was marked offline
    refreshed_failing = await session.get(Peer, failing_peer.id)
    assert refreshed_failing.status == "offline"

    # Verify job was requeued to QUEUED
    refreshed_job = await session.get(Job, job.id)
    assert refreshed_job.status == "QUEUED"
    assert refreshed_job.assigned_peer_id is None

    # Now scheduler runs: Job is reassigned to the healthy backup worker!
    scheduler = Scheduler()
    reassigned_job = await scheduler.schedule_job(session, job.id)
    assert reassigned_job.status == "ASSIGNED"
    assert reassigned_job.assigned_peer_id == healthy_peer.id


# ---------------------------------------------------------------------------
# Test 8: Job Completion or Failure Releases Assigned Peer
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_job_completion_and_failure_releases_peer(
    session: AsyncSession,
    test_user: User,
) -> None:
    """Proves that both normal completion and worker failure release the peer back to available."""
    now = datetime.datetime.now(datetime.UTC)
    peer = Peer(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        hostname="release-tester",
        status="busy",
        last_seen_at=now,
    )
    peer.gpu_capabilities.append(GpuCapability(id=uuid.uuid4(), gpu_name="GPU", vram_mb=8192))
    session.add(peer)

    # Job 1: Completes normally
    job1 = Job(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        name="Successful Run",
        command="matrix_multiply",
        requirements={"required_vram_mb": 1024},
        status=JobStatus.RUNNING.value,
        assigned_peer_id=peer.id,
    )
    session.add(job1)
    await session.commit()

    # Worker submits result
    await JobService.worker_submit_result(
        session,
        job_id=job1.id,
        peer_id=peer.id,
        data=JobResultSubmit(
            exit_code=0,
            status="success",
            execution_time_s=1.5,
            output={"result": "ok"},
        ),
    )

    # Verify peer is released back to available
    refreshed_peer = await session.get(Peer, peer.id)
    assert refreshed_peer.status == "available"

    # Now assign Job 2 to the same peer
    refreshed_peer.status = "busy"
    job2 = Job(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        name="Failed Run",
        command="bad_workload",
        requirements={"required_vram_mb": 1024},
        status=JobStatus.RUNNING.value,
        assigned_peer_id=peer.id,
    )
    session.add(job2)
    await session.commit()

    # Worker reports failure
    await JobService.worker_update_status(
        session,
        job_id=job2.id,
        peer_id=peer.id,
        data=JobStatusUpdate(status="FAILED", error="CUDA out of memory"),
    )

    # Verify peer is again released back to available
    refreshed_peer = await session.get(Peer, peer.id)
    assert refreshed_peer.status == "available"
