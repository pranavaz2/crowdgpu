"""
Worker self-status reporter.

In development mode, returns mock status without requiring GPU hardware.
In production mode (future), this will query PyNVML for real GPU information.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from worker.config import settings


@dataclass
class WorkerStatus:
    """Current worker self-status snapshot."""

    worker_id: str
    mode: str
    coordinator_url: str
    timestamp: str
    gpu_available: bool
    message: str
    details: dict = field(default_factory=dict)

    def display(self) -> None:
        """Print status to stdout."""
        print(f"  Worker ID        : {self.worker_id}")
        print(f"  Mode             : {self.mode}")
        print(f"  Coordinator URL  : {self.coordinator_url}")
        print(f"  GPU Available    : {self.gpu_available}")
        print(f"  Status           : {self.message}")
        print(f"  Timestamp        : {self.timestamp}")


def get_status() -> WorkerStatus:
    """
    Collect worker self-status.

    In development mode, GPU fields are mocked.
    GPU-specific queries (PyNVML) are not invoked at this stage.
    """
    if settings.worker_mode == "development":
        return WorkerStatus(
            worker_id=settings.worker_id,
            mode="development",
            coordinator_url=settings.worker_coordinator_url,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gpu_available=False,
            message="Running in development mode (no GPU hardware required)",
            details={"note": "GPU telemetry will be available in production mode"},
        )

    # Production path — not implemented in bootstrap.
    raise NotImplementedError(
        "Production GPU status not implemented in this phase. "
        "Set WORKER_MODE=development for local development."
    )
