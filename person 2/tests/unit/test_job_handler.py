"""
TASK 11 — Unit tests: JobHandler + validate_job + check_vram.

All GPU, CUDA, and Coordinator calls are mocked.
Tests cover:
  - validate_job: valid, missing fields, bad types
  - check_vram: sufficient, insufficient, margin
  - JobHandler: success path, VRAM rejection, unsupported type,
    CUDA failure, state transitions, result payload,
    Coordinator report failure (non-fatal)
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call


class TestValidateJob(unittest.TestCase):
    def _validate(self, job):
        from worker.executor.job_handler import validate_job
        return validate_job(job)

    def test_valid_job(self):
        self._validate({"job_id": "j1", "type": "matrix_multiply"})  # no exception

    def test_missing_job_id_raises(self):
        from worker.executor.job_handler import InvalidJobError
        with self.assertRaises(InvalidJobError):
            self._validate({"type": "matrix_multiply"})

    def test_missing_type_raises(self):
        from worker.executor.job_handler import InvalidJobError
        with self.assertRaises(InvalidJobError):
            self._validate({"job_id": "j1"})

    def test_empty_job_id_raises(self):
        from worker.executor.job_handler import InvalidJobError
        with self.assertRaises(InvalidJobError):
            self._validate({"job_id": "  ", "type": "matrix_multiply"})

    def test_not_dict_raises(self):
        from worker.executor.job_handler import InvalidJobError
        with self.assertRaises(InvalidJobError):
            self._validate("not a dict")

    def test_negative_vram_raises(self):
        from worker.executor.job_handler import InvalidJobError
        with self.assertRaises(InvalidJobError):
            self._validate({"job_id": "j1", "type": "vector_add", "required_vram_mib": -1})

    def test_valid_with_optional_fields(self):
        self._validate({
            "job_id": "j2",
            "type": "benchmark",
            "required_vram_mib": 512,
            "params": {"dim": 2048},
        })


class TestCheckVRAM(unittest.TestCase):
    def _check(self, free, required, margin=256):
        from worker.executor.cuda_executor import check_vram
        return check_vram(free, required, margin)

    def test_sufficient_vram(self):
        self._check(free=5000, required=1000)  # 5000-256=4744 >= 1000

    def test_exact_boundary(self):
        self._check(free=1256, required=1000)  # 1256-256=1000 == 1000

    def test_insufficient_raises(self):
        from worker.executor.cuda_executor import InsufficientVRAMError
        with self.assertRaises(InsufficientVRAMError):
            self._check(free=1000, required=1000)  # 1000-256=744 < 1000

    def test_zero_required_always_passes(self):
        self._check(free=300, required=0)  # 300-256=44 >= 0

    def test_custom_margin(self):
        from worker.executor.cuda_executor import InsufficientVRAMError
        with self.assertRaises(InsufficientVRAMError):
            self._check(free=600, required=500, margin=200)  # 600-200=400 < 500


class TestJobHandler(unittest.TestCase):
    def _make_handler(self, free_vram=5000, cuda_result=None, coordinator_raises=False):
        """Build a JobHandler with all dependencies mocked."""
        from worker.config import WorkerConfig
        from worker.coordinator.client import CoordinatorClient, JobResultError
        from worker.executor.cuda_executor import CUDAExecutor, CUDAResult
        from worker.executor.job_handler import JobHandler
        from worker.gpu.detector import GPUDetector, GPUTelemetry
        from worker.state import WorkerState, WorkerStateMachine

        config = MagicMock(spec=WorkerConfig)
        config.worker_id = "test-worker"
        config.gpu_id = 0
        config.vram_safety_margin_mib = 256

        sm = WorkerStateMachine()
        sm.transition(WorkerState.AVAILABLE)  # put in AVAILABLE state

        telem = GPUTelemetry(
            gpu_id=0, name="RTX", uuid="uuid",
            total_vram_mib=6141, free_vram_mib=free_vram, used_vram_mib=6141 - free_vram,
            gpu_utilization_pct=0.0, temperature_c=40.0,
            driver_version="616.92", cuda_available=True,
        )
        detector = MagicMock(spec=GPUDetector)
        detector.telemetry.return_value = telem

        coordinator = MagicMock(spec=CoordinatorClient)
        if coordinator_raises:
            coordinator.post_job_result.side_effect = JobResultError("Network error")

        if cuda_result is None:
            cuda_result = CUDAResult(
                workload_type="matrix_multiply",
                device="cuda:0",
                execution_time_s=0.5,
                output={"matrix_dim": 1024, "result_shape": [1024, 1024]},
                success=True,
            )
        executor = MagicMock(spec=CUDAExecutor)
        executor.execute.return_value = cuda_result

        handler = JobHandler(config, sm, detector, coordinator, executor)
        return handler, sm, coordinator, executor

    def test_successful_job_end_to_end(self):
        from worker.executor.job_handler import JobStatus
        from worker.state import WorkerState

        handler, sm, coordinator, executor = self._make_handler()
        job = {"job_id": "job-1", "type": "matrix_multiply", "dim": 1024}
        result = handler.handle(job)

        self.assertEqual(result.status, JobStatus.SUCCESS)
        self.assertIsNone(result.error)
        self.assertGreater(result.execution_time_s, 0)
        self.assertEqual(sm.state, WorkerState.AVAILABLE)  # back to AVAILABLE
        coordinator.post_job_result.assert_called_once()

    def test_invalid_job_rejected(self):
        from worker.executor.job_handler import JobStatus
        from worker.state import WorkerState

        handler, sm, coordinator, executor = self._make_handler()
        result = handler.handle({"job_id": "", "type": "matrix_multiply"})

        self.assertEqual(result.status, JobStatus.REJECTED)
        self.assertIsNotNone(result.error)
        # State should stay AVAILABLE (no transition happened)
        self.assertEqual(sm.state, WorkerState.AVAILABLE)
        executor.execute.assert_not_called()

    def test_insufficient_vram_rejected(self):
        from worker.executor.job_handler import JobStatus
        from worker.state import WorkerState

        handler, sm, coordinator, executor = self._make_handler(free_vram=200)
        # Need 500 MiB, only 200-256 < 0 available
        result = handler.handle({
            "job_id": "j-vram",
            "type": "matrix_multiply",
            "required_vram_mib": 500,
        })
        self.assertEqual(result.status, JobStatus.REJECTED)
        self.assertIn("VRAM", result.error or "")
        executor.execute.assert_not_called()

    def test_cuda_failure_returns_failed(self):
        from worker.executor.cuda_executor import CUDAResult
        from worker.executor.job_handler import JobStatus

        failed_result = CUDAResult(
            workload_type="matrix_multiply",
            device="cuda:0",
            execution_time_s=0.1,
            success=False,
            error="CUDA out of memory",
        )
        handler, sm, coordinator, _ = self._make_handler(cuda_result=failed_result)
        result = handler.handle({"job_id": "j-cuda", "type": "matrix_multiply"})
        self.assertEqual(result.status, JobStatus.FAILED)
        self.assertIn("CUDA", result.error or "")

    def test_unsupported_workload_type_fails(self):
        from worker.executor.cuda_executor import UnsupportedWorkloadError
        from worker.executor.job_handler import JobStatus

        handler, sm, coordinator, executor = self._make_handler()
        executor.execute.side_effect = UnsupportedWorkloadError("not allowed")
        result = handler.handle({"job_id": "j-bad", "type": "matrix_multiply"})
        self.assertEqual(result.status, JobStatus.FAILED)

    def test_coordinator_result_failure_is_non_fatal(self):
        """If posting result fails, the handler should not raise."""
        from worker.executor.job_handler import JobStatus

        handler, sm, coordinator, executor = self._make_handler(coordinator_raises=True)
        result = handler.handle({"job_id": "j-net", "type": "matrix_multiply"})
        # Should still return a result, not raise
        self.assertIsNotNone(result)

    def test_result_payload_structure(self):
        from worker.executor.job_handler import JobStatus

        handler, sm, coordinator, _ = self._make_handler()
        result = handler.handle({"job_id": "j-struct", "type": "matrix_multiply"})
        payload = result.to_coordinator_payload()
        self.assertIn("status", payload)
        self.assertIn("output", payload)
        self.assertIn("execution_time_s", payload)
        self.assertIn("error", payload)
        self.assertEqual(payload["status"], "success")

    def test_state_transitions_during_execution(self):
        """Verify AVAILABLE → BUSY → AVAILABLE sequence."""
        from worker.state import WorkerState
        transitions_seen = []

        handler, sm, _, _ = self._make_handler()
        original_transition = sm.transition

        def spy_transition(state):
            transitions_seen.append(state)
            return original_transition(state)

        sm.transition = spy_transition
        handler.handle({"job_id": "j-trans", "type": "matrix_multiply"})

        self.assertIn(WorkerState.BUSY, transitions_seen)
        self.assertIn(WorkerState.AVAILABLE, transitions_seen)
        # Final state must be AVAILABLE
        self.assertEqual(sm.state, WorkerState.AVAILABLE)


if __name__ == "__main__":
    unittest.main()
