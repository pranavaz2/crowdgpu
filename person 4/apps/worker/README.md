# CrowdGPU Worker Daemon

Provider-side daemon for the CrowdGPU peer-to-peer GPU resource sharing platform.

**Status: Bootstrap phase** — Starts in development mode without GPU hardware.
GPU telemetry, Docker sandboxing, job execution, and WebRTC streaming are not
implemented yet.

---

## Planned Responsibilities

```
worker/
├── config.py       # Configuration
├── status.py       # Self-status reporter
├── monitor/        # GPU hardware monitor (PyNVML) — future
├── sandbox/        # Docker container sandbox engine — future
├── executor/       # Local task executor — future
└── streaming/      # NVENC / WebRTC streaming daemon — future
```

---

## Execution Modes

The worker supports configurable job execution modes:

- **`docker` (default)**: Real container execution using the local Docker Engine. Invokes containers via unprivileged Docker CLI arguments with timeout enforcement, output capture, and guaranteed cleanup.
- **`simulation`**: Explicit development simulation. Does not spawn containers and clearly marks execution logs as simulated.

> **Note on GPU Support**: The Docker executor currently runs in unprivileged CPU mode (`--security-opt=no-new-privileges`, no host mounts). GPU container runtime (`--gpus`) requires NVIDIA Container Toolkit and verified hardware pass-through, which is handled in a separate phase.

---

## Windows & Docker Desktop Setup

### 1. Prerequisites
1. **Docker Desktop for Windows** installed and running with the **WSL 2 backend**.
2. Verify Docker Engine access from PowerShell:
   ```powershell
   docker run --rm ubuntu:latest echo hello
   ```
   This should output `hello`.

### 2. Installation
```powershell
cd apps/worker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 3. Running Job Polling

#### Option A: Real Docker Execution
```powershell
# Auto-register peer with coordinator and poll for assigned jobs:
python -m worker.main --poll --owner-id <OWNER_UUID> --execution-mode docker

# Or poll using an existing registered peer ID:
python -m worker.main --poll --peer-id <PEER_UUID> --execution-mode docker
```

#### Option B: Simulated Execution
```powershell
python -m worker.main --poll --peer-id <PEER_UUID> --execution-mode simulation
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `WORKER_ID` | `worker-dev-001` | Unique worker node identifier |
| `WORKER_MODE` | `development` | Base daemon mode (`development` or `production`) |
| `WORKER_EXECUTION_MODE` | `docker` | Job execution engine: `docker` or `simulation` |
| `WORKER_EXECUTION_TIMEOUT` | `300.0` | Container execution timeout in seconds |
| `WORKER_COORDINATOR_URL` | `http://localhost:8000` | Coordinator base URL |
| `WORKER_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## Testing

Run all unit and integration tests (Docker daemon calls are mocked in unit tests):

```powershell
pytest
```
