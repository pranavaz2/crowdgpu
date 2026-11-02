# CrowdGPU Coordinator

Central coordinator for the CrowdGPU peer-to-peer GPU resource sharing platform.

**Status: Peer Registration API (Phase 3.3)** — Peer Registration & Discovery API
established. Endpoints for registration, GPU capabilities, heartbeat, and deregistration.

---

## Architecture

The coordinator is a **modular monolith** (see ADR-001). All logical modules share a
single FastAPI application and deployment unit. Modules are clearly separated internally.

Current package structure:

```
coordinator/
├── api/            # HTTP router layer
│   ├── health.py   # GET /health
│   └── v1/         # Versioned API routes
│       └── peers.py # /api/v1/peers endpoints
├── peers/          # Peer domain & service layer
│   ├── schemas.py  # Pydantic schemas
│   ├── service.py  # PeerService business logic
│   └── exceptions.py # Domain exceptions
├── database/       # Async SQLAlchemy layer
│   ├── base.py     # DeclarativeBase + TimestampMixin
│   ├── session.py  # Engine + AsyncSession factory + get_db() dependency
│   └── models/     # ORM models (User, Peer, GpuCapability)
└── config.py       # Pydantic Settings (DATABASE_URL, etc.)
```

Planned modules (not yet implemented):

```
coordinator/
├── auth/           # Authentication
├── matchmaker/     # Peer matchmaking
├── scheduler/      # Heterogeneity-aware job scheduler
├── jobs/           # Job manager
├── signaling/      # WebRTC signaling gateway
├── verification/   # Output verification
├── accounting/     # Credits and contribution tracking
└── reputation/     # Peer reputation
```

---

## Peer API (v1)

Base path: `/api/v1/peers`

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/peers` | Register a provider peer and its GPU capabilities |
| `GET` | `/api/v1/peers/{peer_id}` | Retrieve peer details and GPU capabilities |
| `PATCH` | `/api/v1/peers/{peer_id}/heartbeat` | Update server-controlled heartbeat timestamp & status |
| `POST` | `/api/v1/peers/{peer_id}/deregister` | Mark peer offline (soft deregistration) |

---

## Running

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Start development server
uvicorn coordinator.main:app --reload --host 0.0.0.0 --port 8000

# Health check
curl http://localhost:8000/health
```

API documentation: `http://localhost:8000/docs`

---

## Database

### Prerequisites

PostgreSQL must be running (via Docker Compose in development):

```bash
# From the project root
docker compose up -d postgres
```

### Running migrations

```bash
cd apps/coordinator
alembic upgrade head
```

### Creating a new migration (after model changes)

```bash
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

### Rolling back

```bash
alembic downgrade -1   # one step back
alembic downgrade base  # full rollback
```

---

## Testing

```bash
# Unit tests (no PostgreSQL required — uses in-memory SQLite)
pytest

# Integration tests (requires PostgreSQL)
$env:TEST_DATABASE_URL = "postgresql+asyncpg://crowdgpu:changeme@localhost:5432/crowdgpu_test"
pytest tests/integration/ -v
```

See `ARCHITECTURE_DECISIONS.md` (ADR-003) for the test isolation strategy.

---

## Linting / Formatting

```bash
# Format
ruff format .

# Lint
ruff check .

# Type check
mypy coordinator/
```

---

## Configuration

All configuration is read from environment variables (or `.env` at the project root).
See `.env.example` for available settings.

Key variables:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://crowdgpu:changeme@localhost:5432/crowdgpu` | Primary database |
| `TEST_DATABASE_URL` | _(unset)_ | PostgreSQL URL for integration tests |
| `COORDINATOR_HOST` | `0.0.0.0` | Listen host |
| `COORDINATOR_PORT` | `8000` | Listen port |

The `coordinator/config.py` module is the single source of truth for configuration.
Do not read `os.environ` directly in coordinator modules.


---

## Architecture

The coordinator is a **modular monolith** (see ADR-001). All logical modules share a
single FastAPI application and deployment unit. Modules are clearly separated internally.

Planned modules (not yet implemented):

```
coordinator/
├── api/            # HTTP router layer
├── auth/           # Authentication
├── peers/          # Peer registry
├── matchmaker/     # Peer matchmaking
├── scheduler/      # Heterogeneity-aware job scheduler
├── jobs/           # Job manager
├── signaling/      # WebRTC signaling gateway
├── verification/   # Output verification
├── accounting/     # Credits and contribution tracking
└── reputation/     # Peer reputation
```

Currently only `api/health` is implemented.

---

## Running

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Start development server
uvicorn coordinator.main:app --reload --host 0.0.0.0 --port 8000

# Health check
curl http://localhost:8000/health
```

API documentation is available at `http://localhost:8000/docs`.

---

## Testing

```bash
pytest
```

---

## Linting / Formatting

```bash
# Format
ruff format .

# Lint
ruff check .

# Type check
mypy coordinator/
```

---

## Configuration

All configuration is read from environment variables (or `.env` at the project root).
See `.env.example` for available settings.

The `coordinator/config.py` module is the single source of truth for configuration.
Do not read `os.environ` directly in coordinator modules.
