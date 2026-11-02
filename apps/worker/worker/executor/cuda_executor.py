"""
TASK 6 — GPU availability / VRAM checks.
TASK 7 — Safe, controlled PyTorch CUDA workload executor.

SAFETY RULE: This executor only runs a built-in, hard-coded, controlled
workload.  It NEVER executes arbitrary user-supplied Python code, eval(),
exec(), shell commands, or downloaded scripts.

Supported workload types (task "type" field):
  - "matrix_multiply"  — torch.mm on configurable matrix sizes
  - "vector_add"       — element-wise addition on configurable vector size
  - "benchmark"        — time a CUDA synchronised MATMUL loop

Unknown types are rejected with an InvalidJobError.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CUDAExecutionError(RuntimeError):
    """Raised when the CUDA workload fails."""


class InsufficientVRAMError(CUDAExecutionError):
    """Raised when there is not enough free VRAM for the requested workload."""


class UnsupportedWorkloadError(CUDAExecutionError):
    """Raised when the workload type is not in the allowlist."""


# ---------------------------------------------------------------------------
# TASK 6 — VRAM guard
# ---------------------------------------------------------------------------

def check_vram(
    free_vram_mib: int,
    required_vram_mib: int,
    safety_margin_mib: int = 256,
) -> None:
    """
    Raise InsufficientVRAMError if free VRAM - safety_margin < required.

    Args:
        free_vram_mib:    Current free VRAM reported by PyNVML.
        required_vram_mib: VRAM the workload expects to consume.
        safety_margin_mib: Reserve to keep free for driver/OS use.
    """
    available = free_vram_mib - safety_margin_mib
    if required_vram_mib > available:
        raise InsufficientVRAMError(
            f"Insufficient VRAM: job requires {required_vram_mib} MiB, "
            f"only {available} MiB available after {safety_margin_mib} MiB safety margin "
            f"(free={free_vram_mib} MiB)."
        )
    logger.debug(
        "VRAM OK: %d MiB required, %d MiB available (after %d MiB margin)",
        required_vram_mib,
        available,
        safety_margin_mib,
    )


# ---------------------------------------------------------------------------
# TASK 7 — PyTorch CUDA executor
# ---------------------------------------------------------------------------

# Allowlist of safe, controlled workload types.
# Extend this set to add new built-in workloads; never allow user strings.
_ALLOWED_WORKLOAD_TYPES = frozenset({
    "matrix_multiply",
    "vector_add",
    "benchmark",
})

# Maximum safe dimensions to prevent OOM / runaway computation
_MAX_MATRIX_DIM = 16_384
_MAX_VECTOR_LEN = 100_000_000  # 100M elements × 4 bytes ≈ 400 MiB fp32


@dataclass
class CUDAResult:
    """Result of a CUDA workload execution."""

    workload_type: str
    device: str
    execution_time_s: float
    output: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workload_type": self.workload_type,
            "device": self.device,
            "execution_time_s": self.execution_time_s,
            "output": self.output,
            "success": self.success,
            "error": self.error,
        }


class CUDAExecutor:
    """
    Executes a hard-coded, allow-listed PyTorch CUDA workload.

    >>> executor = CUDAExecutor(gpu_id=0)
    >>> result = executor.execute({"type": "matrix_multiply", "dim": 1024})
    """

    def __init__(self, gpu_id: int = 0) -> None:
        self._gpu_id = gpu_id
        self._device_str = f"cuda:{gpu_id}"

    # ------------------------------------------------------------------
    # Public execute — validates, dispatches, times
    # ------------------------------------------------------------------

    def execute(self, params: Dict[str, Any]) -> CUDAResult:
        """
        Validate *params* and execute the requested CUDA workload.

        Parameters
        ----------
        params : dict
            Must contain ``"type"`` key from the allowlist.
            Other keys depend on workload type (see each _run_* method).

        Returns
        -------
        CUDAResult with timing and output.
        """
        import torch  # deferred import — torch may not be installed

        workload_type = params.get("type", "")
        if workload_type not in _ALLOWED_WORKLOAD_TYPES:
            raise UnsupportedWorkloadError(
                f"Workload type {workload_type!r} is not allowed. "
                f"Allowed types: {sorted(_ALLOWED_WORKLOAD_TYPES)}"
            )

        if not torch.cuda.is_available():
            raise CUDAExecutionError(
                "CUDA is not available on this machine. "
                "Ensure PyTorch with CUDA support is installed."
            )

        device = torch.device(self._device_str)
        logger.info("Executing CUDA workload: type=%s device=%s", workload_type, device)

        start = time.perf_counter()
        try:
            if workload_type == "matrix_multiply":
                output = self._run_matrix_multiply(device, params)
            elif workload_type == "vector_add":
                output = self._run_vector_add(device, params)
            elif workload_type == "benchmark":
                output = self._run_benchmark(device, params)
            else:
                raise UnsupportedWorkloadError(f"Unhandled type: {workload_type}")
        except (UnsupportedWorkloadError, InsufficientVRAMError):
            raise
        except Exception as exc:
            elapsed = time.perf_counter() - start
            err_msg = f"CUDA execution failed: {type(exc).__name__}: {exc}"
            logger.error(err_msg)
            return CUDAResult(
                workload_type=workload_type,
                device=str(device),
                execution_time_s=elapsed,
                success=False,
                error=err_msg,
            )

        elapsed = time.perf_counter() - start
        logger.info(
            "CUDA workload done: type=%s elapsed=%.4fs", workload_type, elapsed
        )
        return CUDAResult(
            workload_type=workload_type,
            device=str(device),
            execution_time_s=elapsed,
            output=output,
        )

    # ------------------------------------------------------------------
    # Workload implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _run_matrix_multiply(
        device: "torch.device", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Multiply two random square matrices of size *dim × dim* on the GPU.

        params:
          dim (int, default 1024): matrix dimension, capped at _MAX_MATRIX_DIM
        """
        import torch

        dim = min(int(params.get("dim", 1024)), _MAX_MATRIX_DIM)
        dtype = torch.float32

        a = torch.randn(dim, dim, device=device, dtype=dtype)
        b = torch.randn(dim, dim, device=device, dtype=dtype)
        c = torch.mm(a, b)
        torch.cuda.synchronize(device)

        return {
            "matrix_dim": dim,
            "result_shape": list(c.shape),
            "result_mean": float(c.mean().item()),
            "result_std": float(c.std().item()),
        }

    @staticmethod
    def _run_vector_add(
        device: "torch.device", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Element-wise addition of two random float32 vectors.

        params:
          length (int, default 10_000_000): vector length
        """
        import torch

        length = min(int(params.get("length", 10_000_000)), _MAX_VECTOR_LEN)

        a = torch.randn(length, device=device, dtype=torch.float32)
        b = torch.randn(length, device=device, dtype=torch.float32)
        c = a + b
        torch.cuda.synchronize(device)

        return {
            "vector_length": length,
            "result_mean": float(c.mean().item()),
            "result_std": float(c.std().item()),
        }

    @staticmethod
    def _run_benchmark(
        device: "torch.device", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Timed MATMUL benchmark over *iterations* iterations.

        params:
          dim (int, default 2048): matrix dimension
          iterations (int, default 10): number of MATMUL iterations
        """
        import torch

        dim = min(int(params.get("dim", 2048)), _MAX_MATRIX_DIM)
        iterations = min(int(params.get("iterations", 10)), 100)

        # warm-up
        a = torch.randn(dim, dim, device=device, dtype=torch.float32)
        b = torch.randn(dim, dim, device=device, dtype=torch.float32)
        _ = torch.mm(a, b)
        torch.cuda.synchronize(device)

        # timed run
        lap_times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            c = torch.mm(a, b)
            torch.cuda.synchronize(device)
            lap_times.append(time.perf_counter() - t0)

        avg_ms = (sum(lap_times) / len(lap_times)) * 1000
        gflops = (2 * dim ** 3) / (avg_ms / 1000) / 1e9

        return {
            "matrix_dim": dim,
            "iterations": iterations,
            "avg_time_ms": round(avg_ms, 3),
            "gflops": round(gflops, 2),
        }
