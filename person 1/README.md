# CrowdGPU

**CrowdGPU: Intelligent Peer-to-Peer Distributed GPU Resource Sharing Platform**

CrowdGPU connects users who need GPU compute with providers who have available consumer
GPU resources. The platform supports batch GPU workloads and interactive remote GPU
rendering, combining centralized coordination for peer discovery, matchmaking, scheduling
and accounting with peer-to-peer execution and media communication.

> **Status: Bootstrap phase** — The repository skeleton and development tooling have been
> created. Business functionality has not yet been implemented.

---

## Repository Layout

```
crowdgpu/
├── apps/
│   ├── coordinator/   # Central coordinator — FastAPI modular monolith
│   ├── worker/        # Provider-side worker daemon — Python
│   ├── web/           # Consumer web portal — React + Vite + Tailwind CSS
│   └── cli/           # Developer / consumer CLI — Python + Click
│
├── packages/
│   └── shared/        # Cross-application shared contracts (future)
│
├── infrastructure/
│   ├── docker/        # Dockerfile templates
│   ├── postgres/      # PostgreSQL init scripts
│   ├── redis/         # Redis configuration
│   ├── turn/          # Coturn / TURN server configuration
│   └── monitoring/    # Prometheus + Grafana configuration
│       ├── prometheus/
│       └── grafana/
│
├── research/          # Scheduling research, profiling, notebooks
├── tests/             # Integration, e2e, performance, security tests
├── scripts/           # Developer utility scripts
├── docs/              # Architecture diagrams, API docs, deployment guides
└── .github/
    └── workflows/     # GitHub Actions CI/CD (future)
```

See [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md) for the detailed specification.

---

## Architecture

CrowdGPU follows a **control-plane / execution-plane** separation:

- The **Central Coordinator** (modular monolith) is the control-plane brain.
- The **Worker Daemon** runs on every provider machine and interacts with the GPU.
- Clients communicate with the coordinator via REST/WebSocket.
- Peers communicate directly via WebRTC for data and media.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md).

---

## Technology Stack

| Component | Technology |
|---|---|
| Web frontend | React, Vite, Tailwind CSS |
| Coordinator | Python, FastAPI, Pydantic |
| Worker daemon | Python |
| CLI | Python, Click |
| Database | PostgreSQL, SQLAlchemy, Alembic |
| Cache / broker | Redis, Celery |
| Monitoring | Prometheus, Grafana |
| P2P / streaming | WebRTC, Coturn |
| Infrastructure | Docker, Docker Compose |

See [TECH_STACK.md](TECH_STACK.md) for the full specification.

---

## Development Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Python | 3.11 | Required for coordinator, worker, CLI |
| Node.js | 20 LTS | Required for web frontend |
| npm | 10 | Bundled with Node.js 20 |
| Docker Desktop | Latest | Required for infrastructure services |
| Docker Compose | v2 | Bundled with Docker Desktop |
| Git | 2.x | Source control |

GPU-specific prerequisites (NVIDIA drivers, CUDA, PyNVML, NVIDIA Container Toolkit) are
only required when developing or running the Worker Daemon in GPU mode. They are not
required for bootstrap or coordinator development.

See [DEVELOPMENT_ENVIRONMENT.md](DEVELOPMENT_ENVIRONMENT.md) for the full specification.

---

## Quick Start

### 1. Infrastructure services

```bash
# Copy environment template — fill in values as needed
cp .env.example .env

# Start PostgreSQL, Redis, Prometheus, Grafana, Coturn
docker compose up -d
```

### 2. Coordinator

```bash
cd apps/coordinator
pip install -e ".[dev]"
uvicorn coordinator.main:app --reload
# Health check: GET http://localhost:8000/health
```

### 3. Worker (development / mock mode)

```bash
cd apps/worker
pip install -e ".[dev]"
python -m worker.main
```

### 4. CLI

```bash
cd apps/cli
pip install -e ".[dev]"
crowdgpu-cli --help
crowdgpu-cli --version
```

### 5. Web

```bash
cd apps/web
npm install
npm run dev
# Open http://localhost:5173
```

---

## Running Tests

```bash
# Coordinator
cd apps/coordinator && pytest

# Worker
cd apps/worker && pytest

# CLI
cd apps/cli && pytest

# Web (if test runner configured)
cd apps/web && npm test
```

---

## Project Documents

| Document | Purpose |
|---|---|
| [PRD.md](PRD.md) | Product requirements |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Traceable requirements |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture |
| [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) | Architecture decisions |
| [TECH_STACK.md](TECH_STACK.md) | Technology choices |
| [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md) | Repository layout spec |
| [DEVELOPMENT_ENVIRONMENT.md](DEVELOPMENT_ENVIRONMENT.md) | Dev environment spec |
