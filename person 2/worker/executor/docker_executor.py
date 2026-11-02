"""
TASK 10 — Docker GPU execution.

DockerGPUExecutor runs untrusted workloads inside an NVIDIA-GPU-enabled
Docker container using the NVIDIA Container Toolkit.

SAFETY: This is the ONLY safe way to run untrusted user-provided code.
        Never use CUDAExecutor for untrusted payloads.

Prerequisites:
  - Docker daemon running
  - nvidia-container-toolkit installed
  - Base image with CUDA available (e.g. nvidia/cuda:12.x-base-ubuntu22.04)

This implementation requires the ``docker`` Python SDK:
  pip install docker

The DockerGPUExecutor:
  1. Receives a job dict with "docker_image" and "command" fields
  2. Validates both against an allowlist (image prefix and command allowlist)
  3. Pulls the image if not already cached
  4. Runs the container with GPU access via device_requests
  5. Captures stdout/stderr and exit code
  6. Returns a CUDAResult-compatible dict
  7. Always removes the container on completion
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowlists — MUST be customised before enabling Docker execution
# ---------------------------------------------------------------------------

# Only images from these trusted registries are permitted.
# Add specific images as needed; wildcards are NOT supported.
ALLOWED_IMAGE_PREFIXES: List[str] = [
    "nvidia/cuda:",
    "pytorch/pytorch:",
    "nvcr.io/nvidia/",
]

# Only these exact commands are allowed when using Docker execution.
# For MVP: an empty list means Docker execution is disabled by default.
ALLOWED_COMMANDS: List[str] = [
    "python -c \"import torch; print(torch.cuda.is_available())\"",
    "nvidia-smi",
]

# Container resource limits
_DEFAULT_MEM_LIMIT = "4g"
_DEFAULT_TIMEOUT_S = 300  # 5 minutes max


class DockerExecutionError(RuntimeError):
    """Raised when Docker GPU execution fails."""


class DockerNotAvailableError(DockerExecutionError):
    """Raised when Docker daemon or nvidia-container-toolkit is missing."""


class DockerImageNotAllowedError(DockerExecutionError):
    """Raised when the requested image is not in the allowlist."""


class DockerCommandNotAllowedError(DockerExecutionError):
    """Raised when the requested command is not in the allowlist."""


@dataclass
class DockerResult:
    """Result of a Docker GPU execution."""

    image: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    execution_time_s: float
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image": self.image,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time_s": self.execution_time_s,
            "success": self.success,
            "error": self.error,
        }


class DockerGPUExecutor:
    """
    Runs GPU workloads inside a Docker container with NVIDIA runtime.

    This is the recommended path for UNTRUSTED workloads.

    Usage::

        executor = DockerGPUExecutor(gpu_id=0)
        result = executor.execute({
            "docker_image": "nvidia/cuda:12.1-base-ubuntu22.04",
            "command": "nvidia-smi",
        })
    """

    def __init__(
        self,
        gpu_id: int = 0,
        mem_limit: str = _DEFAULT_MEM_LIMIT,
        timeout_s: int = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._gpu_id = gpu_id
        self._mem_limit = mem_limit
        self._timeout_s = timeout_s
        self._client = None  # lazy-init docker client

    def _get_client(self):
        if self._client is None:
            try:
                import docker  # noqa: PLC0415
                self._client = docker.from_env()
                self._client.ping()
            except ImportError:
                raise DockerNotAvailableError(
                    "docker SDK not installed. Run: pip install docker"
                )
            except Exception as exc:
                raise DockerNotAvailableError(
                    f"Docker daemon not reachable: {exc}"
                ) from exc
        return self._client

    def _validate_image(self, image: str) -> None:
        """Reject images not in the trusted prefix list."""
        for prefix in ALLOWED_IMAGE_PREFIXES:
            if image.startswith(prefix):
                return
        raise DockerImageNotAllowedError(
            f"Image {image!r} is not in the allowed list. "
            f"Allowed prefixes: {ALLOWED_IMAGE_PREFIXES}"
        )

    def _validate_command(self, command: str) -> None:
        """Reject commands not in the exact allowlist."""
        if command not in ALLOWED_COMMANDS:
            raise DockerCommandNotAllowedError(
                f"Command {command!r} is not in the allowed commands list. "
                f"Allowed: {ALLOWED_COMMANDS}"
            )

    def execute(self, params: Dict[str, Any]) -> DockerResult:
        """
        Validate and run a Docker GPU container.

        params must contain:
          - ``docker_image`` (str): container image name (allowlist-checked)
          - ``command``      (str): shell command to run (allowlist-checked)

        Optional:
          - ``mem_limit`` (str): memory limit (e.g. "4g")
          - ``timeout_s`` (int): max execution seconds
        """
        image = params.get("docker_image", "")
        command = params.get("command", "")

        self._validate_image(image)
        self._validate_command(command)

        mem_limit = params.get("mem_limit", self._mem_limit)
        timeout_s = int(params.get("timeout_s", self._timeout_s))

        client = self._get_client()
        start = time.perf_counter()
        container = None

        logger.info(
            "Starting Docker container: image=%s command=%r gpu=%d",
            image,
            command,
            self._gpu_id,
        )
        try:
            container = client.containers.run(
                image=image,
                command=command,
                detach=True,
                mem_limit=mem_limit,
                device_requests=[
                    {
                        "driver": "nvidia",
                        "count": 1,
                        "device_ids": [str(self._gpu_id)],
                        "capabilities": [["gpu"]],
                    }
                ],
                network_disabled=True,  # no outbound network from container
                read_only=True,         # read-only root filesystem
                remove=False,           # we remove manually after log capture
            )

            try:
                exit_code = container.wait(timeout=timeout_s)["StatusCode"]
            except Exception as exc:
                container.kill()
                elapsed = time.perf_counter() - start
                return DockerResult(
                    image=image,
                    command=command,
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    execution_time_s=elapsed,
                    success=False,
                    error=f"Container timeout/error: {exc}",
                )

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            elapsed = time.perf_counter() - start

            logger.info(
                "Container finished: exit_code=%d elapsed=%.2fs", exit_code, elapsed
            )
            return DockerResult(
                image=image,
                command=command,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                execution_time_s=elapsed,
                success=(exit_code == 0),
                error=stderr if exit_code != 0 else None,
            )

        except (DockerImageNotAllowedError, DockerCommandNotAllowedError):
            raise
        except Exception as exc:
            elapsed = time.perf_counter() - start
            err_msg = f"Docker execution error: {type(exc).__name__}: {exc}"
            logger.error(err_msg)
            return DockerResult(
                image=image,
                command=command,
                exit_code=-1,
                stdout="",
                stderr="",
                execution_time_s=elapsed,
                success=False,
                error=err_msg,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
