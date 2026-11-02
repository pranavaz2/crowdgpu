# CrowdGPU Worker — Docker image
#
# Build:
#   docker build -t crowdgpu-worker:latest .
#
# Run (requires NVIDIA Container Toolkit):
#   docker run --gpus device=0 \
#     -e COORDINATOR_URL=http://coordinator:8000 \
#     -e WORKER_ID=worker-gpu-01 \
#     -e GPU_ID=0 \
#     -e HEARTBEAT_INTERVAL=30 \
#     crowdgpu-worker:latest

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy project files
COPY pyproject.toml ./
COPY worker/ ./worker/

# Install runtime dependencies only
RUN pip install --no-cache-dir pynvml requests

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# Use NVIDIA CUDA base so pynvml can talk to the driver
FROM nvidia/cuda:12.1.0-base-ubuntu22.04 AS runtime

# Install Python 3.11
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin/python3.11 /usr/local/bin/python3.11
COPY --from=builder /app/worker ./worker

# Non-root user for safety
RUN useradd --no-create-home --shell /bin/false worker
USER worker

# Environment defaults (override at runtime)
ENV WORKER_ID=""
ENV COORDINATOR_URL=""
ENV GPU_ID="0"
ENV HEARTBEAT_INTERVAL="30"
ENV PYTHONUNBUFFERED="1"

CMD ["python3.11", "-m", "worker.worker"]
