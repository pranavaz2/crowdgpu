"""
TASK 1 — GPU Detection via PyNVML.

Detects the local NVIDIA GPU and collects full telemetry:
  - GPU name, UUID, total/free/used VRAM
  - GPU utilisation %, temperature
  - driver version, CUDA availability
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Optional

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        import pynvml
    _PYNVML_AVAILABLE = True
except ImportError:
    _PYNVML_AVAILABLE = False

logger = logging.getLogger(__name__)


class GPUDetectionError(RuntimeError):
    """Raised when GPU detection fails."""


@dataclass(frozen=True)
class GPUInfo:
    """Static GPU hardware information collected at startup."""

    gpu_id: int
    name: str
    uuid: str
    total_vram_mib: int
    driver_version: str
    cuda_available: bool

    def to_dict(self) -> dict:
        return {
            "gpu_id": self.gpu_id,
            "name": self.name,
            "uuid": self.uuid,
            "total_vram_mib": self.total_vram_mib,
            "driver_version": self.driver_version,
            "cuda_available": self.cuda_available,
        }


@dataclass
class GPUTelemetry:
    """Live GPU metrics collected during heartbeat cycles."""

    gpu_id: int
    name: str
    uuid: str
    total_vram_mib: int
    free_vram_mib: int
    used_vram_mib: int
    gpu_utilization_pct: float
    temperature_c: float
    driver_version: str
    cuda_available: bool

    @property
    def vram_used_pct(self) -> float:
        if self.total_vram_mib == 0:
            return 0.0
        return round(self.used_vram_mib / self.total_vram_mib * 100, 2)

    def to_dict(self) -> dict:
        return {
            "gpu_id": self.gpu_id,
            "name": self.name,
            "uuid": self.uuid,
            "total_vram_mib": self.total_vram_mib,
            "free_vram_mib": self.free_vram_mib,
            "used_vram_mib": self.used_vram_mib,
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "vram_used_pct": self.vram_used_pct,
            "temperature_c": self.temperature_c,
            "driver_version": self.driver_version,
            "cuda_available": self.cuda_available,
        }


class GPUDetector:
    """
    Detects and queries NVIDIA GPUs via PyNVML.

    Usage::

        detector = GPUDetector(gpu_id=0)
        info = detector.detect()        # static info — call once
        telemetry = detector.telemetry()  # live stats — call every heartbeat
        detector.shutdown()
    """

    def __init__(self, gpu_id: int = 0) -> None:
        self._gpu_id = gpu_id
        self._handle: Optional[object] = None
        self._initialized = False
        self._driver_version: str = "unknown"
        self._cuda_available: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Initialize PyNVML and open a handle to the target GPU."""
        if not _PYNVML_AVAILABLE:
            raise GPUDetectionError(
                "pynvml is not installed. Run: pip install pynvml"
            )
        try:
            pynvml.nvmlInit()
        except pynvml.NVMLError as exc:
            raise GPUDetectionError(f"nvmlInit() failed: {exc}") from exc

        device_count = pynvml.nvmlDeviceGetCount()
        if self._gpu_id >= device_count:
            pynvml.nvmlShutdown()
            raise GPUDetectionError(
                f"GPU ID {self._gpu_id} not found. "
                f"System has {device_count} GPU(s) (0-{device_count - 1})."
            )

        self._handle = pynvml.nvmlDeviceGetHandleByIndex(self._gpu_id)

        try:
            self._driver_version = pynvml.nvmlSystemGetDriverVersion()
        except pynvml.NVMLError:
            self._driver_version = "unknown"

        self._cuda_available = self._check_cuda()
        self._initialized = True
        logger.info(
            "GPUDetector initialised — GPU %d, driver %s, CUDA=%s",
            self._gpu_id,
            self._driver_version,
            self._cuda_available,
        )

    def shutdown(self) -> None:
        """Shut down PyNVML cleanly."""
        if self._initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:  # noqa: BLE001
                pass
            self._initialized = False
            self._handle = None

    def __enter__(self) -> "GPUDetector":
        self.initialize()
        return self

    def __exit__(self, *_: object) -> None:
        self.shutdown()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self) -> GPUInfo:
        """Return static GPU hardware info. Initialises if needed."""
        if not self._initialized:
            self.initialize()
        self._require_handle()

        name = self._safe_call(
            pynvml.nvmlDeviceGetName, self._handle, default="Unknown GPU"
        )
        uuid = self._safe_call(
            pynvml.nvmlDeviceGetUUID, self._handle, default="unknown-uuid"
        )
        mem = self._get_memory_info()

        info = GPUInfo(
            gpu_id=self._gpu_id,
            name=name,
            uuid=uuid,
            total_vram_mib=mem["total"],
            driver_version=self._driver_version,
            cuda_available=self._cuda_available,
        )
        logger.info("GPU detected: %s — %d MiB VRAM", info.name, info.total_vram_mib)
        return info

    def telemetry(self) -> GPUTelemetry:
        """Return live GPU metrics. Initialises if needed."""
        if not self._initialized:
            self.initialize()
        self._require_handle()

        name = self._safe_call(
            pynvml.nvmlDeviceGetName, self._handle, default="Unknown GPU"
        )
        uuid = self._safe_call(
            pynvml.nvmlDeviceGetUUID, self._handle, default="unknown-uuid"
        )
        mem = self._get_memory_info()
        utilization = self._get_utilization()
        temperature = self._get_temperature()

        return GPUTelemetry(
            gpu_id=self._gpu_id,
            name=name,
            uuid=uuid,
            total_vram_mib=mem["total"],
            free_vram_mib=mem["free"],
            used_vram_mib=mem["used"],
            gpu_utilization_pct=utilization,
            temperature_c=temperature,
            driver_version=self._driver_version,
            cuda_available=self._cuda_available,
        )

    def has_free_vram(self, required_mib: int) -> bool:
        """Return True if there is at least *required_mib* MiB of free VRAM."""
        telem = self.telemetry()
        has = telem.free_vram_mib >= required_mib
        logger.debug(
            "VRAM check: need %d MiB, have %d MiB free → %s",
            required_mib,
            telem.free_vram_mib,
            has,
        )
        return has

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_handle(self) -> None:
        if self._handle is None:
            raise GPUDetectionError("GPU handle is not open — call initialize() first.")

    def _get_memory_info(self) -> dict:
        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            mib = 1024 * 1024
            return {
                "total": int(mem.total / mib),
                "free": int(mem.free / mib),
                "used": int(mem.used / mib),
            }
        except pynvml.NVMLError as exc:
            logger.warning("Memory info unavailable: %s", exc)
            return {"total": 0, "free": 0, "used": 0}

    def _get_utilization(self) -> float:
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
            return float(util.gpu)
        except pynvml.NVMLError as exc:
            logger.warning("Utilization unavailable: %s", exc)
            return -1.0

    def _get_temperature(self) -> float:
        try:
            return float(
                pynvml.nvmlDeviceGetTemperature(
                    self._handle, pynvml.NVML_TEMPERATURE_GPU
                )
            )
        except pynvml.NVMLError as exc:
            logger.warning("Temperature unavailable: %s", exc)
            return -1.0

    @staticmethod
    def _check_cuda() -> bool:
        """Return True if PyTorch CUDA is available (non-blocking)."""
        try:
            import torch  # noqa: PLC0415
            return torch.cuda.is_available()
        except ImportError:
            return False  # torch not installed — CUDA status unknown

    @staticmethod
    def _safe_call(fn: callable, *args, default: str = "") -> str:
        """Call a PyNVML function; return *default* on NVMLError."""
        try:
            result = fn(*args)
            # pynvml may return bytes on some versions
            if isinstance(result, bytes):
                return result.decode("utf-8", errors="replace")
            return str(result)
        except Exception:  # noqa: BLE001
            return default
