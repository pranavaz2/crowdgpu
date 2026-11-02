"""
Peer service layer.

Encapsulates all peer business logic and atomic database persistence
for registration, retrieval, heartbeat updates, and deregistration.
"""

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from coordinator.database.models import GpuCapability, Peer, User
from coordinator.peers.exceptions import OwnerNotFoundError, PeerNotFoundError
from coordinator.peers.schemas import PeerHeartbeatRequest, PeerRegisterRequest, PeerStatus


class PeerService:
    """Service handling peer lifecycle and database operations."""

    @staticmethod
    async def register_peer(
        session: AsyncSession,
        data: PeerRegisterRequest,
    ) -> Peer:
        """
        Register a new peer and its associated GPU capabilities atomically.

        1. Verify that the referenced owner user exists.
        2. Create the Peer entity with server-generated ID and timestamps.
        3. Create GpuCapability entities for all specified GPU devices.
        4. Commit transaction atomically.
        """
        # Verify owner existence
        owner = await session.get(User, data.owner_id)
        if owner is None:
            raise OwnerNotFoundError(data.owner_id)

        now = datetime.datetime.now(datetime.UTC)
        peer_id = uuid.uuid4()

        peer = Peer(
            id=peer_id,
            owner_id=data.owner_id,
            hostname=data.hostname,
            status=data.initial_status.value,
            registered_at=now,
            last_seen_at=now,
        )

        for cap_data in data.gpu_capabilities:
            gpu = GpuCapability(
                id=uuid.uuid4(),
                peer_id=peer_id,
                gpu_name=cap_data.gpu_name,
                vram_mb=cap_data.vram_mb,
                driver_version=cap_data.driver_version,
                cuda_version=cap_data.cuda_version,
                compute_capability=cap_data.compute_capability,
            )
            peer.gpu_capabilities.append(gpu)

        session.add(peer)
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        # Re-fetch with capabilities eagerly loaded for return
        return await PeerService.get_peer(session, peer_id)

    @staticmethod
    async def get_peer(
        session: AsyncSession,
        peer_id: uuid.UUID,
    ) -> Peer:
        """
        Retrieve a peer by ID including its registered GPU capabilities.

        Raises PeerNotFoundError if no matching peer is found.
        """
        stmt = (
            select(Peer)
            .options(selectinload(Peer.gpu_capabilities))
            .where(Peer.id == peer_id)
        )
        result = await session.execute(stmt)
        peer = result.scalar_one_or_none()

        if peer is None:
            raise PeerNotFoundError(peer_id)

        return peer

    @staticmethod
    async def heartbeat(
        session: AsyncSession,
        peer_id: uuid.UUID,
        data: PeerHeartbeatRequest,
    ) -> Peer:
        """
        Process a peer heartbeat using server-controlled timestamps.

        Updates last_seen_at to the current server UTC time.
        Optionally updates lifecycle status if requested.
        """
        peer = await PeerService.get_peer(session, peer_id)

        now = datetime.datetime.now(datetime.UTC)
        peer.last_seen_at = now

        if data.status is not None:
            peer.status = data.status.value

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        return await PeerService.get_peer(session, peer_id)

    @staticmethod
    async def deregister_peer(
        session: AsyncSession,
        peer_id: uuid.UUID,
    ) -> Peer:
        """
        Mark a peer as offline/inactive without hard-deleting the record.

        Maintains identity continuity and historical accounting records.
        """
        peer = await PeerService.get_peer(session, peer_id)

        peer.status = PeerStatus.OFFLINE.value
        peer.last_seen_at = datetime.datetime.now(datetime.UTC)

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        return await PeerService.get_peer(session, peer_id)
