"""
Unit tests for WorkerExecutor.
"""

from unittest.mock import MagicMock, patch
import pytest

from worker.executor import WorkerExecutor


def test_executor_defaults() -> None:
    executor = WorkerExecutor()
    assert executor.coordinator_url == "http://localhost:8000"
    assert executor.mode == "development"
    assert executor.peer_id is None


def test_executor_register() -> None:
    executor = WorkerExecutor(coordinator_url="http://test-coord:8000")
    with patch.object(executor, "_http_request", return_value={"id": "peer-12345"}) as mock_req:
        peer_id = executor.register(owner_id="owner-abc", hostname="rig-alpha")
        assert peer_id == "peer-12345"
        assert executor.peer_id == "peer-12345"
        mock_req.assert_called_once()
        args, kwargs = mock_req.call_args
        assert args[0] == "POST"
        assert args[1] == "/api/v1/peers"
        assert args[2]["owner_id"] == "owner-abc"
        assert args[2]["hostname"] == "rig-alpha"


def test_executor_fetch_assigned_jobs() -> None:
    executor = WorkerExecutor(peer_id="peer-12345")
    mock_jobs = [
        {"id": "job-1", "status": "assigned", "command": "echo test", "docker_image": "ubuntu"}
    ]
    with patch.object(executor, "_http_request", return_value=mock_jobs) as mock_req:
        jobs = executor.fetch_assigned_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "job-1"
        mock_req.assert_called_once_with(
            "GET", "/api/v1/jobs?assigned_peer_id=peer-12345&status=assigned"
        )


def test_executor_fetch_assigned_jobs_no_peer_id_raises() -> None:
    executor = WorkerExecutor()
    with pytest.raises(RuntimeError, match="cannot fetch assigned jobs without peer registration"):
        executor.fetch_assigned_jobs()


def test_executor_execute_job_lifecycle() -> None:
    executor = WorkerExecutor(peer_id="peer-12345", mode="development")
    job = {
        "id": "job-abc",
        "command": "python train.py",
        "docker_image": "nvidia/cuda:12.0",
    }
    status_calls = []

    def mock_update(job_id, status):
        status_calls.append((job_id, status))
        return {"id": job_id, "status": status}

    with patch.object(executor, "update_job_status", side_effect=mock_update):
        success = executor.execute_job(job)
        assert success is True
        assert status_calls == [
            ("job-abc", "running"),
            ("job-abc", "completed"),
        ]


def test_executor_process_next_assigned() -> None:
    executor = WorkerExecutor(peer_id="peer-12345", mode="development")
    job = {
        "id": "job-999",
        "command": "echo done",
        "docker_image": "ubuntu:latest",
    }
    with (
        patch.object(executor, "fetch_assigned_jobs", return_value=[job]),
        patch.object(executor, "execute_job", return_value=True) as mock_exec,
    ):
        result = executor.process_next_assigned()
        assert result is True
        mock_exec.assert_called_once_with(job)
