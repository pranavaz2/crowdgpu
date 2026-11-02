"""
CrowdGPU Worker — MVP Demo Script

Demonstrates the full worker flow WITHOUT requiring a running Coordinator.
All Coordinator HTTP calls are intercepted and printed instead.

Run:
    python demo_mvp.py

What you'll see:
    ✅ GPU detected (real PyNVML call to your GPU)
    ✅ Registration payload printed (what would be sent to Coordinator)
    ✅ Heartbeat telemetry printed (live GPU metrics)
    ✅ Job validated and accepted
    ✅ VRAM checked (real free VRAM vs job requirement)
    ✅ State transitions: STARTING → AVAILABLE → BUSY → AVAILABLE
    ✅ Job execution result (PyTorch or stubbed if torch not installed)
    ✅ Result payload printed (what would be sent to Coordinator)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from unittest.mock import MagicMock

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

# --------------------------------------------------------------------------
# Logging setup
# --------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("demo")

SEP = "-" * 60


def section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


# --------------------------------------------------------------------------
# Step 0 — Configuration
# --------------------------------------------------------------------------

section("STEP 0 — Configuration")

os.environ.setdefault("COORDINATOR_URL", "http://coordinator.demo:8000")
os.environ.setdefault("WORKER_ID", "demo-worker-01")
os.environ.setdefault("GPU_ID", "0")
os.environ.setdefault("HEARTBEAT_INTERVAL", "60")

from worker.config import WorkerConfig  # noqa: E402

config = WorkerConfig.from_env()
print(config)

# --------------------------------------------------------------------------
# Step 1 — GPU Detection (REAL PyNVML call)
# --------------------------------------------------------------------------

section("STEP 1 — GPU Detection (live PyNVML)")

from worker.gpu.detector import GPUDetector, GPUDetectionError  # noqa: E402

try:
    detector = GPUDetector(gpu_id=config.gpu_id)
    detector.initialize()
    gpu_info = detector.detect()
    print(f"  GPU Name        : {gpu_info.name}")
    print(f"  GPU UUID        : {gpu_info.uuid}")
    print(f"  Total VRAM      : {gpu_info.total_vram_mib} MiB")
    print(f"  Driver Version  : {gpu_info.driver_version}")
    print(f"  CUDA Available  : {gpu_info.cuda_available}")
    print("\n  ✅ GPU detection successful")
except GPUDetectionError as e:
    print(f"  ❌ GPU detection failed: {e}")
    print("  → Is an NVIDIA GPU present and PyNVML installed?")
    sys.exit(1)

# --------------------------------------------------------------------------
# Step 2 — Live Telemetry (REAL PyNVML call)
# --------------------------------------------------------------------------

section("STEP 2 — Live GPU Telemetry")

telem = detector.telemetry()
print(json.dumps(telem.to_dict(), indent=4))

# --------------------------------------------------------------------------
# Step 3 — Coordinator Registration (intercepted — no real HTTP)
# --------------------------------------------------------------------------

section("STEP 3 — Coordinator Registration (intercepted)")

from worker.coordinator.client import CoordinatorClient  # noqa: E402

coordinator = MagicMock(spec=CoordinatorClient)
coordinator.register.return_value = {"status": "registered", "worker_id": config.worker_id}

registration_payload = {
    "worker_id": config.worker_id,
    "gpu_name": gpu_info.name,
    "gpu_uuid": gpu_info.uuid,
    "total_vram_mib": gpu_info.total_vram_mib,
    "driver_version": gpu_info.driver_version,
    "cuda_available": gpu_info.cuda_available,
    "gpu_id": gpu_info.gpu_id,
}
print(f"  Would POST to: {config.api_url('api/v1/workers/register')}")
print("  Payload:")
print(json.dumps(registration_payload, indent=4))
print("\n  ✅ Registration intercepted (Coordinator mock)")

# --------------------------------------------------------------------------
# Step 4 — State machine: STARTING → AVAILABLE
# --------------------------------------------------------------------------

section("STEP 4 — Worker State Machine")

from worker.state import WorkerState, WorkerStateMachine  # noqa: E402

sm = WorkerStateMachine()
print(f"  Initial state : {sm.state.value}")
sm.transition(WorkerState.AVAILABLE)
print(f"  After start   : {sm.state.value}  (STARTING → AVAILABLE)")
print(f"  is_available()  : {sm.is_available()}")
print(f"  can → BUSY    : {sm.can_transition(WorkerState.BUSY)}")

# --------------------------------------------------------------------------
# Step 5 — Heartbeat (intercepted)
# --------------------------------------------------------------------------

section("STEP 5 — Heartbeat / Telemetry (intercepted)")

heartbeat_payload = {
    "state": sm.state.value,
    "current_job_id": None,
    "gpu_telemetry": {
        "free_vram_mib": telem.free_vram_mib,
        "used_vram_mib": telem.used_vram_mib,
        "total_vram_mib": telem.total_vram_mib,
        "gpu_utilization_pct": telem.gpu_utilization_pct,
        "temperature_c": telem.temperature_c,
        "cuda_available": telem.cuda_available,
    },
}
print(f"  Would POST to: {config.api_url(f'api/v1/workers/{config.worker_id}/heartbeat')}")
print("  Payload:")
print(json.dumps(heartbeat_payload, indent=4))

# --------------------------------------------------------------------------
# Step 6 — Job + VRAM check
# --------------------------------------------------------------------------

section("STEP 6 — Job Validation & VRAM Check")

sample_job = {
    "job_id": "demo-job-001",
    "type": "matrix_multiply",
    "dim": 512,
    "required_vram_mib": 200,
}
print("  Job payload:")
print(json.dumps(sample_job, indent=4))

from worker.executor.job_handler import validate_job  # noqa: E402
from worker.executor.cuda_executor import check_vram, InsufficientVRAMError  # noqa: E402

try:
    validate_job(sample_job)
    print("\n  ✅ Job schema valid")
except Exception as e:
    print(f"\n  ❌ Validation failed: {e}")

try:
    check_vram(
        free_vram_mib=telem.free_vram_mib,
        required_vram_mib=sample_job["required_vram_mib"],
        safety_margin_mib=256,
    )
    print(
        f"  ✅ VRAM OK: need {sample_job['required_vram_mib']} MiB, "
        f"have {telem.free_vram_mib - 256} MiB available (after 256 MiB margin)"
    )
except InsufficientVRAMError as e:
    print(f"  ❌ VRAM check failed: {e}")

# --------------------------------------------------------------------------
# Step 7 — State: AVAILABLE → BUSY
# --------------------------------------------------------------------------

section("STEP 7 — State: AVAILABLE → BUSY")

sm.transition(WorkerState.BUSY)
print(f"  State: {sm.state.value}")

# --------------------------------------------------------------------------
# Step 8 — CUDA Workload Execution
# --------------------------------------------------------------------------

section("STEP 8 — CUDA Workload Execution")

from worker.executor.cuda_executor import CUDAExecutor, CUDAResult  # noqa: E402

try:
    import torch
    if torch.cuda.is_available():
        print("  PyTorch CUDA is available — running real CUDA workload...")
        executor = CUDAExecutor(gpu_id=config.gpu_id)
        t0 = time.perf_counter()
        result = executor.execute(sample_job)
        elapsed = time.perf_counter() - t0
        print(f"  ✅ Workload complete in {elapsed:.4f}s")
        print(f"  Output: {json.dumps(result.output, indent=4)}")
    else:
        raise ImportError("CUDA not available")
except ImportError:
    print("  ⚠  PyTorch not installed or CUDA unavailable — using stub result")
    result = CUDAResult(
        workload_type="matrix_multiply",
        device="cuda:0 (stub)",
        execution_time_s=0.042,
        output={
            "matrix_dim": 512,
            "result_shape": [512, 512],
            "result_mean": 0.0001,
            "result_std": 22.6,
        },
        success=True,
    )
    print(f"  Stub result: {json.dumps(result.to_dict(), indent=4)}")

# --------------------------------------------------------------------------
# Step 9 — State: BUSY → AVAILABLE + result reporting
# --------------------------------------------------------------------------

section("STEP 9 — State: BUSY → AVAILABLE + Result Report")

sm.transition(WorkerState.AVAILABLE)
print(f"  State: {sm.state.value}")

result_payload = {
    "worker_id": config.worker_id,
    "status": "success" if result.success else "failed",
    "output": result.output,
    "execution_time_s": result.execution_time_s,
    "error": result.error,
}
job_id = sample_job["job_id"]
print(f"\n  Would POST to: {config.api_url(f'api/v1/jobs/{job_id}/result')}")
print("  Payload:")
print(json.dumps(result_payload, indent=4))
print("\n  ✅ Result reported (intercepted)")

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

section("MVP DEMO COMPLETE ✅")

print(
    f"""
  Worker ID  : {config.worker_id}
  GPU        : {gpu_info.name}
  VRAM total : {gpu_info.total_vram_mib} MiB  |  free: {telem.free_vram_mib} MiB
  Temp       : {telem.temperature_c}°C   |  util: {telem.gpu_utilization_pct}%
  Job        : {sample_job['job_id']} ({sample_job['type']})
  Job result : {'SUCCESS ✅' if result.success else 'FAILED ❌'}
  Exec time  : {result.execution_time_s:.4f}s
  Final state: {sm.state.value}

  Full MVP flow completed:
    STARTING → detected GPU → registered → AVAILABLE
    → received job → validated → VRAM OK → BUSY
    → executed workload → reported result → AVAILABLE
"""
)

detector.shutdown()
