"""
CrowdGPU Worker Daemon — entry point.

Bootstrap phase: starts the worker in development mode and reports self-status.
No GPU hardware, WebRTC, Docker sandbox, or job execution is implemented yet.

Usage:
    python -m worker.main
"""

import logging
import sys

from worker.config import settings
from worker.status import get_status


def main() -> None:
    """Start the CrowdGPU worker daemon."""
    logging.basicConfig(
        level=settings.worker_log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    logger.info("CrowdGPU Worker Daemon starting (bootstrap phase)")
    logger.info("Worker ID: %s", settings.worker_id)
    logger.info("Mode: %s", settings.worker_mode)

    status = get_status()

    print("\n--- CrowdGPU Worker Status ---")
    status.display()
    print("------------------------------\n")

    if settings.worker_mode != "development":
        logger.error(
            "Only development mode is supported in the bootstrap phase. "
            "Set WORKER_MODE=development."
        )
        sys.exit(1)

    logger.info("Worker started successfully in development mode.")
    logger.info(
        "Production features (GPU telemetry, job execution, WebRTC) "
        "will be implemented in later phases."
    )


if __name__ == "__main__":
    main()
