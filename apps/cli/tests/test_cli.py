"""
Unit and integration tests for CrowdGPU CLI.

Tests:
- --help and --version options
- health check (online, offline)
- peers list and get
- jobs submit (presets, validation, custom flags)
- jobs list (with status filter)
- jobs status (with execution results)
- jobs cancel (queued, conflict, not found)
- client header separation (X-User-Id vs worker headers)
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from click.testing import CliRunner

from cli import __version__
from cli.client import (
    CoordinatorAuthError,
    CoordinatorClient,
    CoordinatorConnectionError,
    CoordinatorNotFoundError,
    InvalidStateTransitionError,
)
from cli.config import CliSettings
from cli.main import cli
from cli.workloads import resolve_workload


# ---------------------------------------------------------------------------
# Basic CLI tests
# ---------------------------------------------------------------------------
def test_help_exits_zero() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "CrowdGPU" in result.output
    assert "health" in result.output
    assert "peers" in result.output
    assert "jobs" in result.output


def test_version_output() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


# ---------------------------------------------------------------------------
# Health command tests
# ---------------------------------------------------------------------------
def test_health_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"
            self.user_id = "00000000-0000-0000-0000-000000000001"

        def health(self) -> dict[str, Any]:
            return {"status": "ok", "version": "0.1.0"}

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["health"])
    assert result.exit_code == 0
    assert "=== Coordinator Health ===" in result.output
    assert "Status:          ok" in result.output
    assert "Version:         0.1.0" in result.output


def test_health_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"

        def health(self) -> dict[str, Any]:
            raise CoordinatorConnectionError("Connection refused")

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["health"])
    assert result.exit_code != 0
    assert "Coordinator unreachable" in result.output


# ---------------------------------------------------------------------------
# Peers command tests
# ---------------------------------------------------------------------------
def test_peers_list_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_peers = [
        {
            "id": "b1691e68-46a2-533b-bda1-7b1c07e0c8f5",
            "hostname": "demo-rtx3050-worker",
            "status": "available",
            "gpu_capabilities": [
                {
                    "gpu_name": "NVIDIA GeForce RTX 3050 Laptop GPU",
                    "vram_mb": 4096,
                    "driver_version": "591.91",
                    "cuda_version": "12.8",
                    "compute_capability": "8.6",
                }
            ],
        }
    ]

    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"

        def list_peers(self) -> list[dict[str, Any]]:
            return mock_peers

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["peers", "list"])
    assert result.exit_code == 0
    assert "demo-rtx3050-worker" in result.output
    assert "AVAILABLE" in result.output
    assert "RTX 3050" in result.output
    assert "4096 MiB" in result.output


def test_peers_list_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"

        def list_peers(self) -> list[dict[str, Any]]:
            return []

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["peers", "list"])
    assert result.exit_code == 0
    assert "No provider peers registered." in result.output


def test_peers_get_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_peer = {
        "id": "b1691e68-46a2-533b-bda1-7b1c07e0c8f5",
        "hostname": "test-rig",
        "status": "available",
        "owner_id": "00000000-0000-0000-0000-000000000001",
        "registered_at": "2026-10-15T00:00:00Z",
        "last_seen_at": "2026-10-15T00:01:00Z",
        "gpu_capabilities": [
            {
                "gpu_name": "NVIDIA GeForce RTX 4090",
                "vram_mb": 24576,
                "driver_version": "535.104",
                "cuda_version": "12.2",
                "compute_capability": "8.9",
            }
        ],
    }

    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"

        def get_peer(self, peer_id: str) -> dict[str, Any]:
            return mock_peer

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["peers", "get", "b1691e68-46a2-533b-bda1-7b1c07e0c8f5"])
    assert result.exit_code == 0
    assert "=== Peer Details ===" in result.output
    assert "test-rig" in result.output
    assert "NVIDIA GeForce RTX 4090" in result.output
    assert "24576 MiB" in result.output


def test_peers_get_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"

        def get_peer(self, peer_id: str) -> dict[str, Any]:
            raise CoordinatorNotFoundError(f"Peer '{peer_id}' not found.")

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["peers", "get", "bad-id"])
    assert result.exit_code != 0
    assert "Peer 'bad-id' not found" in result.output


# ---------------------------------------------------------------------------
# Jobs submit tests
# ---------------------------------------------------------------------------
def test_jobs_submit_with_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"
            self.user_id = "00000000-0000-0000-0000-000000000001"

        def submit_job(self, name, command, required_vram_mb, workload_type, docker_image):
            captured.update(
                {
                    "name": name,
                    "command": command,
                    "required_vram_mb": required_vram_mb,
                    "workload_type": workload_type,
                    "docker_image": docker_image,
                }
            )
            return {
                "id": "04cebf28-0f99-4198-84e0-bc0c863c17f0",
                "name": name,
                "status": "ASSIGNED",
                "workload_type": workload_type,
                "vram_required_mb": required_vram_mb,
                "assigned_peer_id": "b1691e68-46a2-533b-bda1-7b1c07e0c8f5",
                "peer_hostname": "demo-worker",
            }

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "submit", "--preset", "matrix_multiply"])
    assert result.exit_code == 0
    assert "[+] Job submitted successfully!" in result.output
    assert "04cebf28-0f99-4198-84e0-bc0c863c17f0" in result.output
    assert "ASSIGNED" in result.output
    assert "demo-worker" in result.output

    assert captured["workload_type"] == "matrix_multiply"
    assert captured["command"] == "matrix_multiply"
    assert captured["required_vram_mb"] == 512


def test_jobs_submit_docker_requires_image() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "submit", "--preset", "docker"])
    assert result.exit_code != 0
    assert "Docker image (--docker-image) is required" in result.output


def test_jobs_submit_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"
            self.user_id = "00000000-0000-0000-0000-000000000001"

        def submit_job(self, *args, **kwargs):
            raise CoordinatorAuthError("Authentication failure: User ID rejected")

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "submit", "--preset", "benchmark"])
    assert result.exit_code != 0
    assert "Auth error" in result.output


# ---------------------------------------------------------------------------
# Jobs list & status tests
# ---------------------------------------------------------------------------
def test_jobs_list_with_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_status = []

    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"

        def list_jobs(self, status=None, limit=50, offset=0):
            captured_status.append(status)
            return [
                {
                    "id": "job-1",
                    "name": "MatMul Test",
                    "status": "QUEUED",
                    "workload_type": "matrix_multiply",
                    "assigned_peer_id": None,
                }
            ]

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "list", "--status", "QUEUED"])
    assert result.exit_code == 0
    assert "job-1" in result.output
    assert "QUEUED" in result.output
    assert captured_status == ["QUEUED"]


def test_jobs_status_displays_result(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_job = {
        "id": "04cebf28-0f99-4198-84e0-bc0c863c17f0",
        "name": "CUDA Matrix Multiplication",
        "status": "COMPLETED",
        "workload_type": "matrix_multiply",
        "command": "matrix_multiply",
        "vram_required_mb": 512,
        "attempt_count": 1,
        "assigned_peer_id": "b1691e68-46a2-533b-bda1-7b1c07e0c8f5",
        "peer_hostname": "demo-rtx3050-worker",
        "gpu_name": "NVIDIA GeForce RTX 3050 Laptop GPU",
        "created_at": "2026-10-15T00:00:00Z",
        "started_at": "2026-10-15T00:00:01Z",
        "completed_at": "2026-10-15T00:00:03Z",
        "result": {
            "exit_code": 0,
            "execution_time_s": 1.629,
            "output": {
                "matrix_dim": 1024,
                "result_shape": [1024, 1024],
                "result_mean": 0.0012,
                "result_std": 31.98,
            },
        },
        "error": None,
    }

    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"

        def get_job(self, job_id):
            return mock_job

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "status", "04cebf28-0f99-4198-84e0-bc0c863c17f0"])
    assert result.exit_code == 0
    assert "=== Job Details ===" in result.output
    assert "COMPLETED" in result.output
    assert "demo-rtx3050-worker" in result.output
    assert "NVIDIA GeForce RTX 3050" in result.output
    assert "Exit Code:     0" in result.output
    assert "Duration:      1.6290s" in result.output
    assert "matrix_dim: 1024" in result.output


# ---------------------------------------------------------------------------
# Jobs cancel tests
# ---------------------------------------------------------------------------
def test_jobs_cancel_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"

        def cancel_job(self, job_id):
            return {"id": job_id, "status": "CANCELLED"}

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "cancel", "job-queued"])
    assert result.exit_code == 0
    assert "Job job-queued cancelled successfully." in result.output
    assert "Status: CANCELLED" in result.output


def test_jobs_cancel_conflict_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockClient(CoordinatorClient):
        def __init__(self, *args, **kwargs):
            self.base_url = "http://127.0.0.1:8000"

        def cancel_job(self, job_id):
            raise InvalidStateTransitionError(
                "Only jobs in QUEUED status can be cancelled (current status: RUNNING)"
            )

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)
    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "cancel", "job-running"])
    assert result.exit_code != 0
    assert "Cannot cancel job" in result.output
    assert "Only jobs in QUEUED status can be cancelled" in result.output


# ---------------------------------------------------------------------------
# Identity & Client Header Separation Tests
# ---------------------------------------------------------------------------
def test_client_headers_contain_x_user_id_and_no_worker_headers() -> None:
    """Verifies Requirement 3: Worker headers are never reused as user identity headers."""
    client = CoordinatorClient(
        settings_override=CliSettings(
            coordinator_url="http://localhost:8000",
            user_id="11111111-2222-3333-4444-555555555555",
        )
    )
    headers = client._get_headers()
    assert headers.get("X-User-Id") == "11111111-2222-3333-4444-555555555555"
    assert "X-Peer-Id" not in headers
    assert "X-Worker-ID" not in headers
    assert "x-worker-id" not in headers
    assert "x-peer-id" not in headers
