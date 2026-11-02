"""
CLI HTTP client for communicating with the CrowdGPU Coordinator API.

Implements the Stage 1 canonical REST API contracts:
- GET /health
- GET /api/v1/peers
- GET /api/v1/peers/{peer_id}
- POST /api/v1/peers
- POST /api/v1/jobs
- GET /api/v1/jobs
- GET /api/v1/jobs/{job_id}
- POST /api/v1/jobs/{job_id}/cancel
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from cli.config import CliSettings, get_settings


# ---------------------------------------------------------------------------
# Custom CLI Exceptions
# ---------------------------------------------------------------------------
class CoordinatorClientError(Exception):
    """Base exception for all CLI coordinator client errors."""


class CoordinatorConnectionError(CoordinatorClientError):
    """Raised when connecting to the coordinator fails (offline, connection refused, DNS)."""


class CoordinatorAuthError(CoordinatorClientError):
    """Raised on 401 Unauthorized or 403 Forbidden."""


class CoordinatorNotFoundError(CoordinatorClientError):
    """Raised when a job or peer is not found (404)."""


class InvalidStateTransitionError(CoordinatorClientError):
    """Raised on 409 Conflict (e.g. attempting to cancel an active/completed job)."""


class CoordinatorValidationError(CoordinatorClientError):
    """Raised on 422 Unprocessable Entity."""


class CoordinatorAPIError(CoordinatorClientError):
    """Raised for any other unexpected HTTP status error."""


# ---------------------------------------------------------------------------
# Coordinator Client
# ---------------------------------------------------------------------------
class CoordinatorClient:
    """Client for the CrowdGPU Coordinator API."""

    def __init__(self, settings_override: CliSettings | None = None) -> None:
        self.settings = settings_override or get_settings()
        self.base_url = self.settings.coordinator_url.rstrip("/")
        self.user_id = self.settings.user_id

    def _get_headers(self) -> dict[str, str]:
        """
        Produce user client headers.
        CRITICAL: Never reuses worker identity headers (X-Peer-Id, X-Worker-ID).
        """
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.user_id:
            headers["X-User-Id"] = self.user_id
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.settings.timeout_seconds) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=self._get_headers(),
                    params=params,
                    json=json_data,
                )
        except httpx.ConnectError as exc:
            raise CoordinatorConnectionError(
                f"Cannot connect to CrowdGPU Coordinator at {self.base_url}. "
                "Ensure coordinator service is running on the specified host and port."
            ) from exc
        except httpx.TimeoutException as exc:
            raise CoordinatorConnectionError(
                f"Request to Coordinator at {self.base_url} timed out after {self.settings.timeout_seconds}s."
            ) from exc
        except httpx.RequestError as exc:
            raise CoordinatorConnectionError(f"Network error communicating with Coordinator: {exc}") from exc

        # Handle HTTP error status codes
        if response.status_code == 401 or response.status_code == 403:
            detail = self._extract_error_detail(response)
            raise CoordinatorAuthError(
                f"Authentication failure (HTTP {response.status_code}): {detail or 'User ID rejected'}"
            )

        if response.status_code == 404:
            detail = self._extract_error_detail(response)
            raise CoordinatorNotFoundError(detail or f"Resource not found at {path}")

        if response.status_code == 409:
            detail = self._extract_error_detail(response)
            raise InvalidStateTransitionError(detail or "Invalid state transition or resource conflict")

        if response.status_code == 422:
            detail = self._extract_error_detail(response)
            raise CoordinatorValidationError(detail or "Validation failed on requested parameters")

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_detail(response)
            raise CoordinatorAPIError(
                f"Coordinator API error (HTTP {response.status_code}): {detail or response.text}"
            ) from exc

        if response.status_code == 204:
            return None
        return response.json()

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
            if isinstance(data, dict):
                detail = data.get("detail")
                if isinstance(detail, list):
                    # Pydantic 422 errors list
                    messages = [f"{'.'.join(str(loc) for loc in err.get('loc', []))}: {err.get('msg')}" for err in detail]
                    return "; ".join(messages)
                if detail:
                    return str(detail)
            return response.text
        except Exception:
            return response.text

    # -------------------------------------------------------------------------
    # Health & System
    # -------------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        """Fetch coordinator liveness and health status."""
        return self._request("GET", "/health")

    # -------------------------------------------------------------------------
    # Peers
    # -------------------------------------------------------------------------
    def list_peers(self) -> list[dict[str, Any]]:
        """Fetch all registered provider peers and their GPU capabilities."""
        data = self._request("GET", "/api/v1/peers")
        return data if isinstance(data, list) else []

    def get_peer(self, peer_id: str | uuid.UUID) -> dict[str, Any]:
        """Fetch details of a single registered peer node."""
        return self._request("GET", f"/api/v1/peers/{peer_id}")

    def register_peer(
        self,
        owner_id: str,
        hostname: str,
        gpu_name: str,
        vram_mb: int,
        initial_status: str = "available",
        driver_version: str | None = None,
        cuda_version: str | None = None,
        compute_capability: str | None = None,
    ) -> dict[str, Any]:
        """Register a provider peer node with GPU capabilities."""
        payload = {
            "owner_id": owner_id,
            "hostname": hostname,
            "initial_status": initial_status,
            "gpu_capabilities": [
                {
                    "gpu_name": gpu_name,
                    "vram_mb": int(vram_mb),
                    "driver_version": driver_version,
                    "cuda_version": cuda_version,
                    "compute_capability": compute_capability,
                }
            ],
        }
        return self._request("POST", "/api/v1/peers", json_data=payload)

    # -------------------------------------------------------------------------
    # Jobs
    # -------------------------------------------------------------------------
    def submit_job(
        self,
        name: str,
        command: str,
        required_vram_mb: int = 512,
        workload_type: str = "matrix_multiply",
        docker_image: str | None = None,
    ) -> dict[str, Any]:
        """Submit a computational workload using the canonical JobCreate schema."""
        payload = {
            "name": name,
            "command": command,
            "required_vram_mb": int(required_vram_mb),
            "vram_required_mb": int(required_vram_mb),
            "workload_type": workload_type,
            "docker_image": docker_image,
        }
        return self._request("POST", "/api/v1/jobs", json_data=payload)

    def list_jobs(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List jobs submitted by caller, with optional status filtering."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status.upper().strip()
        data = self._request("GET", "/api/v1/jobs", params=params)
        return data if isinstance(data, list) else []

    def get_job(self, job_id: str | uuid.UUID) -> dict[str, Any]:
        """Fetch details, assignment status, and result of a specific job."""
        return self._request("GET", f"/api/v1/jobs/{job_id}")

    def cancel_job(self, job_id: str | uuid.UUID) -> dict[str, Any]:
        """Cancel an eligible QUEUED job."""
        return self._request("POST", f"/api/v1/jobs/{job_id}/cancel")

    # -------------------------------------------------------------------------
    # WebRTC Signaling Info
    # -------------------------------------------------------------------------
    def list_signaling_peers(self) -> dict[str, Any]:
        """Fetch active peers connected to the WebRTC signaling gateway."""
        return self._request("GET", "/api/v1/signaling/peers")

    def get_ice_servers(self) -> dict[str, Any]:
        """Fetch configured STUN/TURN ICE servers from coordinator."""
        return self._request("GET", "/api/v1/signaling/ice-servers")
