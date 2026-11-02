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

## Running (Development Mode)

```bash
pip install -e ".[dev]"
python -m worker.main
```

The worker will start without requiring GPU hardware and print its status.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `WORKER_ID` | `worker-dev-001` | Unique worker identifier |
| `WORKER_MODE` | `development` | `development` or `production` |
| `WORKER_COORDINATOR_URL` | `http://localhost:8000` | Coordinator base URL |
| `WORKER_LOG_LEVEL` | `INFO` | Log level |

---

## Testing

```bash
pytest
```
