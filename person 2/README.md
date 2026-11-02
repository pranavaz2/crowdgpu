# CrowdGPU Worker

A production-grade GPU Worker node for the CrowdGPU distributed compute platform.

## What it does

```
Worker starts
  → detects NVIDIA GPU via PyNVML
  → registers with Coordinator REST API
  → sends periodic GPU telemetry heartbeats
  → becomes AVAILABLE
  → receives a GPU job
  → validates job + checks free VRAM
  → executes CUDA workload (allow-listed, no arbitrary code)
  → captures result + execution time
  → reports result to Coordinator
  → returns to AVAILABLE
```

## Quick Start

### 1. Install dependencies

```bash
pip install pynvml requests pytest
# For CUDA execution (Python ≤ 3.12 required):
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

### 2. Configure

```bash
cp config/.env.example .env
# Edit .env:
#   COORDINATOR_URL=http://your-coordinator:8000
#   WORKER_ID=worker-gpu-01       (auto-generated if omitted)
#   GPU_ID=0
#   HEARTBEAT_INTERVAL=30
```

### 3. Run

```bash
# Load env and start worker
export $(cat .env | xargs)
python -m worker.worker

# Or with Python entry-point (after pip install -e .):
crowdgpu-worker
```

### 4. Run tests

```bash
# Unit tests only (no GPU required)
pytest tests/unit/ -v

# All tests including live GPU integration
pytest tests/ -v -s

# Demo the MVP flow locally (no Coordinator needed)
python demo_mvp.py
```

---

## Project Structure

```
crowdgpu-worker/
├── worker/
│   ├── gpu/
│   │   └── detector.py        GPU detection & telemetry (PyNVML)
│   ├── coordinator/
│   │   └── client.py          Coordinator REST API client
│   ├── executor/
│   │   ├── cuda_executor.py   Safe CUDA workload executor (allow-listed)
│   │   ├── job_handler.py     Job lifecycle orchestration
│   │   └── docker_executor.py Docker GPU isolation for untrusted workloads
│   ├── config.py              Environment variable configuration
│   ├── state.py               Thread-safe worker state machine
│   └── worker.py              Main orchestrator & CLI entry-point
├── tests/
│   ├── unit/                  77 unit tests (fully mocked, no GPU needed)
│   └── integration/           12 live GPU tests (need NVIDIA GPU)
├── docker/Dockerfile          Multi-stage NVIDIA CUDA container image
└── config/.env.example        Configuration template
```

---

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `COORDINATOR_URL` | *(required)* | Base URL of the Coordinator API |
| `WORKER_ID` | `worker-<random>` | Unique identifier for this worker |
| `GPU_ID` | `0` | Index of the GPU to use |
| `HEARTBEAT_INTERVAL` | `30` | Seconds between heartbeat posts |

---

## Worker States

```
STARTING ──→ AVAILABLE ──→ BUSY ──→ AVAILABLE
    │              │          │
    └──→ ERROR ←───┘          └──→ ERROR ──→ AVAILABLE
              │                                  │
              └──────────────────────────────────┘
                         ↓
                      OFFLINE (terminal)
```

---

## Coordinator API Contract

The worker uses these endpoints (defined by the Coordinator — not invented here):

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/workers/register` | Register worker + GPU info |
| `POST` | `/api/v1/workers/{worker_id}/heartbeat` | Send telemetry + state |
| `POST` | `/api/v1/workers/{worker_id}/status` | Lightweight status update |
| `POST` | `/api/v1/jobs/{job_id}/result` | Post job execution result |

---

## Supported Workload Types

The `CUDAExecutor` only runs allow-listed, built-in workloads. **No arbitrary code is ever executed.**

| Type | Parameters | Description |
|------|-----------|-------------|
| `matrix_multiply` | `dim` (default 1024) | Square matrix multiplication on GPU |
| `vector_add` | `length` (default 10M) | Element-wise vector addition |
| `benchmark` | `dim`, `iterations` | Timed MATMUL GFLOPS benchmark |

For untrusted workloads, use `DockerGPUExecutor` (requires Docker + NVIDIA Container Toolkit).

---

## Safety

- **No `eval()` / `exec()` / `subprocess` with user strings** — ever.
- Workload type is checked against a hard-coded `frozenset` allowlist.
- Matrix dimensions and vector lengths are clamped to prevent OOM.
- Docker executor: image prefix allowlist, exact command allowlist, `network_disabled=True`, `read_only=True`.
- VRAM guard with configurable safety margin (default 256 MiB).

---

## Docker (GPU pass-through)

```bash
# Build
docker build -f docker/Dockerfile -t crowdgpu-worker:latest .

# Run with GPU (requires NVIDIA Container Toolkit)
docker run --gpus device=0 \
  -e COORDINATOR_URL=http://coordinator:8000 \
  -e WORKER_ID=worker-gpu-01 \
  -e GPU_ID=0 \
  crowdgpu-worker:latest
```

---

## Test Results

```
84 passed · 5 skipped (CUDA/torch — needs Python ≤ 3.12) · 0 failed
```
