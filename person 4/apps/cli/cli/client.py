"""
CLI HTTP client for communicating with the Coordinator.
"""

import httpx

from cli.config import settings


class CoordinatorClient:
    """Client for the CrowdGPU Coordinator API."""

    def __init__(self) -> None:
        self.base_url = settings.coordinator_url.rstrip("/")

    def _get_client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=10.0)

    def list_peers(self) -> list[dict]:
        """Fetch all registered peers."""
        with self._get_client() as client:
            try:
                response = client.get("/api/v1/peers")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Connection failed: {exc}") from exc

    def submit_job(self, owner_id: str, docker_image: str, command: str) -> dict:
        """Submit a new compute job."""
        with self._get_client() as client:
            try:
                response = client.post(
                    "/api/v1/jobs",
                    json={
                        "owner_id": owner_id,
                        "docker_image": docker_image,
                        "command": command,
                    }
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Connection failed: {exc}") from exc

    def list_jobs(self, owner_id: str | None = None) -> list[dict]:
        """List all compute jobs."""
        with self._get_client() as client:
            try:
                params = {"owner_id": owner_id} if owner_id else None
                response = client.get("/api/v1/jobs", params=params)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Connection failed: {exc}") from exc

    def get_job(self, job_id: str) -> dict:
        """Get status of a compute job."""
        with self._get_client() as client:
            try:
                response = client.get(f"/api/v1/jobs/{job_id}")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Connection failed: {exc}") from exc

    def list_signaling_peers(self) -> dict:
        """Fetch all peers connected to WebRTC signaling gateway."""
        with self._get_client() as client:
            try:
                response = client.get("/api/v1/signaling/peers")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Connection failed: {exc}") from exc

    def get_ice_servers(self) -> dict:
        """Fetch configured STUN/TURN ICE servers from coordinator."""
        with self._get_client() as client:
            try:
                response = client.get("/api/v1/signaling/ice-servers")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Connection failed: {exc}") from exc

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
    ) -> dict:
        """Register a new peer and its GPU capability."""
        payload = {
            "owner_id": owner_id,
            "hostname": hostname,
            "initial_status": initial_status,
            "gpu_capabilities": [
                {
                    "gpu_name": gpu_name,
                    "vram_mb": vram_mb,
                    "driver_version": driver_version,
                    "cuda_version": cuda_version,
                    "compute_capability": compute_capability,
                }
            ],
        }
        with self._get_client() as client:
            try:
                response = client.post("/api/v1/peers", json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Connection failed: {exc}") from exc

    def assign_job(self, job_id: str, peer_id: str) -> dict:
        """Assign a compute job to a peer."""
        with self._get_client() as client:
            try:
                response = client.post(f"/api/v1/jobs/{job_id}/assign", json={"peer_id": peer_id})
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Connection failed: {exc}") from exc

    def schedule_job(self) -> dict | None:
        """Dispatch oldest pending job to first available peer."""
        with self._get_client() as client:
            try:
                response = client.post("/api/v1/jobs/schedule")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Connection failed: {exc}") from exc

    def update_job_status(self, job_id: str, status: str) -> dict:
        """Update job lifecycle status (running, completed, failed)."""
        with self._get_client() as client:
            try:
                response = client.patch(f"/api/v1/jobs/{job_id}/status", json={"status": status})
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"Connection failed: {exc}") from exc
