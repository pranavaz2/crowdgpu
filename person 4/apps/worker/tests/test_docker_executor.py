"""
Unit tests for Docker executor and WorkerExecutor container integration.

All Docker CLI interactions are mocked to enable fast, hermetic testing without
requiring a running Docker daemon.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from worker.docker import (
    DockerExecutionResult,
    build_docker_run_args,
    cleanup_container,
    execute_docker_job,
    parse_and_validate_command,
    validate_docker_image,
)
from worker.executor import WorkerExecutor


# ---------------------------------------------------------------------------
# Image Validation Tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "valid_image",
    [
        "ubuntu",
        "ubuntu:latest",
        "ubuntu:22.04",
        "nvidia/cuda:12.0-base-ubuntu22.04",
        "docker.io/library/python:3.11-slim",
        "ghcr.io/owner/repo:v1.2.3",
        "localhost:5000/my-image:latest",
        "alpine@sha256:c5b1261d6d3e43071626931fc004f70149baeba2c8ec672bd49f277b8218e680",
    ],
)
def test_validate_docker_image_valid(valid_image: str) -> None:
    assert validate_docker_image(valid_image) == valid_image


@pytest.mark.parametrize(
    "invalid_image",
    [
        "",
        "   ",
        "--privileged",
        "-v /:/host ubuntu",
        "ubuntu; rm -rf /",
        "ubuntu | curl evil.com",
        "ubuntu && whoami",
        "ubuntu `id`",
        "ubuntu$(whoami)",
        "ubuntu\0",
        "ubuntu\nlatest",
        "a" * 256,
    ],
)
def test_validate_docker_image_invalid(invalid_image: str) -> None:
    with pytest.raises(ValueError):
        validate_docker_image(invalid_image)


# ---------------------------------------------------------------------------
# Command Parsing Tests
# ---------------------------------------------------------------------------
def test_parse_and_validate_command_simple() -> None:
    cmd = "echo hello world"
    args = parse_and_validate_command(cmd)
    assert args == ["echo", "hello", "world"]


def test_parse_and_validate_command_quotes() -> None:
    cmd = "python -c \"import sys; print('hello')\""
    args = parse_and_validate_command(cmd)
    assert args == ["python", "-c", "import sys; print('hello')"]


@pytest.mark.parametrize(
    "invalid_cmd",
    [
        "",
        "   ",
        "echo 'unclosed string",
        "echo \0 forbidden",
    ],
)
def test_parse_and_validate_command_invalid(invalid_cmd: str) -> None:
    with pytest.raises(ValueError):
        parse_and_validate_command(invalid_cmd)


# ---------------------------------------------------------------------------
# Docker Command Construction Tests
# ---------------------------------------------------------------------------
def test_build_docker_run_args_structure() -> None:
    image = "ubuntu:latest"
    cmd_args = ["echo", "hello"]
    container_name = "crowdgpu-job-test-123"

    args = build_docker_run_args(image, cmd_args, container_name)

    assert args[0] == "docker"
    assert args[1] == "run"
    assert "--name" in args
    assert container_name in args
    assert "--rm" in args
    assert "--security-opt=no-new-privileges" in args
    assert image in args
    assert args[-2:] == ["echo", "hello"]

    # Security guarantees: no privileged flags or host mounts
    assert "--privileged" not in args
    assert "-v" not in args
    assert "--volume" not in args
    assert "--mount" not in args


def test_build_docker_run_args_invalid_container_name() -> None:
    with pytest.raises(ValueError, match="Invalid container name"):
        build_docker_run_args("ubuntu:latest", ["echo"], "--invalid-flag")


# ---------------------------------------------------------------------------
# Container Cleanup Tests
# ---------------------------------------------------------------------------
def test_cleanup_container_invokes_docker_rm() -> None:
    with patch("subprocess.run") as mock_run:
        cleanup_container("test-container")
        mock_run.assert_called_once_with(
            ["docker", "rm", "-f", "test-container"],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )


def test_cleanup_container_handles_not_found() -> None:
    with patch("subprocess.run", side_effect=FileNotFoundError("docker not found")):
        # Should not raise
        cleanup_container("test-container")


def test_cleanup_container_handles_timeout() -> None:
    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["docker"], timeout=10.0),
    ):
        # Should not raise
        cleanup_container("test-container")


# ---------------------------------------------------------------------------
# Docker Execution Tests (Mocked Subprocess)
# ---------------------------------------------------------------------------
def test_execute_docker_job_success() -> None:
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "hello\n"
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        res = execute_docker_job("ubuntu:latest", "echo hello", container_name="test-job-1")
        assert res.is_success is True
        assert res.exit_code == 0
        assert res.stdout == "hello\n"
        assert res.timed_out is False
        assert res.error_message is None
        # Subprocess was invoked
        mock_run.assert_called()


def test_execute_docker_job_nonzero_exit() -> None:
    mock_proc = MagicMock()
    mock_proc.returncode = 42
    mock_proc.stdout = ""
    mock_proc.stderr = "error occurred\n"

    with patch("subprocess.run", return_value=mock_proc):
        res = execute_docker_job("ubuntu:latest", "exit 42", container_name="test-job-fail")
        assert res.is_success is False
        assert res.exit_code == 42
        assert res.stderr == "error occurred\n"


def test_execute_docker_job_timeout() -> None:
    timeout_exc = subprocess.TimeoutExpired(
        cmd=["docker", "run"],
        timeout=5.0,
        output=b"partial output",
        stderr=b"timeout",
    )

    with (
        patch("subprocess.run", side_effect=timeout_exc),
        patch("worker.docker.cleanup_container") as mock_cleanup,
    ):
        res = execute_docker_job(
            "ubuntu:latest", "sleep 100", container_name="test-job-timeout", timeout=5.0
        )
        assert res.is_success is False
        assert res.timed_out is True
        assert "timed out" in (res.error_message or "").lower()
        # Ensure cleanup was invoked
        mock_cleanup.assert_called()


def test_execute_docker_job_docker_cli_missing() -> None:
    with patch("subprocess.run", side_effect=FileNotFoundError("No docker")):
        res = execute_docker_job("ubuntu:latest", "echo hello")
        assert res.is_success is False
        assert "not found" in (res.error_message or "").lower()


def test_execute_docker_job_validation_failure() -> None:
    res = execute_docker_job("--bad-image", "echo hello")
    assert res.is_success is False
    assert res.exit_code == -1
    assert (
        "hyphen" in (res.error_message or "").lower()
        or "invalid" in (res.error_message or "").lower()
    )


# ---------------------------------------------------------------------------
# WorkerExecutor Integration Tests with Docker Mode
# ---------------------------------------------------------------------------
def test_worker_executor_mode_selection() -> None:
    # Explicit mode
    assert WorkerExecutor(mode="docker").execution_mode == "docker"
    assert WorkerExecutor(mode="simulation").execution_mode == "simulation"
    assert WorkerExecutor(mode="development").execution_mode == "simulation"

    # Explicit execution_mode argument
    assert WorkerExecutor(execution_mode="docker").execution_mode == "docker"
    assert WorkerExecutor(execution_mode="simulation").execution_mode == "simulation"


def test_worker_executor_docker_mode_success() -> None:
    executor = WorkerExecutor(peer_id="peer-test", execution_mode="docker")
    job = {
        "id": "job-100",
        "docker_image": "ubuntu:latest",
        "command": "echo test",
    }
    status_calls: list[tuple[str, str]] = []

    def mock_status(job_id: str, status: str) -> dict:
        status_calls.append((job_id, status))
        return {"id": job_id, "status": status}

    mock_result = DockerExecutionResult(
        exit_code=0,
        stdout="test output",
        stderr="",
        timed_out=False,
    )

    with (
        patch.object(executor, "update_job_status", side_effect=mock_status),
        patch("worker.executor.execute_docker_job", return_value=mock_result) as mock_exec,
    ):
        success = executor.execute_job(job)
        assert success is True
        mock_exec.assert_called_once()
        assert status_calls == [
            ("job-100", "running"),
            ("job-100", "completed"),
        ]


def test_worker_executor_docker_mode_failure_reports_failed() -> None:
    executor = WorkerExecutor(peer_id="peer-test", execution_mode="docker")
    job = {
        "id": "job-200",
        "docker_image": "ubuntu:latest",
        "command": "bad_cmd",
    }
    status_calls: list[tuple[str, str]] = []

    def mock_status(job_id: str, status: str) -> dict:
        status_calls.append((job_id, status))
        return {"id": job_id, "status": status}

    mock_result = DockerExecutionResult(
        exit_code=127,
        stdout="",
        stderr="command not found",
        timed_out=False,
    )

    with (
        patch.object(executor, "update_job_status", side_effect=mock_status),
        patch("worker.executor.execute_docker_job", return_value=mock_result),
    ):
        success = executor.execute_job(job)
        assert success is False
        assert status_calls == [
            ("job-200", "running"),
            ("job-200", "failed"),
        ]


def test_worker_executor_docker_mode_timeout_reports_failed() -> None:
    executor = WorkerExecutor(peer_id="peer-test", execution_mode="docker")
    job = {
        "id": "job-300",
        "docker_image": "ubuntu:latest",
        "command": "sleep 999",
    }
    status_calls: list[tuple[str, str]] = []

    def mock_status(job_id: str, status: str) -> dict:
        status_calls.append((job_id, status))
        return {"id": job_id, "status": status}

    mock_result = DockerExecutionResult(
        exit_code=-1,
        stdout="",
        stderr="",
        timed_out=True,
        error_message="Container execution timed out",
    )

    with (
        patch.object(executor, "update_job_status", side_effect=mock_status),
        patch("worker.executor.execute_docker_job", return_value=mock_result),
    ):
        success = executor.execute_job(job)
        assert success is False
        assert status_calls == [
            ("job-300", "running"),
            ("job-300", "failed"),
        ]


def test_worker_executor_docker_mode_exception_restores_peer() -> None:
    executor = WorkerExecutor(peer_id="peer-test", execution_mode="docker")
    job = {
        "id": "job-400",
        "docker_image": "ubuntu:latest",
        "command": "echo crash",
    }
    status_calls: list[tuple[str, str]] = []

    def mock_status(job_id: str, status: str) -> dict:
        status_calls.append((job_id, status))
        return {"id": job_id, "status": status}

    with (
        patch.object(executor, "update_job_status", side_effect=mock_status),
        patch("worker.executor.execute_docker_job", side_effect=RuntimeError("System crash")),
        patch.object(executor, "ensure_peer_available") as mock_ensure,
    ):
        success = executor.execute_job(job)
        assert success is False
        assert status_calls == [
            ("job-400", "running"),
            ("job-400", "failed"),
        ]
        mock_ensure.assert_called_once()
