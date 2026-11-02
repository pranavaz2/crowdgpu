"""
TASK 3 — Coordinator registration client.
TASK 4 — GPU heartbeat / telemetry sender.

Implements the Coordinator REST API contract.  All endpoints follow the
standard CrowdGPU Coordinator API schema:

  POST /api/v1/workers/register
  POST /api/v1/workers/{worker_id}/heartbeat
  POST /api/v1/workers/{worker_id}/status
  POST /api/v1/jobs/{job_id}/result

The client does NOT invent new endpoints; if the Coordinator contract
changes this file must be updated to match.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from worker.config import WorkerConfig
from worker.gpu.detector import GPUInfo, GPUTelemetry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions — all derive from CoordinatorError
# ---------------------------------------------------------------------------

class CoordinatorError(RuntimeError):
    """Base class for Coordinator communication errors."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RegistrationError(CoordinatorError):
    """Raised when worker registration fails."""


class HeartbeatError(CoordinatorError):
    """Raised when a heartbeat POST fails."""


class JobResultError(CoordinatorError):
    """Raised when posting a job result fails."""


# ---------------------------------------------------------------------------
# Coordinator API client
# ---------------------------------------------------------------------------

class CoordinatorClient:
    """
    HTTP client for the CrowdGPU Coordinator REST API.

    Usage::

        client = CoordinatorClient(config)
        client.register(gpu_info)
        client.send_heartbeat(telemetry, state="AVAILABLE")
        client.post_job_result(job_id, result_payload)
    """

    _REGISTER_PATH = "api/v1/workers/register"
    _HEARTBEAT_PATH = "api/v1/workers/{worker_id}/heartbeat"
    _STATUS_PATH = "api/v1/workers/{worker_id}/status"
    _JOB_RESULT_PATH = "api/v1/jobs/{job_id}/result"

    def __init__(self, config: WorkerConfig) -> None:
        self._config = config
        self._session: Optional[Session] = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _get_session(self) -> Session:
        if self._session is None:
            session = requests.Session()
            retry = Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[502, 503, 504],
                allowed_methods=["POST", "GET"],
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            session.headers.update(
                {
                    "Content-Type": "application/json",
                    "X-Worker-ID": self._config.worker_id,
                }
            )
            self._session = session
        return self._session

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self) -> "CoordinatorClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # TASK 3 — Registration
    # ------------------------------------------------------------------

    def register(self, gpu_info: GPUInfo) -> Dict[str, Any]:
        """
        Register this worker with the Coordinator.

        POST /api/v1/workers/register

        Request body (Coordinator contract)::

            {
              "worker_id":      str,
              "gpu_name":       str,
              "gpu_uuid":       str,
              "total_vram_mib": int,
              "driver_version": str,
              "cuda_available": bool,
              "gpu_id":         int
            }

        Returns the parsed JSON response body on success.
        Raises RegistrationError on failure.
        """
        url = self._config.api_url(self._REGISTER_PATH)
        payload: Dict[str, Any] = {
            "worker_id": self._config.worker_id,
            "gpu_name": gpu_info.name,
            "gpu_uuid": gpu_info.uuid,
            "total_vram_mib": gpu_info.total_vram_mib,
            "driver_version": gpu_info.driver_version,
            "cuda_available": gpu_info.cuda_available,
            "gpu_id": gpu_info.gpu_id,
        }
        logger.info("Registering with Coordinator: %s", url)

        for attempt in range(1, self._config.max_registration_retries + 1):
            try:
                response = self._post(url, payload)
                if response.status_code in (200, 201):
                    data = response.json()
                    logger.info("Registration successful: %s", data)
                    return data
                raise RegistrationError(
                    f"Registration rejected by Coordinator: "
                    f"HTTP {response.status_code} — {response.text[:200]}",
                    status_code=response.status_code,
                )
            except RegistrationError:
                raise
            except requests.RequestException as exc:
                wait = self._config.retry_backoff_base ** attempt
                logger.warning(
                    "Registration attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt,
                    self._config.max_registration_retries,
                    exc,
                    wait,
                )
                if attempt < self._config.max_registration_retries:
                    time.sleep(wait)
                else:
                    raise RegistrationError(
                        f"Registration failed after {attempt} attempts: {exc}"
                    ) from exc

        raise RegistrationError("Exhausted registration retries.")  # should not reach

    # ------------------------------------------------------------------
    # TASK 4 — Heartbeat / telemetry
    # ------------------------------------------------------------------

    def send_heartbeat(
        self,
        telemetry: GPUTelemetry,
        state: str,
        current_job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a heartbeat with current GPU telemetry and worker state.

        POST /api/v1/workers/{worker_id}/heartbeat

        Request body (Coordinator contract)::

            {
              "state":               str,   # AVAILABLE | BUSY | ERROR | OFFLINE
              "current_job_id":      str | null,
              "gpu_telemetry": {
                "free_vram_mib":      int,
                "used_vram_mib":      int,
                "total_vram_mib":     int,
                "gpu_utilization_pct": float,
                "temperature_c":       float,
                "cuda_available":      bool
              }
            }

        Returns the parsed JSON response (or empty dict on 204).
        Raises HeartbeatError on failure.
        """
        url = self._config.api_url(
            self._HEARTBEAT_PATH.format(worker_id=self._config.worker_id)
        )
        payload: Dict[str, Any] = {
            "state": state,
            "current_job_id": current_job_id,
            "gpu_telemetry": {
                "free_vram_mib": telemetry.free_vram_mib,
                "used_vram_mib": telemetry.used_vram_mib,
                "total_vram_mib": telemetry.total_vram_mib,
                "gpu_utilization_pct": telemetry.gpu_utilization_pct,
                "temperature_c": telemetry.temperature_c,
                "cuda_available": telemetry.cuda_available,
            },
        }
        logger.debug("Sending heartbeat (state=%s)", state)
        try:
            response = self._post(url, payload)
            if response.status_code in (200, 201, 204):
                if response.status_code == 204 or not response.content:
                    return {}
                return response.json()
            raise HeartbeatError(
                f"Heartbeat rejected: HTTP {response.status_code} — {response.text[:200]}",
                status_code=response.status_code,
            )
        except HeartbeatError:
            raise
        except requests.RequestException as exc:
            raise HeartbeatError(f"Heartbeat network error: {exc}") from exc

    def update_status(self, state: str) -> None:
        """
        Lightweight status update without full telemetry.

        POST /api/v1/workers/{worker_id}/status
        """
        url = self._config.api_url(
            self._STATUS_PATH.format(worker_id=self._config.worker_id)
        )
        payload = {"state": state}
        logger.debug("Updating worker status → %s", state)
        try:
            response = self._post(url, payload)
            if response.status_code not in (200, 201, 204):
                logger.warning(
                    "Status update returned HTTP %d: %s",
                    response.status_code,
                    response.text[:200],
                )
        except requests.RequestException as exc:
            logger.warning("Status update failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # TASK 9 — Job result reporting
    # ------------------------------------------------------------------

    def post_job_result(self, job_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post the result of a completed (or failed) job.

        POST /api/v1/jobs/{job_id}/result

        Request body (Coordinator contract)::

            {
              "worker_id":        str,
              "status":           str,   # "success" | "failed"
              "output":           any,   # job-specific output payload
              "execution_time_s": float,
              "error":            str | null
            }

        Returns the parsed JSON response.
        Raises JobResultError on failure.
        """
        url = self._config.api_url(
            self._JOB_RESULT_PATH.format(job_id=job_id)
        )
        payload: Dict[str, Any] = {
            "worker_id": self._config.worker_id,
            **result,
        }
        logger.info("Posting result for job %s (status=%s)", job_id, result.get("status"))
        try:
            response = self._post(url, payload)
            if response.status_code in (200, 201, 204):
                if response.status_code == 204 or not response.content:
                    return {}
                return response.json()
            raise JobResultError(
                f"Job result rejected: HTTP {response.status_code} — {response.text[:200]}",
                status_code=response.status_code,
            )
        except JobResultError:
            raise
        except requests.RequestException as exc:
            raise JobResultError(f"Job result network error: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal HTTP helper
    # ------------------------------------------------------------------

    def _post(self, url: str, payload: Dict[str, Any]) -> Response:
        session = self._get_session()
        timeout = (
            self._config.http_connect_timeout,
            self._config.http_read_timeout,
        )
        return session.post(url, json=payload, timeout=timeout)
