# CrowdGPU CLI

Command-line interface for the CrowdGPU distributed GPU resource platform.

The CLI allows users and developers to:
- Inspect coordinator cluster health
- Discover and inspect registered GPU provider peers
- Submit computational GPU jobs using canonical presets or custom workloads
- Monitor execution status and examine tensor results
- Cancel queued jobs
- Diagnose WebRTC signaling status

---

## Installation

Install in editable mode from the monorepo root or the CLI directory:

```bash
cd apps/cli
pip install -e .
```

To run development tests:
```bash
pip install -e ".[dev]"
```

---

## Configuration

The CLI can be configured via environment variables or CLI flags:

| Variable | CLI Flag | Default | Description |
|---|---|---|---|
| `COORDINATOR_URL` | `--coordinator-url` | `http://127.0.0.1:8000` | Target CrowdGPU Coordinator API URL |
| `CROWDGPU_USER_ID` | `--user-id` | `00000000-0000-0000-0000-000000000001` | Client User UUID (X-User-Id header) |

---

## Command Reference & Working Examples

### 1. Check Coordinator Health
```bash
crowdgpu-cli health
```
*Output:*
```text
=== Coordinator Health ===
Coordinator URL: http://127.0.0.1:8000
Status:          ok
Version:         0.1.0
```

### 2. Discover GPU Provider Peers
```bash
# List all registered peers
crowdgpu-cli peers list

# Inspect specific peer hardware telemetry
crowdgpu-cli peers get <PEER_UUID>
```

### 3. Submit a GPU Workload
```bash
# Submit using canonical preset (matrix_multiply, vector_add, benchmark)
crowdgpu-cli jobs submit --preset matrix_multiply

# Submit benchmark with custom name and VRAM allocation
crowdgpu-cli jobs submit --preset benchmark --name "CUDA Benchmark Run" --vram 1024

# Submit custom workload
crowdgpu-cli jobs submit --name "Vector Add 10M" --command vector_add --vram 256
```

### 4. List and Filter Compute Jobs
```bash
# List all jobs
crowdgpu-cli jobs list

# Filter by lifecycle status
crowdgpu-cli jobs list --status QUEUED
crowdgpu-cli jobs list --status COMPLETED
```

### 5. Inspect Job Details & Execution Results
```bash
crowdgpu-cli jobs status <JOB_UUID>
```
*Output shows status, timing, exit code, duration, and structured tensor output.*

### 6. Cancel a Queued Job
```bash
crowdgpu-cli jobs cancel <JOB_UUID>
```

---

## Running Tests

```bash
cd apps/cli
pytest tests -v
```
