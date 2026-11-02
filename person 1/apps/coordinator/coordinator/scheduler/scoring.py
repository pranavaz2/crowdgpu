"""
Scheduler Scoring Strategy.

Provides pluggable scoring interfaces and algorithms for candidate GPU peer selection.
"""

import datetime
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from coordinator.config import settings


@dataclass
class PeerCandidate:
    """Representation of an evaluated GPU provider peer candidate."""

    peer_id: uuid.UUID
    hostname: str
    status: str
    last_seen_at: datetime.datetime | None
    max_vram_mb: int
    available_vram_mb: int
    rtt_ms: float | None = None
    compute_capability: str | None = None


class ScoringStrategy(ABC):
    """Abstract base class for peer scoring algorithms."""

    @abstractmethod
    def score(
        self,
        candidate: PeerCandidate,
        required_vram_mb: int,
        timeout_seconds: int = 30,
    ) -> float:
        """Calculate a composite suitability score in [0.0, 1.0]."""
        pass


class DefaultScoringStrategy(ScoringStrategy):
    """
    Default heuristic scoring strategy for MVP.

    Components:
    1. VRAM Tight-Fit (default weight 0.5):
       Prefers peers with GPU VRAM closest to the requested amount (reduces fragmentation).
       Formula: 1.0 - (available_vram - required_vram) / available_vram
    2. Heartbeat Freshness (default weight 0.3):
       Formula: 1.0 - (heartbeat_age / timeout_seconds)
    3. Network Latency RTT (default weight 0.2):
       Used ONLY when measured RTT is available; otherwise weights are renormalized
       between VRAM and Freshness without fabricating latency.
    """

    def __init__(
        self,
        weight_vram: float = settings.scheduler_weight_vram,
        weight_availability: float = settings.scheduler_weight_availability,
        weight_latency: float = settings.scheduler_weight_latency,
    ) -> None:
        self.w_vram = weight_vram
        self.w_avail = weight_availability
        self.w_lat = weight_latency

    def score(
        self,
        candidate: PeerCandidate,
        required_vram_mb: int,
        timeout_seconds: int = 30,
    ) -> float:
        if candidate.available_vram_mb < required_vram_mb:
            return 0.0

        # 1. VRAM tight fit: range [0.0, 1.0], 1.0 = exact fit
        vram_diff = candidate.available_vram_mb - required_vram_mb
        vram_score = max(0.0, 1.0 - (vram_diff / candidate.available_vram_mb))

        # 2. Availability freshness: range [0.0, 1.0], 1.0 = brand new heartbeat
        if candidate.last_seen_at:
            last_seen = candidate.last_seen_at
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            age = max(0.0, (now - last_seen).total_seconds())
            avail_score = max(0.0, min(1.0, 1.0 - (age / max(1.0, timeout_seconds))))
        else:
            avail_score = 0.0

        # 3. Latency score (if measured RTT is present)
        if candidate.rtt_ms is not None:
            lat_score = max(0.0, min(1.0, 1.0 - (min(candidate.rtt_ms, 500.0) / 500.0)))
            total = (
                self.w_vram * vram_score
                + self.w_avail * avail_score
                + self.w_lat * lat_score
            )
        else:
            # Renormalize without latency weight
            norm_sum = self.w_vram + self.w_avail
            if norm_sum > 0:
                total = (
                    (self.w_vram / norm_sum) * vram_score
                    + (self.w_avail / norm_sum) * avail_score
                )
            else:
                total = vram_score

        return round(total, 4)
