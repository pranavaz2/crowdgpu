"""
TASK 11 — Integration test: live GPU detection.

This test runs against the REAL NVIDIA GPU using PyNVML.
It is skipped automatically if no NVIDIA GPU is available.

Run with:  pytest tests/integration/ -v
"""

from __future__ import annotations

import os
import unittest


def _nvml_available() -> bool:
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=FutureWarning)
            import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        pynvml.nvmlShutdown()
        return count > 0
    except Exception:
        return False


@unittest.skipUnless(_nvml_available(), "No NVIDIA GPU / pynvml not available")
class TestGPUDetectorIntegration(unittest.TestCase):
    """Live integration tests against the real GPU."""

    def setUp(self):
        from worker.gpu.detector import GPUDetector
        self.detector = GPUDetector(gpu_id=0)
        self.detector.initialize()

    def tearDown(self):
        self.detector.shutdown()

    def test_detect_returns_real_gpu_info(self):
        from worker.gpu.detector import GPUInfo
        info = self.detector.detect()
        self.assertIsInstance(info, GPUInfo)
        self.assertGreater(len(info.name), 0)
        self.assertGreater(info.total_vram_mib, 0)
        self.assertNotEqual(info.uuid, "unknown-uuid")
        self.assertNotEqual(info.driver_version, "unknown")
        print(f"\n[Integration] GPU: {info.name}")
        print(f"[Integration] UUID: {info.uuid}")
        print(f"[Integration] VRAM: {info.total_vram_mib} MiB")
        print(f"[Integration] Driver: {info.driver_version}")
        print(f"[Integration] CUDA: {info.cuda_available}")

    def test_telemetry_returns_valid_values(self):
        from worker.gpu.detector import GPUTelemetry
        telem = self.detector.telemetry()
        self.assertIsInstance(telem, GPUTelemetry)
        self.assertGreaterEqual(telem.total_vram_mib, 0)
        self.assertGreaterEqual(telem.free_vram_mib, 0)
        self.assertGreaterEqual(telem.used_vram_mib, 0)
        self.assertLessEqual(telem.used_vram_mib, telem.total_vram_mib)
        # utilization should be in [0, 100] or -1 (error fallback)
        self.assertTrue(
            telem.gpu_utilization_pct >= -1.0,
            f"Unexpected utilization: {telem.gpu_utilization_pct}",
        )
        print(f"\n[Integration] Free VRAM: {telem.free_vram_mib} MiB")
        print(f"[Integration] Utilization: {telem.gpu_utilization_pct}%")
        print(f"[Integration] Temperature: {telem.temperature_c}°C")

    def test_vram_constraint_zero_always_passes(self):
        self.assertTrue(self.detector.has_free_vram(0))

    def test_vram_constraint_huge_fails(self):
        self.assertFalse(self.detector.has_free_vram(999_999))

    def test_telemetry_vram_consistency(self):
        """free + used should approximately equal total (within rounding)."""
        telem = self.detector.telemetry()
        diff = abs(telem.total_vram_mib - (telem.free_vram_mib + telem.used_vram_mib))
        # Allow up to 1 MiB rounding difference
        self.assertLessEqual(diff, 1, f"VRAM inconsistency: {telem}")

    def test_context_manager_cleans_up(self):
        from worker.gpu.detector import GPUDetector
        with GPUDetector(gpu_id=0) as det:
            info = det.detect()
            self.assertGreater(info.total_vram_mib, 0)
        self.assertFalse(det._initialized)

    def test_multiple_telemetry_calls_stable(self):
        """Multiple rapid calls should not crash."""
        for _ in range(5):
            telem = self.detector.telemetry()
            self.assertIsNotNone(telem)


@unittest.skipUnless(_nvml_available(), "No NVIDIA GPU / pynvml not available")
class TestCUDAExecutorIntegration(unittest.TestCase):
    """
    Live CUDA workload tests.
    Skipped if PyTorch is not installed or CUDA is not available.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import torch
            if not torch.cuda.is_available():
                raise unittest.SkipTest("CUDA not available (torch installed but no CUDA)")
        except ImportError:
            raise unittest.SkipTest("PyTorch not installed")

    def setUp(self):
        from worker.executor.cuda_executor import CUDAExecutor
        self.executor = CUDAExecutor(gpu_id=0)

    def test_matrix_multiply_success(self):
        result = self.executor.execute({"type": "matrix_multiply", "dim": 256})
        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertGreater(result.execution_time_s, 0)
        self.assertIn("matrix_dim", result.output)
        self.assertEqual(result.output["matrix_dim"], 256)
        print(f"\n[CUDA] MatMul 256x256: {result.execution_time_s:.4f}s")

    def test_vector_add_success(self):
        result = self.executor.execute({"type": "vector_add", "length": 1_000_000})
        self.assertTrue(result.success)
        self.assertEqual(result.output["vector_length"], 1_000_000)
        print(f"\n[CUDA] VectorAdd 1M: {result.execution_time_s:.4f}s")

    def test_benchmark_success(self):
        result = self.executor.execute({"type": "benchmark", "dim": 512, "iterations": 3})
        self.assertTrue(result.success)
        self.assertIn("avg_time_ms", result.output)
        self.assertIn("gflops", result.output)
        print(f"\n[CUDA] Benchmark: {result.output['avg_time_ms']:.2f}ms avg, {result.output['gflops']} GFLOPS")

    def test_unsupported_type_raises(self):
        from worker.executor.cuda_executor import UnsupportedWorkloadError
        with self.assertRaises(UnsupportedWorkloadError):
            self.executor.execute({"type": "run_arbitrary_code"})

    def test_matrix_dim_clamped_at_max(self):
        """Oversized dim should be clamped, not crash."""
        result = self.executor.execute({"type": "matrix_multiply", "dim": 999_999})
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
