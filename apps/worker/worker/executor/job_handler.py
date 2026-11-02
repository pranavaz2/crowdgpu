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
from worker.executor.docker_executor import (
    DockerCommandNotAllowedError,
    DockerExecutionError,
    DockerGPUExecutor,
    DockerImageNotAllowedError,
    DockerNotAvailableError,
    DockerResult,
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


import re

def sanitize_text(text: str | None) -> str | None:
    """Mask known sensitive patterns such as passwords or database credentials."""
    if not text or not isinstance(text, str):
        return text
    sanitized = text
    # Mask database connection passwords: postgresql://user:password@host
    sanitized = re.sub(
        r"(postgres(?:ql)?(?:\+[a-z0-9_]+)?://[^:]+:)[^@]+(@)",
        r"\1***\2",
        sanitized,
        flags=re.IGNORECASE,
    )
    # Mask key=value secrets: password=..., token=..., etc.
    sanitized = re.sub(
        r"(password|passwd|secret|token|api_key|auth)=([^\s&]+)",
        r"\1=***",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


@dataclass
class JobResult:
    """Encapsulates the outcome of a job execution."""

    job_id: str
    status: JobStatus
    execution_time_s: float
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_coordinator_payload(self) -> Dict[str, Any]:
        """Serialize to the Coordinator job-result contract with sensitive credentials redacted."""
        exit_code = 0 if self.status == JobStatus.SUCCESS else 1
        if isinstance(self.output, dict) and "exit_code" in self.output:
            try:
                exit_code = int(self.output["exit_code"])
            except (ValueError, TypeError):
                pass

        payload: Dict[str, Any] = {
            "status": self.status.value,
            "output": self.output,
            "execution_time_s": self.execution_time_s,
            "error": sanitize_text(self.error),
            "exit_code": exit_code,
        }
        if isinstance(self.output, dict) and "stdout" in self.output:
            payload["stdout_tail"] = sanitize_text(str(self.output["stdout"])[:20000])
        return payload


class InvalidJobError(ValueError):
    """Raised when a job payload fails validation."""


# ---------------------------------------------------------------------------
# Job schema validation & normalization
# ---------------------------------------------------------------------------

def normalize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize raw job dictionary from either Person 2 format or Coordinator format.
    Ensures 'job_id', 'type', and 'required_vram_mib' are populated.
    """
    if not isinstance(job, dict):
        return job

    normalized = dict(job)

    # 1. job_id
    if "job_id" not in normalized or not normalized["job_id"]:
        if "id" in normalized and normalized["id"]:
            normalized["job_id"] = str(normalized["id"])

    # 2. Extract requirements if present
    reqs = normalized.get("requirements")
    if not isinstance(reqs, dict):
        reqs = {}

    # 3. type / workload_type / command
    if "type" not in normalized or not normalized["type"]:
        workload = (
            normalized.get("workload_type")
            or reqs.get("workload_type")
            or reqs.get("type")
            or normalized.get("command")
        )
        if workload:
            normalized["type"] = str(workload).strip()

    # 4. required_vram_mib
    if "required_vram_mib" not in normalized or normalized["required_vram_mib"] is None:
        vram = (
            normalized.get("vram_required_mb")
            or reqs.get("required_vram_mb")
            or reqs.get("vram_required_mb")
            or normalized.get("required_vram_mb")
            or 0
        )
        try:
            normalized["required_vram_mib"] = int(vram)
        except (ValueError, TypeError):
            normalized["required_vram_mib"] = 0

    # 5. docker_image
    if "docker_image" not in normalized or not normalized["docker_image"]:
        docker_img = reqs.get("docker_image")
        if docker_img:
            normalized["docker_image"] = str(docker_img).strip()

    return normalized


def validate_job(job: Dict[str, Any]) -> None:
    """
    Validate the job payload.

    Required fields::

        job_id (or id)   (str)  — unique job identifier
        type (or command) (str) — workload type

    Optional fields::

        required_vram_mib (int) — VRAM the job expects to use (default 0)
        params            (dict) — workload-specific parameters

    Raises InvalidJobError on any validation failure.
    """
    if not isinstance(job, dict):
        raise InvalidJobError("Job payload must be a dict.")

    # Check for job_id or id
    job_id = job.get("job_id") if job.get("job_id") is not None else job.get("id")
    if job_id is None:
        raise InvalidJobError("Job is missing required field: 'job_id'")
    if not isinstance(job_id, (str, int)) or not str(job_id).strip():
        raise InvalidJobError("job_id must be a non-empty string.")

    # Check for type / workload_type / command
    reqs = job.get("requirements") if isinstance(job.get("requirements"), dict) else {}
    w_type = (
        job.get("type")
        if job.get("type") is not None
        else (job.get("workload_type") or reqs.get("workload_type") or reqs.get("type") or job.get("command"))
    )
    if w_type is None:
        raise InvalidJobError("Job is missing required field: 'type'")
    if not isinstance(w_type, str) or not w_type.strip():
        raise InvalidJobError("type must be a non-empty string.")

    required_vram = job.get("required_vram_mib")
    if required_vram is None:
        required_vram = job.get("vram_required_mb") or reqs.get("required_vram_mb") or reqs.get("vram_required_mb", 0)
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
        docker_executor: Optional[DockerGPUExecutor] = None,
    ) -> None:
        self._config = config
        self._sm = state_machine
        self._detector = detector
        self._coordinator = coordinator
        self._executor = executor or CUDAExecutor(gpu_id=config.gpu_id)
        self._docker_executor = docker_executor

    def handle(self, job: Dict[str, Any]) -> JobResult:
        """
        Execute a job through the full lifecycle.

        Steps:
          1. Normalize & validate job schema
          2. Check GPU VRAM
          3. Notify Coordinator -> RUNNING
          4. Transition -> BUSY
          5. Execute CUDA or Docker workload
          6. Transition -> AVAILABLE (or ERROR)
          7. Report result to Coordinator

        Returns JobResult regardless of success/failure.
        """
        start = time.perf_counter()
        normalized = normalize_job(job) if isinstance(job, dict) else job
        job_id = normalized.get("job_id", "unknown") if isinstance(normalized, dict) else "unknown"

        # Step 1 — Validate
        try:
            validate_job(normalized)
        except InvalidJobError as exc:
            logger.warning("Job %s rejected (validation): %s", job_id, exc)
            return self._make_and_report_result(
                job_id=job_id,
                status=JobStatus.REJECTED,
                error=str(exc),
                start=start,
            )

        # Step 2 — VRAM check
        required_vram = int(normalized.get("required_vram_mib", 0))
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

        # Step 4 — Mark RUNNING with Coordinator
        try:
            self._coordinator.update_job_status(job_id=job_id, status="RUNNING")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to update status to RUNNING for job %s: %s", job_id, exc)

        # Step 5 — Execute workload (Docker or CUDA)
        cuda_result = None
        docker_result = None
        exec_error: Optional[str] = None
        workload_type = normalized.get("type", "")
        has_docker_image = bool(normalized.get("docker_image"))

        try:
            if has_docker_image or workload_type == "docker":
                executor = self._docker_executor or DockerGPUExecutor(gpu_id=self._config.gpu_id)
                docker_result = executor.execute(normalized)
                if not docker_result.success:
                    exec_error = docker_result.error or f"Docker container exited with code {docker_result.exit_code}"
            else:
                params = dict(normalized)
                params.setdefault("type", workload_type)
                cuda_result = self._executor.execute(params)
                if not cuda_result.success:
                    exec_error = cuda_result.error

        except (UnsupportedWorkloadError, InsufficientVRAMError) as exc:
            exec_error = str(exc)
            logger.warning("Job %s workload error: %s", job_id, exc)
        except (DockerNotAvailableError, DockerImageNotAllowedError, DockerCommandNotAllowedError) as exc:
            exec_error = str(exc)
            logger.warning("Job %s Docker error: %s", job_id, exc)
        except CUDAExecutionError as exc:
            exec_error = str(exc)
            logger.error("Job %s CUDA error: %s", job_id, exc)
        except Exception as exc:  # noqa: BLE001
            exec_error = f"Unexpected error: {type(exc).__name__}: {exc}"
            logger.exception("Job %s unexpected failure", job_id)

        # Step 6 — Transition back
        if exec_error:
            try:
                self._sm.transition(WorkerState.ERROR)
            except InvalidStateTransitionError:
                pass  # already in bad state, best-effort
        else:
            try:
                self._sm.transition(WorkerState.AVAILABLE)
            except InvalidStateTransitionError as exc:
                logger.warning("State recovery warning: %s", exc)

        # Step 7 — Build and report result
        status = JobStatus.FAILED if exec_error else JobStatus.SUCCESS
        output = {}
        if docker_result:
            output = docker_result.to_dict()
        elif cuda_result:
            output = cuda_result.to_dict()

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
