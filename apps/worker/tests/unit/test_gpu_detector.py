"""
TASK 11 — Unit tests: GPU detector (PyNVML mocked).

Tests cover:
  - GPUInfo / GPUTelemetry dataclasses
  - GPUDetector with mocked pynvml
  - has_free_vram logic
  - Error handling (NVMLError, no GPU found, bad GPU_ID)
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Build a minimal pynvml stub so tests run without real NVIDIA hardware
# ---------------------------------------------------------------------------

def _make_pynvml_stub():
    """Return a mock pynvml module with the minimal API surface."""
    stub = types.ModuleType("pynvml")

    # Constants
    stub.NVML_TEMPERATURE_GPU = 0

    # Exceptions
    class NVMLError(Exception):
        pass
    stub.NVMLError = NVMLError

    # Functions (default happy-path behaviour — overridable per test)
    stub.nvmlInit = MagicMock()
    stub.nvmlShutdown = MagicMock()
    stub.nvmlDeviceGetCount = MagicMock(return_value=1)
    stub.nvmlSystemGetDriverVersion = MagicMock(return_value="616.92")

    handle = MagicMock()
    stub.nvmlDeviceGetHandleByIndex = MagicMock(return_value=handle)
    stub.nvmlDeviceGetName = MagicMock(return_value="NVIDIA GeForce RTX 4050 Laptop GPU")
    stub.nvmlDeviceGetUUID = MagicMock(return_value="GPU-97b4586a-d808-bb73-0d97-d401a4357b6a")

    mem_info = MagicMock()
    mem_info.total = 6141 * 1024 * 1024
    mem_info.free  = 5000 * 1024 * 1024
    mem_info.used  = 1141 * 1024 * 1024
    stub.nvmlDeviceGetMemoryInfo = MagicMock(return_value=mem_info)

    util_info = MagicMock()
    util_info.gpu = 42
    stub.nvmlDeviceGetUtilizationRates = MagicMock(return_value=util_info)
    stub.nvmlDeviceGetTemperature = MagicMock(return_value=65)

    return stub, handle


class TestGPUInfo(unittest.TestCase):
    def test_to_dict_has_all_fields(self):
        from worker.gpu.detector import GPUInfo
        info = GPUInfo(
            gpu_id=0,
            name="RTX 4050",
            uuid="GPU-abc",
            total_vram_mib=6141,
            driver_version="616.92",
            cuda_available=True,
        )
        d = info.to_dict()
        for key in ("gpu_id", "name", "uuid", "total_vram_mib", "driver_version", "cuda_available"):
            self.assertIn(key, d)

    def test_frozen(self):
        from worker.gpu.detector import GPUInfo
        info = GPUInfo(
            gpu_id=0, name="X", uuid="Y", total_vram_mib=1,
            driver_version="1.0", cuda_available=False,
        )
        with self.assertRaises((AttributeError, TypeError)):
            info.name = "Z"  # type: ignore[misc]


class TestGPUTelemetry(unittest.TestCase):
    def test_vram_used_pct(self):
        from worker.gpu.detector import GPUTelemetry
        t = GPUTelemetry(
            gpu_id=0, name="X", uuid="Y",
            total_vram_mib=6000, free_vram_mib=4000, used_vram_mib=2000,
            gpu_utilization_pct=50.0, temperature_c=60.0,
            driver_version="1.0", cuda_available=True,
        )
        self.assertAlmostEqual(t.vram_used_pct, 33.33, places=1)

    def test_vram_used_pct_zero_total(self):
        from worker.gpu.detector import GPUTelemetry
        t = GPUTelemetry(
            gpu_id=0, name="X", uuid="Y",
            total_vram_mib=0, free_vram_mib=0, used_vram_mib=0,
            gpu_utilization_pct=0.0, temperature_c=0.0,
            driver_version="1.0", cuda_available=False,
        )
        self.assertEqual(t.vram_used_pct, 0.0)

    def test_to_dict_has_all_required_keys(self):
        from worker.gpu.detector import GPUTelemetry
        t = GPUTelemetry(
            gpu_id=0, name="X", uuid="Y",
            total_vram_mib=6141, free_vram_mib=5000, used_vram_mib=1141,
            gpu_utilization_pct=42.0, temperature_c=65.0,
            driver_version="616.92", cuda_available=True,
        )
        d = t.to_dict()
        expected = {
            "gpu_id", "name", "uuid", "total_vram_mib", "free_vram_mib",
            "used_vram_mib", "gpu_utilization_pct", "vram_used_pct",
            "temperature_c", "driver_version", "cuda_available",
        }
        self.assertEqual(expected, set(d.keys()))


class TestGPUDetector(unittest.TestCase):
    """All pynvml calls are mocked — no real GPU required."""

    def setUp(self):
        self.stub, self.handle = _make_pynvml_stub()
        # Inject stub into sys.modules before importing detector
        sys.modules["pynvml"] = self.stub

    def tearDown(self):
        sys.modules.pop("pynvml", None)

    def _make_detector(self, gpu_id: int = 0):
        # Re-import to pick up the patched pynvml
        import importlib
        import worker.gpu.detector as mod
        importlib.reload(mod)
        return mod.GPUDetector(gpu_id=gpu_id)

    def test_detect_returns_gpuinfo(self):
        det = self._make_detector()
        det.initialize()
        info = det.detect()
        from worker.gpu.detector import GPUInfo
        self.assertIsInstance(info, GPUInfo)
        self.assertEqual(info.name, "NVIDIA GeForce RTX 4050 Laptop GPU")
        self.assertEqual(info.total_vram_mib, 6141)
        self.assertEqual(info.driver_version, "616.92")

    def test_detect_uuid(self):
        det = self._make_detector()
        det.initialize()
        info = det.detect()
        self.assertEqual(info.uuid, "GPU-97b4586a-d808-bb73-0d97-d401a4357b6a")

    def test_telemetry_returns_gputelemetry(self):
        det = self._make_detector()
        det.initialize()
        telem = det.telemetry()
        from worker.gpu.detector import GPUTelemetry
        self.assertIsInstance(telem, GPUTelemetry)
        self.assertEqual(telem.free_vram_mib, 5000)
        self.assertEqual(telem.used_vram_mib, 1141)
        self.assertEqual(telem.gpu_utilization_pct, 42.0)
        self.assertEqual(telem.temperature_c, 65.0)

    def test_has_free_vram_sufficient(self):
        det = self._make_detector()
        det.initialize()
        self.assertTrue(det.has_free_vram(1000))   # 5000 free, need 1000

    def test_has_free_vram_insufficient(self):
        det = self._make_detector()
        det.initialize()
        self.assertFalse(det.has_free_vram(9999))  # 5000 free, need 9999

    def test_invalid_gpu_id_raises(self):
        self.stub.nvmlDeviceGetCount = MagicMock(return_value=1)
        det = self._make_detector(gpu_id=5)  # only gpu 0 exists
        import worker.gpu.detector as mod
        import importlib; importlib.reload(mod)
        det2 = mod.GPUDetector(gpu_id=5)
        with self.assertRaises(mod.GPUDetectionError):
            det2.initialize()

    def test_nvmlinit_failure_raises(self):
        import importlib
        import worker.gpu.detector as mod
        importlib.reload(mod)
        self.stub.nvmlInit.side_effect = self.stub.NVMLError("Init failed")
        det = mod.GPUDetector(gpu_id=0)
        with self.assertRaises(mod.GPUDetectionError):
            det.initialize()

    def test_context_manager(self):
        import importlib
        import worker.gpu.detector as mod
        importlib.reload(mod)
        with mod.GPUDetector(gpu_id=0) as det:
            info = det.detect()
            self.assertIsNotNone(info)
        self.assertFalse(det._initialized)

    def test_nvml_not_installed_raises(self):
        """Simulate pynvml not being installed at all."""
        import importlib
        saved = sys.modules.pop("pynvml", None)
        try:
            import worker.gpu.detector as mod
            # Patch _PYNVML_AVAILABLE to False
            mod._PYNVML_AVAILABLE = False
            det = mod.GPUDetector(gpu_id=0)
            with self.assertRaises(mod.GPUDetectionError):
                det.initialize()
        finally:
            if saved is not None:
                sys.modules["pynvml"] = saved
            importlib.reload(mod)

    def test_memory_info_nvml_error_returns_zeros(self):
        self.stub.nvmlDeviceGetMemoryInfo.side_effect = self.stub.NVMLError("mem err")
        det = self._make_detector()
        det.initialize()
        telem = det.telemetry()
        self.assertEqual(telem.total_vram_mib, 0)

    def test_utilization_nvml_error_returns_minus_one(self):
        self.stub.nvmlDeviceGetUtilizationRates.side_effect = self.stub.NVMLError("util err")
        det = self._make_detector()
        det.initialize()
        telem = det.telemetry()
        self.assertEqual(telem.gpu_utilization_pct, -1.0)

    def test_temperature_nvml_error_returns_minus_one(self):
        self.stub.nvmlDeviceGetTemperature.side_effect = self.stub.NVMLError("temp err")
        det = self._make_detector()
        det.initialize()
        telem = det.telemetry()
        self.assertEqual(telem.temperature_c, -1.0)


if __name__ == "__main__":
    unittest.main()
