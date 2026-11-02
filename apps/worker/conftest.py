"""
pytest conftest.py — shared fixtures for all test suites.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Shared pynvml stub factory (used by unit tests that need GPU mocking)
# ---------------------------------------------------------------------------

def make_pynvml_stub(
    gpu_count: int = 1,
    gpu_name: str = "NVIDIA GeForce RTX 4050 Laptop GPU",
    gpu_uuid: str = "GPU-97b4586a-d808-bb73-0d97-d401a4357b6a",
    total_mib: int = 6141,
    free_mib: int = 5000,
    used_mib: int = 1141,
    utilization: int = 42,
    temperature: int = 65,
    driver_version: str = "616.92",
) -> types.ModuleType:
    """Return a fully configured pynvml stub module."""
    stub = types.ModuleType("pynvml")
    stub.NVML_TEMPERATURE_GPU = 0

    class NVMLError(Exception):
        pass

    stub.NVMLError = NVMLError
    stub.nvmlInit = MagicMock()
    stub.nvmlShutdown = MagicMock()
    stub.nvmlDeviceGetCount = MagicMock(return_value=gpu_count)
    stub.nvmlSystemGetDriverVersion = MagicMock(return_value=driver_version)

    handle = MagicMock()
    stub.nvmlDeviceGetHandleByIndex = MagicMock(return_value=handle)
    stub.nvmlDeviceGetName = MagicMock(return_value=gpu_name)
    stub.nvmlDeviceGetUUID = MagicMock(return_value=gpu_uuid)

    mem_info = MagicMock()
    mem_info.total = total_mib * 1024 * 1024
    mem_info.free = free_mib * 1024 * 1024
    mem_info.used = used_mib * 1024 * 1024
    stub.nvmlDeviceGetMemoryInfo = MagicMock(return_value=mem_info)

    util_info = MagicMock()
    util_info.gpu = utilization
    stub.nvmlDeviceGetUtilizationRates = MagicMock(return_value=util_info)
    stub.nvmlDeviceGetTemperature = MagicMock(return_value=temperature)

    return stub


@pytest.fixture()
def pynvml_stub():
    """Inject a pynvml stub and clean up after the test."""
    stub = make_pynvml_stub()
    sys.modules["pynvml"] = stub
    yield stub
    sys.modules.pop("pynvml", None)


@pytest.fixture()
def worker_config():
    """Return a WorkerConfig built from test env vars."""
    saved = {}
    test_env = {
        "WORKER_ID": "test-worker-01",
        "COORDINATOR_URL": "http://coordinator.test:8000",
        "GPU_ID": "0",
        "HEARTBEAT_INTERVAL": "10",
    }
    for k in test_env:
        saved[k] = os.environ.get(k)
        os.environ[k] = test_env[k]

    from worker.config import WorkerConfig
    cfg = WorkerConfig.from_env()

    yield cfg

    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture()
def state_machine_available():
    """Return a WorkerStateMachine already in AVAILABLE state."""
    from worker.state import WorkerState, WorkerStateMachine
    sm = WorkerStateMachine()
    sm.transition(WorkerState.AVAILABLE)
    return sm
