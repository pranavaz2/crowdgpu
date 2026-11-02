"""
Worker job execution module.

Implements coordinator registration, assigned job polling, lifecycle status
reporting, and command execution (simulated development mode vs production GPU).
"""

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from worker.config import settings
from worker.docker import execute_docker_job

logger = logging.getLogger(__name__)


class WorkerExecutor:
    """Handles communication with coordinator and job execution lifecycle."""

    def __init__(
        self,
        coordinator_url: str | None = None,
        peer_id: str | None = None,
        mode: str | None = None,
        execution_mode: str | None = None,
        execution_timeout: float | None = None,
    ) -> None:
        self.coordinator_url = (coordinator_url or settings.worker_coordinator_url).rstrip("/")
        self.peer_id = peer_id
        # Preserve self.mode for backwards compatibility
        self.mode = mode or settings.worker_mode

        # Explicit execution mode: "docker" or "simulation"
        if execution_mode:
            self.execution_mode = execution_mode.lower()
        elif mode and mode.lower() in ("docker", "simulation", "development"):
            if mode.lower() == "development":
                self.execution_mode = "simulation"
            else:
                self.execution_mode = mode.lower()
        else:
            self.execution_mode = settings.worker_execution_mode.lower()

        self.execution_timeout = (
            execution_timeout
            if execution_timeout is not None
            else settings.worker_execution_timeout
        )

    def _http_request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        url = f"{self.coordinator_url}{path}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                resp_body = resp.read().decode("utf-8")
                return json.loads(resp_body) if resp_body else {}
        except urllib.error.HTTPError as exc:
            err_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Coordinator API error ({exc.code}): {err_text}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to connect to Coordinator at {url}: {exc.reason}") from exc

    def register(
        self,
        owner_id: str,
        hostname: str | None = None,
        gpu_name: str = "NVIDIA GeForce RTX 4090",
        vram_mb: int = 24576,
    ) -> str:
        """Register worker as a peer with the coordinator."""
        host = hostname or settings.worker_id
        payload = {
            "owner_id": owner_id,
            "hostname": host,
            "initial_status": "available",
            "gpu_capabilities": [
                {
                    "gpu_name": gpu_name,
                    "vram_mb": vram_mb,
                    "driver_version": "550.54.14",
                    "cuda_version": "12.4",
                    "compute_capability": "8.9",
                }
            ],
        }
        res = self._http_request("POST", "/api/v1/peers", payload)
        if isinstance(res, dict) and "id" in res:
            self.peer_id = str(res["id"])
            logger.info("Worker registered with coordinator. Peer ID: %s", self.peer_id)
            return self.peer_id
        raise RuntimeError(f"Unexpected registration response from coordinator: {res}")

    def fetch_assigned_jobs(self) -> list[dict[str, Any]]:
        """Fetch jobs assigned to this worker."""
        if not self.peer_id:
            raise RuntimeError(
                "Worker has no peer_id; cannot fetch assigned jobs without peer registration."
            )
        path = f"/api/v1/jobs?assigned_peer_id={self.peer_id}&status=assigned"
        jobs = self._http_request("GET", path)
        return jobs if isinstance(jobs, list) else []

    def update_job_status(self, job_id: str, status: str) -> dict[str, Any]:
        """Update job lifecycle status on coordinator."""
        path = f"/api/v1/jobs/{job_id}/status"
        res = self._http_request("PATCH", path, {"status": status})
        return res if isinstance(res, dict) else {}

    def ensure_peer_available(self) -> None:
        """Best-effort update to restore peer status to 'available' on coordinator."""
        if not self.peer_id:
            return
        try:
            self._http_request(
                "PATCH", f"/api/v1/peers/{self.peer_id}/heartbeat", {"status": "available"}
            )
            logger.info("Worker peer %s status confirmed as 'available'.", self.peer_id)
        except Exception as exc:
            logger.warning("Could not set peer %s to available: %s", self.peer_id, exc)

    def execute_job(self, job: dict[str, Any]) -> bool:
        """
        Execute an assigned job, updating lifecycle from running -> completed or failed.
        Differentiates simulated development mode from real Docker execution.
        """
        job_id = str(job["id"])
        command = job.get("command", "")
        docker_image = job.get("docker_image", "unknown")

        logger.info(
            "Starting execution for Job ID: %s (execution_mode: %s)",
            job_id,
            self.execution_mode,
        )

        # 1. Update status to running
        self.update_job_status(job_id, "running")
        logger.info("Job %s status updated to 'running'", job_id)

        try:
            # 2. Execution phase
            if self.execution_mode in ("simulation", "development"):
                logger.info(
                    "[SIMULATED DEV EXECUTION] Explicit simulation mode selected. "
                    "No container will be spawned. Simulating image '%s' with command '%s'",
                    docker_image,
                    command,
                )
                time.sleep(0.5)
                logger.info(
                    "[SIMULATED DEV EXECUTION] Command '%s' completed successfully.", command
                )
                self.update_job_status(job_id, "completed")
                logger.info(
                    "Job %s status updated to 'completed'. Worker peer freed to 'available'.",
                    job_id,
                )
                return True

            elif self.execution_mode == "docker":
                logger.info(
                    "[DOCKER EXECUTION] Real Docker container execution initiated. "
                    "Image: '%s', Command: '%s', Timeout: %.1fs "
                    "(CPU mode / unprivileged, GPU runtime not claimed)",
                    docker_image,
                    command,
                    self.execution_timeout,
                )
                result = execute_docker_job(
                    image=docker_image,
                    command=command,
                    container_name=f"crowdgpu-job-{job_id}",
                    timeout=self.execution_timeout,
                )

                if result.is_success:
                    logger.info(
                        "[DOCKER EXECUTION] Job %s succeeded (exit code 0).\nCaptured output:\n%s",
                        job_id,
                        result.stdout.strip(),
                    )
                    self.update_job_status(job_id, "completed")
                    logger.info(
                        "Job %s status updated to 'completed'. Worker peer freed to 'available'.",
                        job_id,
                    )
                    return True
                else:
                    logger.error(
                        "[DOCKER EXECUTION] Job %s failed (exit_code=%s, timed_out=%s, error=%s).\n"
                        "Stdout:\n%s\nStderr:\n%s",
                        job_id,
                        result.exit_code,
                        result.timed_out,
                        result.error_message,
                        result.stdout.strip(),
                        result.stderr.strip(),
                    )
                    self.update_job_status(job_id, "failed")
                    logger.info(
                        "Job %s status updated to 'failed'. Worker peer freed to 'available'.",
                        job_id,
                    )
                    return False

            else:
                raise ValueError(f"Unsupported execution mode: '{self.execution_mode}'")

        except Exception as exc:
            logger.exception("Unexpected exception executing Job %s: %s", job_id, exc)
            try:
                self.update_job_status(job_id, "failed")
                logger.info("Job %s status updated to 'failed' following error.", job_id)
            except Exception as update_exc:
                logger.error(
                    "Failed to update status for Job %s to 'failed': %s", job_id, update_exc
                )
            self.ensure_peer_available()
            return False

    def process_next_assigned(self) -> bool:
        """Fetch and execute the next assigned job. Returns True if a job was processed."""
        jobs = self.fetch_assigned_jobs()
        if not jobs:
            return False
        job = jobs[0]
        return self.execute_job(job)
