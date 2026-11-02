"""
TASK 8 — Worker job handler.
TASK 9 — Result reporting.

JobHandler:
  1. Receives a raw job dict from the Coordinator
  2. Validates it (schema check, required fields)
  3. Checks GPU resources (VRAM)
  4. Transitions worker state → BUSY
  5. Executes the CUDA workload via CUDAExecutor
  6. Captures execution time + result
  7. Reports result to Coordinator via CoordinatorClient
  8. Transitions worker state → AVAILABLE (or ERROR on failure)

TASK 10 — Docker GPU execution stub is included at the bottom.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from worker.config import WorkerConfig
from worker.coordinator.client import CoordinatorClient, JobResultError
from worker.executor.cuda_executor import (
    CUDAExecutor,
    CUDAExecutionError,
    InsufficientVRAMError,
    UnsupportedWorkloadError,
    check_vram,
)
from worker.gpu.detector import GPUDetector, GPUDetectionError
from worker.state import InvalidStateTransitionError, WorkerState, WorkerStateMachine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job data structures
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass
class JobResult:
    """Encapsulates the outcome of a job execution."""

    job_id: str
    status: JobStatus
    execution_time_s: float
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_coordinator_payload(self) -> Dict[str, Any]:
        """Serialize to the Coordinator job-result contract."""
        return {
            "status": self.status.value,
            "output": self.output,
            "execution_time_s": self.execution_time_s,
            "error": self.error,
        }


class InvalidJobError(ValueError):
    """Raised when a job payload fails validation."""


# ---------------------------------------------------------------------------
# Job schema validation
# ---------------------------------------------------------------------------

_REQUIRED_JOB_FIELDS = {"job_id", "type"}


def validate_job(job: Dict[str, Any]) -> None:
    """
    Validate the job payload.

    Required fields::

        job_id  (str)  — unique job identifier
        type    (str)  — workload type (must be in CUDAExecutor allowlist)

    Optional fields::

        required_vram_mib (int)  — VRAM the job expects to use (default 0)
        params            (dict) — workload-specific parameters

    Raises InvalidJobError on any validation failure.
    """
    if not isinstance(job, dict):
        raise InvalidJobError("Job payload must be a dict.")

    missing = _REQUIRED_JOB_FIELDS - job.keys()
    if missing:
        raise InvalidJobError(f"Job is missing required fields: {missing}")

    if not isinstance(job.get("job_id"), str) or not job["job_id"].strip():
        raise InvalidJobError("job_id must be a non-empty string.")

    if not isinstance(job.get("type"), str) or not job["type"].strip():
        raise InvalidJobError("type must be a non-empty string.")

    required_vram = job.get("required_vram_mib", 0)
    if not isinstance(required_vram, (int, float)) or required_vram < 0:
        raise InvalidJobError("required_vram_mib must be a non-negative number.")


# ---------------------------------------------------------------------------
# TASK 8 + 9 — Job handler
# ---------------------------------------------------------------------------

class JobHandler:
    """
    Orchestrates the full job lifecycle.

    Usage::

        handler = JobHandler(config, state_machine, detector, coordinator)
        result = handler.handle(job_dict)
    """

    def __init__(
        self,
        config: WorkerConfig,
        state_machine: WorkerStateMachine,
        detector: GPUDetector,
        coordinator: CoordinatorClient,
        executor: Optional[CUDAExecutor] = None,
    ) -> None:
        self._config = config
        self._sm = state_machine
        self._detector = detector
        self._coordinator = coordinator
        self._executor = executor or CUDAExecutor(gpu_id=config.gpu_id)

    def handle(self, job: Dict[str, Any]) -> JobResult:
        """
        Execute a job through the full lifecycle.

        Steps:
          1. Validate job schema
          2. Check GPU VRAM
          3. Transition → BUSY
          4. Execute CUDA workload
          5. Transition → AVAILABLE (or ERROR)
          6. Report result to Coordinator

        Returns JobResult regardless of success/failure.
        """
        start = time.perf_counter()
        job_id = job.get("job_id", "unknown")

        # Step 1 — Validate
        try:
            validate_job(job)
        except InvalidJobError as exc:
            logger.warning("Job %s rejected (validation): %s", job_id, exc)
            return self._make_and_report_result(
                job_id=job_id,
                status=JobStatus.REJECTED,
                error=str(exc),
                start=start,
            )

        # Step 2 — VRAM check
        required_vram = int(job.get("required_vram_mib", 0))
        try:
            telem = self._detector.telemetry()
            check_vram(
                free_vram_mib=telem.free_vram_mib,
                required_vram_mib=required_vram,
                safety_margin_mib=self._config.vram_safety_margin_mib,
            )
        except (InsufficientVRAMError, GPUDetectionError) as exc:
            logger.warning("Job %s rejected (VRAM): %s", job_id, exc)
            return self._make_and_report_result(
                job_id=job_id,
                status=JobStatus.REJECTED,
                error=str(exc),
                start=start,
            )

        # Step 3 — Transition AVAILABLE → BUSY
        try:
            self._sm.transition(WorkerState.BUSY)
        except InvalidStateTransitionError as exc:
            logger.error("Cannot accept job %s — state error: %s", job_id, exc)
            return self._make_and_report_result(
                job_id=job_id,
                status=JobStatus.REJECTED,
                error=f"Worker not AVAILABLE: {exc}",
                start=start,
            )

        # Step 4 — Execute CUDA workload
        cuda_result = None
        exec_error: Optional[str] = None
        try:
            params = dict(job)
            params.setdefault("type", job["type"])
            cuda_result = self._executor.execute(params)
            if not cuda_result.success:
                exec_error = cuda_result.error

        except (UnsupportedWorkloadError, InsufficientVRAMError) as exc:
            exec_error = str(exc)
            logger.warning("Job %s workload error: %s", job_id, exc)
        except CUDAExecutionError as exc:
            exec_error = str(exc)
            logger.error("Job %s CUDA error: %s", job_id, exc)
        except Exception as exc:  # noqa: BLE001
            exec_error = f"Unexpected error: {type(exc).__name__}: {exc}"
            logger.exception("Job %s unexpected failure", job_id)

        # Step 5 — Transition back
        if exec_error:
            try:
                self._sm.transition(WorkerState.ERROR)
                # Attempt recovery → AVAILABLE after reporting
            except InvalidStateTransitionError:
                pass  # already in bad state, best-effort
        else:
            try:
                self._sm.transition(WorkerState.AVAILABLE)
            except InvalidStateTransitionError as exc:
                logger.warning("State recovery warning: %s", exc)

        # Step 6 — Build and report result
        status = JobStatus.FAILED if exec_error else JobStatus.SUCCESS
        output = cuda_result.to_dict() if cuda_result else {}
        result = self._make_and_report_result(
            job_id=job_id,
            status=status,
            error=exec_error,
            start=start,
            output=output,
        )

        # Recover ERROR → AVAILABLE after result is posted
        if self._sm.state == WorkerState.ERROR:
            try:
                self._sm.transition(WorkerState.AVAILABLE)
            except InvalidStateTransitionError:
                pass

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_and_report_result(
        self,
        job_id: str,
        status: JobStatus,
        start: float,
        error: Optional[str] = None,
        output: Optional[Dict[str, Any]] = None,
    ) -> JobResult:
        elapsed = time.perf_counter() - start
        result = JobResult(
            job_id=job_id,
            status=status,
            execution_time_s=round(elapsed, 6),
            output=output or {},
            error=error,
        )
        self._report_result(result)
        return result

    def _report_result(self, result: JobResult) -> None:
        """Post result to Coordinator — non-fatal if network fails."""
        try:
            self._coordinator.post_job_result(
                job_id=result.job_id,
                result=result.to_coordinator_payload(),
            )
            logger.info(
                "Result posted: job=%s status=%s time=%.3fs",
                result.job_id,
                result.status.value,
                result.execution_time_s,
            )
        except JobResultError as exc:
            # Non-fatal: log and continue so worker doesn't crash
            logger.error(
                "Failed to post result for job %s: %s", result.job_id, exc
            )
