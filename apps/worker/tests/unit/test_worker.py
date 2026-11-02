"""
TASK 11 — Unit tests: Worker orchestrator (worker.py).

All external I/O (GPU, Coordinator, thread) is mocked.
Tests cover:
  - start() happy path: GPU detect → register → AVAILABLE → heartbeat
  - start() GPU failure → ERROR state
  - start() Coordinator failure → ERROR state
  - execute_job() before start() raises
  - execute_job() when not AVAILABLE raises
  - stop() transitions to OFFLINE and closes resources
  - heartbeat loop sends telemetry on interval
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, patch, call


def _make_gpu_info():
    from worker.gpu.detector import GPUInfo
    return GPUInfo(
        gpu_id=0, name="RTX 4050", uuid="GPU-abc",
        total_vram_mib=6141, driver_version="616.92", cuda_available=True,
    )


def _make_telemetry():
    from worker.gpu.detector import GPUTelemetry
    return GPUTelemetry(
        gpu_id=0, name="RTX", uuid="GPU-abc",
        total_vram_mib=6141, free_vram_mib=5000, used_vram_mib=1141,
        gpu_utilization_pct=10.0, temperature_c=45.0,
        driver_version="616.92", cuda_available=True,
    )


def _build_worker(
    gpu_detect_raises=None,
    coordinator_register_raises=None,
):
    """Build a Worker with all dependencies mocked."""
    import os
    os.environ["COORDINATOR_URL"] = "http://coordinator.test"
    os.environ["WORKER_ID"] = "w-test"
    os.environ["GPU_ID"] = "0"
    os.environ["HEARTBEAT_INTERVAL"] = "10"

    from worker.config import WorkerConfig
    from worker.coordinator.client import CoordinatorClient
    from worker.executor.cuda_executor import CUDAExecutor
    from worker.gpu.detector import GPUDetector, GPUDetectionError
    from worker.worker import Worker

    config = WorkerConfig.from_env()
    worker = Worker(config)

    # Mock detector
    detector = MagicMock(spec=GPUDetector)
    if gpu_detect_raises:
        detector.detect.side_effect = gpu_detect_raises
    else:
        detector.detect.return_value = _make_gpu_info()
        detector.telemetry.return_value = _make_telemetry()
    worker._detector = detector

    # Mock coordinator
    coordinator = MagicMock(spec=CoordinatorClient)
    if coordinator_register_raises:
        coordinator.register.side_effect = coordinator_register_raises
    worker._coordinator = coordinator

    # Mock executor
    from worker.executor.cuda_executor import CUDAResult
    executor = MagicMock(spec=CUDAExecutor)
    executor.execute.return_value = CUDAResult(
        workload_type="matrix_multiply",
        device="cuda:0",
        execution_time_s=0.3,
        output={"matrix_dim": 512},
        success=True,
    )
    worker._executor = executor

    return worker, detector, coordinator, executor


class TestWorkerStart(unittest.TestCase):
    def tearDown(self):
        # Clean env
        for k in ("COORDINATOR_URL", "WORKER_ID", "GPU_ID", "HEARTBEAT_INTERVAL"):
            import os; os.environ.pop(k, None)

    def test_start_happy_path(self):
        from worker.state import WorkerState
        worker, detector, coordinator, _ = _build_worker()
        worker.start()

        detector.initialize.assert_called_once()
        detector.detect.assert_called_once()
        coordinator.register.assert_called_once()
        self.assertEqual(worker._sm.state, WorkerState.AVAILABLE)

        worker.stop()

    def test_start_gpu_failure_transitions_to_error(self):
        from worker.gpu.detector import GPUDetectionError
        from worker.state import WorkerState

        worker, _, _, _ = _build_worker(
            gpu_detect_raises=GPUDetectionError("nvmlInit failed")
        )
        with self.assertRaises(GPUDetectionError):
            worker.start()

        self.assertEqual(worker._sm.state, WorkerState.ERROR)

    def test_start_coordinator_failure_transitions_to_error(self):
        from worker.coordinator.client import RegistrationError
        from worker.state import WorkerState

        worker, _, _, _ = _build_worker(
            coordinator_register_raises=RegistrationError("refused")
        )
        with self.assertRaises(RegistrationError):
            worker.start()

        self.assertEqual(worker._sm.state, WorkerState.ERROR)

    def test_start_spawns_heartbeat_thread(self):
        worker, _, _, _ = _build_worker()
        worker.start()

        self.assertIsNotNone(worker._heartbeat_thread)
        self.assertTrue(worker._heartbeat_thread.is_alive())

        worker.stop()
        self.assertFalse(worker._heartbeat_thread.is_alive())

    def test_stop_transitions_to_offline(self):
        from worker.state import WorkerState
        worker, _, _, _ = _build_worker()
        worker.start()
        worker.stop()
        self.assertEqual(worker._sm.state, WorkerState.OFFLINE)

    def test_stop_closes_coordinator(self):
        worker, _, coordinator, _ = _build_worker()
        worker.start()
        worker.stop()
        coordinator.close.assert_called_once()

    def test_stop_shuts_down_detector(self):
        worker, detector, _, _ = _build_worker()
        worker.start()
        worker.stop()
        detector.shutdown.assert_called_once()


class TestWorkerExecuteJob(unittest.TestCase):
    def tearDown(self):
        for k in ("COORDINATOR_URL", "WORKER_ID", "GPU_ID", "HEARTBEAT_INTERVAL"):
            import os; os.environ.pop(k, None)

    def test_execute_job_before_start_raises(self):
        worker, _, _, _ = _build_worker()
        with self.assertRaises(RuntimeError, msg="should raise if not started"):
            worker.execute_job({"job_id": "j1", "type": "matrix_multiply"})

    def test_execute_job_when_not_available_raises(self):
        from worker.state import WorkerState
        worker, _, _, _ = _build_worker()
        worker.start()
        worker._sm.transition(WorkerState.BUSY)  # force BUSY
        with self.assertRaises(RuntimeError):
            worker.execute_job({"job_id": "j2", "type": "matrix_multiply"})
        worker._sm.transition(WorkerState.AVAILABLE)  # clean up for stop()
        worker.stop()

    def test_execute_job_success(self):
        from worker.executor.job_handler import JobStatus
        from worker.state import WorkerState

        worker, detector, coordinator, executor = _build_worker()
        # Set up telemetry for VRAM check
        detector.telemetry.return_value = _make_telemetry()
        worker.start()

        result = worker.execute_job({"job_id": "j-ok", "type": "matrix_multiply"})
        self.assertEqual(result.status, JobStatus.SUCCESS)
        self.assertEqual(worker._sm.state, WorkerState.AVAILABLE)

        worker.stop()

    def test_execute_invalid_job_rejected(self):
        from worker.executor.job_handler import JobStatus

        worker, detector, _, _ = _build_worker()
        detector.telemetry.return_value = _make_telemetry()
        worker.start()

        result = worker.execute_job({"job_id": "", "type": "matrix_multiply"})
        self.assertEqual(result.status, JobStatus.REJECTED)

        worker.stop()


class TestWorkerHeartbeat(unittest.TestCase):
    def tearDown(self):
        for k in ("COORDINATOR_URL", "WORKER_ID", "GPU_ID", "HEARTBEAT_INTERVAL"):
            import os; os.environ.pop(k, None)

    def test_heartbeat_sends_telemetry(self):
        """_send_heartbeat() calls coordinator.send_heartbeat with state."""
        from worker.state import WorkerState

        worker, detector, coordinator, _ = _build_worker()
        worker.start()
        # Call heartbeat once explicitly (don't wait for the interval)
        worker._send_heartbeat()

        coordinator.send_heartbeat.assert_called()
        call_kwargs = coordinator.send_heartbeat.call_args
        # state argument should be current state
        state_arg = call_kwargs[1].get("state") or call_kwargs[0][1]
        self.assertEqual(state_arg, WorkerState.AVAILABLE.value)

        worker.stop()

    def test_heartbeat_gpu_error_is_non_fatal(self):
        """If GPU telemetry throws, heartbeat should not crash the worker."""
        from worker.gpu.detector import GPUDetectionError

        worker, detector, coordinator, _ = _build_worker()
        worker.start()

        # Record calls already made (e.g. by daemon heartbeat thread)
        calls_before = coordinator.send_heartbeat.call_count

        # Now make telemetry fail
        detector.telemetry.side_effect = GPUDetectionError("NVMLError")

        # Explicit heartbeat call — should not raise
        worker._send_heartbeat()

        # No new call to send_heartbeat should have been made
        calls_after = coordinator.send_heartbeat.call_count
        self.assertEqual(
            calls_after, calls_before,
            "send_heartbeat should NOT be called when telemetry raises"
        )

        # Worker is still alive
        self.assertTrue(worker._heartbeat_thread.is_alive())
        worker.stop()

    def test_heartbeat_coordinator_error_is_non_fatal(self):
        """If coordinator POST fails, heartbeat should not crash the worker."""
        from worker.coordinator.client import HeartbeatError

        worker, detector, coordinator, _ = _build_worker()
        detector.telemetry.return_value = _make_telemetry()
        worker.start()
        coordinator.send_heartbeat.side_effect = HeartbeatError("timeout")

        # Should not raise
        worker._send_heartbeat()
        self.assertTrue(worker._heartbeat_thread.is_alive())

        worker.stop()


if __name__ == "__main__":
    unittest.main()
