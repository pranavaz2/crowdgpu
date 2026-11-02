"""
Tests for the CLI entry point.
"""

from click.testing import CliRunner

from cli.main import cli
from cli import __version__


def test_help_exits_zero() -> None:
    """--help should exit with code 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0


def test_help_contains_crowdgpu() -> None:
    """--help output should mention CrowdGPU."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert "CrowdGPU" in result.output


def test_version_exits_zero() -> None:
    """--version should exit with code 0."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0


def test_version_output_contains_version_string() -> None:
    """--version output should contain the current version."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert __version__ in result.output


def test_jobs_group_help() -> None:
    """jobs --help should exit zero."""
    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "--help"])
    assert result.exit_code == 0


def test_sessions_group_help() -> None:
    """sessions --help should exit zero."""
    runner = CliRunner()
    result = runner.invoke(cli, ["sessions", "--help"])
    assert result.exit_code == 0


def test_peers_group_help() -> None:
    """peers --help should exit zero."""
    runner = CliRunner()
    result = runner.invoke(cli, ["peers", "--help"])
    assert result.exit_code == 0


def test_jobs_submit_success(monkeypatch) -> None:
    class MockClient:
        def submit_job(self, owner_id, docker_image, command):
            return {"id": "job-123"}

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "submit", "--owner-id", "owner1", "--docker-image", "ubuntu", "--command", "echo"])
    assert result.exit_code == 0
    assert "Job submitted successfully. Job ID: job-123" in result.output


def test_jobs_list_success(monkeypatch) -> None:
    class MockClient:
        def list_jobs(self, owner_id):
            return [{"id": "job-123", "owner_id": "owner1", "status": "pending", "docker_image": "ubuntu"}]

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "list"])
    assert result.exit_code == 0
    assert "job-123" in result.output
    assert "owner1" in result.output


def test_jobs_status_success(monkeypatch) -> None:
    class MockClient:
        def get_job(self, job_id):
            return {"id": job_id, "owner_id": "owner1", "status": "pending", "docker_image": "ubuntu", "command": "echo"}

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "status", "job-123"])
    assert result.exit_code == 0
    assert "Job ID: job-123" in result.output
    assert "Status: pending" in result.output


def test_peers_list_success(monkeypatch) -> None:
    mock_peers = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "hostname": "test-host",
            "status": "available",
            "gpu_capabilities": [{"gpu_name": "RTX 3080", "vram_mb": 10240}]
        }
    ]

    class MockClient:
        def list_peers(self):
            return mock_peers

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["peers", "list"])
    assert result.exit_code == 0
    assert "11111111-1111-1111-1111-111111111111" in result.output
    assert "test-host" in result.output
    assert "RTX 3080" in result.output


def test_peers_list_empty(monkeypatch) -> None:
    class MockClient:
        def list_peers(self):
            return []

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["peers", "list"])
    assert result.exit_code == 0
    assert "No peers found." in result.output


def test_peers_register_success(monkeypatch) -> None:
    class MockClient:
        def register_peer(self, owner_id, hostname, gpu_name, vram_mb):
            return {"id": "peer-999", "hostname": hostname, "status": "available"}

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "peers", "register",
        "--owner-id", "owner-1",
        "--hostname", "rig-1",
        "--gpu", "RTX 4090",
        "--vram", "24576",
    ])
    assert result.exit_code == 0
    assert "Peer registered successfully. Peer ID: peer-999" in result.output


def test_jobs_assign_success(monkeypatch) -> None:
    class MockClient:
        def assign_job(self, job_id, peer_id):
            return {"id": job_id, "assigned_peer_id": peer_id, "status": "assigned"}

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "assign", "job-1", "--peer-id", "peer-1"])
    assert result.exit_code == 0
    assert "Job job-1 assigned to peer peer-1. Status: assigned" in result.output


def test_jobs_schedule_success(monkeypatch) -> None:
    class MockClient:
        def schedule_job(self):
            return {"id": "job-auto", "assigned_peer_id": "peer-auto", "status": "assigned"}

    monkeypatch.setattr("cli.main.CoordinatorClient", MockClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["jobs", "schedule"])
    assert result.exit_code == 0
    assert "Scheduled job job-auto to peer peer-auto. Status: assigned" in result.output
