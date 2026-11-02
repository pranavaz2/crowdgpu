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

    # Check for execution / polling flags
    args = sys.argv[1:]
    if "--execute" in args or "--poll" in args:
        from worker.executor import WorkerExecutor

        peer_id = None
        if "--peer-id" in args:
            idx = args.index("--peer-id")
            if idx + 1 < len(args):
                peer_id = args[idx + 1]

        owner_id = None
        if "--owner-id" in args:
            idx = args.index("--owner-id")
            if idx + 1 < len(args):
                owner_id = args[idx + 1]

        execution_mode = None
        if "--execution-mode" in args:
            idx = args.index("--execution-mode")
            if idx + 1 < len(args):
                execution_mode = args[idx + 1]
        elif "--mode" in args:
            idx = args.index("--mode")
            if idx + 1 < len(args):
                execution_mode = args[idx + 1]

        timeout = None
        if "--timeout" in args:
            idx = args.index("--timeout")
            if idx + 1 < len(args):
                try:
                    timeout = float(args[idx + 1])
                except ValueError:
                    logger.warning("Invalid --timeout value; using default.")

        executor = WorkerExecutor(
            peer_id=peer_id,
            execution_mode=execution_mode,
            execution_timeout=timeout,
        )
        logger.info("Worker execution mode configured as: %s", executor.execution_mode)

        if not peer_id and owner_id:
            logger.info("Auto-registering worker with coordinator for owner %s...", owner_id)
            peer_id = executor.register(owner_id=owner_id)

        if not executor.peer_id:
            logger.error("No --peer-id or --owner-id provided. Cannot poll for assigned jobs.")
            sys.exit(1)

        logger.info("Checking for assigned jobs for peer %s...", executor.peer_id)
        processed = executor.process_next_assigned()
        if processed:
            logger.info("Job successfully executed and reported.")
        else:
            logger.info("No assigned jobs found for peer %s.", executor.peer_id)


if __name__ == "__main__":
    main()
