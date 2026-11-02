"""
Supported workload definitions and presets.

Mirrors the frontend workload presets from SubmitJobPage.jsx so that CLI and
Web experiences share the exact same canonical computational task profiles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class WorkloadPreset:
    """Canonical workload preset definition."""

    type: str
    name: str
    description: str
    default_command: str
    default_vram_mb: int
    requires_docker_image: bool = False


WORKLOAD_PRESETS: Dict[str, WorkloadPreset] = {
    "matrix_multiply": WorkloadPreset(
        type="matrix_multiply",
        name="CUDA Matrix Multiplication",
        description="Runs PyTorch matrix multiplication on GPU with configurable dimension.",
        default_command="matrix_multiply",
        default_vram_mb=512,
    ),
    "vector_add": WorkloadPreset(
        type="vector_add",
        name="CUDA Vector Addition",
        description="Runs element-wise addition of 10M float32 vectors on GPU.",
        default_command="vector_add",
        default_vram_mb=256,
    ),
    "benchmark": WorkloadPreset(
        type="benchmark",
        name="CUDA MatMul Benchmark",
        description="Executes timed synchronized GPU MATMUL loops and computes GFLOPS.",
        default_command="benchmark",
        default_vram_mb=1024,
    ),
    "docker": WorkloadPreset(
        type="docker",
        name="Custom Container Job",
        description="Runs a container image in an isolated GPU sandbox environment.",
        default_command="python train.py --epochs 10",
        default_vram_mb=2048,
        requires_docker_image=True,
    ),
}


def resolve_workload(
    preset_name: str | None = None,
    name: str | None = None,
    workload_type: str | None = None,
    command: str | None = None,
    vram_mb: int | None = None,
    docker_image: str | None = None,
) -> dict[str, Any]:
    """
    Resolve and validate job parameters against canonical workload specifications.
    Ensures safe, structured parameters without executing any arbitrary shell scripts.
    """
    selected_preset: WorkloadPreset | None = None
    if preset_name:
        key = preset_name.lower().strip()
        if key not in WORKLOAD_PRESETS:
            raise ValueError(
                f"Unknown preset '{preset_name}'. Supported presets: {', '.join(WORKLOAD_PRESETS.keys())}"
            )
        selected_preset = WORKLOAD_PRESETS[key]

    final_type = workload_type or (selected_preset.type if selected_preset else "matrix_multiply")
    final_name = name or (selected_preset.name if selected_preset else f"GPU {final_type} Job")
    final_command = command or (selected_preset.default_command if selected_preset else final_type)
    final_vram = vram_mb if vram_mb is not None else (selected_preset.default_vram_mb if selected_preset else 512)
    final_docker = docker_image or None

    if final_type == "docker" and not final_docker:
        raise ValueError("Docker image (--docker-image) is required for container workloads.")

    if "\x00" in final_command:
        raise ValueError("Command contains illegal NUL character.")

    if not final_command.strip():
        raise ValueError("Command cannot be empty or whitespace.")

    if final_vram < 0:
        raise ValueError("Required VRAM must be greater than or equal to 0.")

    return {
        "name": final_name.strip(),
        "workload_type": final_type.strip(),
        "command": final_command.strip(),
        "required_vram_mb": int(final_vram),
        "docker_image": final_docker.strip() if final_docker else None,
    }
