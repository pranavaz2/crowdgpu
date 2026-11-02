"""
CrowdGPU Worker — main orchestrator.

Demonstrates the full MVP flow:

    Worker starts
    → detects NVIDIA GPU
    → registers with Coordinator
    → reports GPU telemetry
    → becomes AVAILABLE
    → receives a GPU job
    → checks VRAM
    → executes using CUDA
    → records result
    → reports result
    → becomes AVAILABLE again
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional

from worker.config import WorkerConfig
from worker.coordinator.client import CoordinatorClient, CoordinatorError, JobPollError
from worker.executor.cuda_executor import CUDAExecutor
from worker.executor.job_handler import JobHandler, JobResult
from worker.gpu.detector import GPUDetector, GPUDetectionError, GPUInfo
from worker.state import WorkerState, WorkerStateMachine

logger = logging.getLogger(__name__)


class Worker:
    """
    CrowdGPU Worker node orchestrator.

    Manages the full lifecycle:
      - GPU detection
      - Coordinator registration (with bounded retry)
      - Heartbeat loop
      - Job polling and execution loop
    """

    def __init__(self, config: WorkerConfig) -> None:
        self._config = config
        self._sm = WorkerStateMachine()  # starts in STARTING
        self._detector = GPUDetector(gpu_id=config.gpu_id)
        self._coordinator = CoordinatorClient(config)
        self._executor = CUDAExecutor(gpu_id=config.gpu_id)
        self._gpu_info: Optional[GPUInfo] = None
        self._job_handler: Optional[JobHandler] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def peer_id(self) -> Optional[str]:
        """Coordinator-assigned peer UUID."""
        return self._coordinator.peer_id

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the worker: detect GPU → register → begin heartbeat loop → begin job poll loop.
        Transitions STARTING → AVAILABLE on success, STARTING → ERROR on failure.
        """
        logger.info("=== CrowdGPU Worker starting (id=%s) ===", self._config.worker_id)

        # --- TASK 1: detect GPU ---
        try:
            self._detector.initialize()
            self._gpu_info = self._detector.detect()
            logger.info(
                "GPU: %s | UUID: %s | VRAM: %d MiB | Driver: %s | CUDA: %s",
                self._gpu_info.name,
                self._gpu_info.uuid,
                self._gpu_info.total_vram_mib,
                self._gpu_info.driver_version,
                self._gpu_info.cuda_available,
            )
        except (GPUDetectionError, Exception) as exc:
            logger.error("GPU detection failed: %s", exc)
            self._sm.transition(WorkerState.ERROR)
            raise

        # --- TASK 3: register with Coordinator (with bounded retry) ---
        try:
            self._register_with_retry()
        except CoordinatorError as exc:
            logger.error("Coordinator registration failed: %s", exc)
            self._sm.transition(WorkerState.ERROR)
            raise

        # Build job handler now that dependencies are ready
        self._job_handler = JobHandler(
            config=self._config,
            state_machine=self._sm,
            detector=self._detector,
            coordinator=self._coordinator,
            executor=self._executor,
        )

        # --- TASK 5: STARTING → AVAILABLE ---
        self._sm.transition(WorkerState.AVAILABLE)
        logger.info("Worker is AVAILABLE and ready for jobs (peer_id=%s).", self.peer_id)

        # --- TASK 4: start heartbeat and polling loops ---
        self._start_heartbeat_loop()
        self._start_poll_loop()

    def _register_with_retry(
        self,
        max_attempts: int = 3,
        initial_backoff: float = 0.1,
        max_backoff: float = 5.0,
    ) -> None:
        """Register worker with coordinator using bounded exponential backoff."""
        attempt = 0
        backoff = initial_backoff
        while not self._stop_event.is_set():
            attempt += 1
            try:
                self._coordinator.register(self._gpu_info)
                return
            except CoordinatorError as exc:
                if attempt >= max_attempts:
                    raise
                logger.warning(
                    "Registration attempt %d/%d failed: %s. Retrying in %.2fs...",
                    attempt,
                    max_attempts,
                    exc,
                    backoff,
                )
                self._stop_event.wait(timeout=backoff)
                backoff = min(backoff * 2.0, max_backoff)

    def stop(self) -> None:
        """Graceful shutdown: stop polling & heartbeat, deregister, transition OFFLINE, cleanup."""
        logger.info("Worker shutting down...")
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=5)
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)

        if self._sm.can_transition(WorkerState.OFFLINE):
            self._sm.transition(WorkerState.OFFLINE)

        # Best-effort deregistration with coordinator
        try:
            self._coordinator.deregister()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Deregistration notice: %s", exc)

        self._coordinator.close()
        self._detector.shutdown()
        logger.info("Worker stopped.")

    # ------------------------------------------------------------------
    # Job execution (called externally or by internal poll loop)
    # ------------------------------------------------------------------

    def execute_job(self, job: Dict[str, Any]) -> JobResult:
        """
        Accept and execute a job. Delegates to JobHandler.
        Raises RuntimeError if the worker is not AVAILABLE.
        """
        if not self._sm.is_available():
            raise RuntimeError(
                f"Worker is {self._sm.state.value}, cannot accept jobs."
            )
        if self._job_handler is None:
            raise RuntimeError("Worker has not been started. Call start() first.")
        return self._job_handler.handle(job)

    # ------------------------------------------------------------------
    # Job polling loop
    # ------------------------------------------------------------------

    def _start_poll_loop(self) -> None:
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="job-polling",
            daemon=True,
        )
        self._poll_thread.start()
        logger.info(
            "Job polling loop started (interval=%.1fs)", self._config.poll_interval
        )

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._sm.is_available():
                self._poll_and_execute_next_job()
            self._stop_event.wait(timeout=self._config.poll_interval)

    def _poll_and_execute_next_job(self) -> Optional[JobResult]:
        """Poll coordinator for the next assigned job and execute it."""
        try:
            job = self._coordinator.poll_next_job()
        except JobPollError as exc:
            logger.warning("Error polling for jobs: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error polling for jobs: %s", exc)
            return None

        if not isinstance(job, dict):
            return None  # HTTP 204 No Content (or not a job dict)

        job_id = job.get("id") or job.get("job_id", "unknown")
        logger.info("Claimed assigned job: %s", job_id)
        try:
            return self.execute_job(job)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error executing claimed job %s: %s", job_id, exc)
            return None

    # ------------------------------------------------------------------
    # Heartbeat loop (TASK 4)
    # ------------------------------------------------------------------

    def _start_heartbeat_loop(self) -> None:
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()
        logger.info(
            "Heartbeat loop started (interval=%ds)", self._config.heartbeat_interval
        )

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            self._send_heartbeat()
            self._stop_event.wait(timeout=self._config.heartbeat_interval)

    def _send_heartbeat(self) -> None:
        try:
            telem = self._detector.telemetry()
            self._coordinator.send_heartbeat(
                telemetry=telem,
                state=self._sm.state.value,
            )
            logger.debug(
                "Heartbeat sent: state=%s free=%dMiB temp=%.1f°C util=%.1f%%",
                self._sm.state.value,
                telem.free_vram_mib,
                telem.temperature_c,
                telem.gpu_utilization_pct,
            )
        except GPUDetectionError as exc:
            logger.warning("Heartbeat GPU telemetry error: %s", exc)
        except CoordinatorError as exc:
            logger.warning("Heartbeat coordinator error: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.error("Heartbeat unexpected error: %s", exc)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def main() -> None:
    _setup_logging()

    try:
        config = WorkerConfig.from_env()
    except ValueError as exc:
        print(f"[ERROR] Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    worker = Worker(config)

    # Graceful shutdown on SIGINT / SIGTERM
    def _shutdown(sig: int, _frame: object) -> None:
        logger.info("Received signal %d — shutting down.", sig)
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        worker.start()
    except (GPUDetectionError, CoordinatorError) as exc:
        logger.error("Worker failed to start: %s", exc)
        sys.exit(1)

    # Keep main thread alive (heartbeat runs in daemon thread)
    logger.info("Worker running. Send SIGINT (Ctrl+C) to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    main()
