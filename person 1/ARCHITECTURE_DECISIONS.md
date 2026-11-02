# CrowdGPU — Architecture Decision Records

## 1. Document Information

**Project:** CrowdGPU  
**Full Name:** CrowdGPU: Intelligent Peer-to-Peer Distributed GPU Resource Sharing Platform

**Document:** Architecture Decision Records

**Purpose:** Record important architectural and technical decisions, their rationale, alternatives, trade-offs, and impact.

**Status:** Baseline

---

# 2. Decision Management

Every important architectural decision should record:

- Decision ID
- Title
- Status
- Context
- Decision
- Rationale
- Alternatives considered
- Trade-offs
- Consequences
- Affected components
- Date / phase

Decisions should not be silently changed during development.

If a decision needs to change, create a new decision or explicitly supersede the existing one.

---

# ADR-001 — Modular Monolith Coordinator

**Status:** Accepted

## Context

CrowdGPU contains multiple logical coordinator responsibilities:

- API
- Peer Registry
- Matchmaker
- Scheduler
- Job Manager
- Signaling
- Verification
- Accounting
- Reputation

The project requires clear modular separation but does not currently require independent deployment of every component.

## Decision

The CrowdGPU Coordinator will initially be implemented as a **modular monolith**.

Logical modules will remain clearly separated inside the same deployable coordinator application.

Conceptually:

```text
Coordinator
├── API
├── Authentication
├── Peer Registry
├── Matchmaker
├── Scheduler
├── Job Manager
├── Signaling
├── Verification
├── Accounting
└── Reputation

---

# ADR-002 — CLI Framework: Click

**Status:** Accepted

**Phase:** 3 — Bootstrap

## Context

The CrowdGPU CLI (`apps/cli/`) requires a Python CLI framework.

`TECH_STACK.md` specifies Python as the CLI language but does not specify a CLI framework.

## Decision

The CrowdGPU CLI will use **Click** (`click>=8.1.7`).

## Rationale

- Click is the dominant Python CLI framework and is already a transitive dependency of FastAPI and uvicorn.
- It provides composable command groups, built-in `--help` and `--version` generation, and a `CliRunner` test utility compatible with pytest.
- It integrates cleanly with Pydantic-based configuration.
- No additional infrastructure or runtime is required.

## Alternatives Considered

| Alternative | Reason not chosen |
|---|---|
| `argparse` | Standard library, but verbose and lacks composable group structure |
| `typer` | Built on Click; adds type-annotation ergonomics but adds a dependency layer without benefit at this stage |
| `python-fire` | Less explicit; harder to test deterministically |

## Trade-offs

- Click adds one direct dependency. This is minimal and well-justified.
- Typer would be a straightforward future upgrade if desirable.

## Consequences

- `apps/cli/pyproject.toml` declares `click>=8.1.7` as a direct dependency.
- CLI tests use `click.testing.CliRunner`.

## Affected Components

- `apps/cli/`

## Date / Phase

Bootstrap — Phase 3.1

---

# ADR-003 — Unit Test Isolation Strategy: aiosqlite for Model Tests

**Status:** Accepted

**Phase:** 3 — Database Foundation (3.2)

## Context

Task 3.2 establishes SQLAlchemy async models targeting PostgreSQL.

The task requirements contain two constraints that are in tension:

1. "Do not require the full Docker stack merely to run unit tests."
2. "Do not fake PostgreSQL-specific behavior."

A single strategy cannot satisfy both constraints for all tests simultaneously.

## Decision

Split tests into two tiers:

**Tier 1 — Unit/Model tests** (`tests/`)

- Use `aiosqlite` in-memory database.
- Cover: model instantiation, relationships, basic CRUD, cascade correctness.
- These tests run without Docker or any external service.
- They do NOT cover PostgreSQL-specific constraint behavior (e.g. `CHECK` constraints, `UUID` type enforcement, `TIMESTAMPTZ` precision).

**Tier 2 — Integration tests** (`tests/integration/`)

- Require a live PostgreSQL instance via `TEST_DATABASE_URL` environment variable.
- Skipped automatically via `pytest.mark.skipif` when `TEST_DATABASE_URL` is not set.
- Cover: PostgreSQL-specific constraint enforcement, Alembic migration against real Postgres.

## Rationale

- Tier 1 tests give fast, dependency-free feedback on model correctness.
- Tier 2 tests give authoritative PostgreSQL validation in CI or when Docker is available.
- The split is honest: no tier claims to validate more than it actually tests.
- This pattern is standard in the SQLAlchemy ecosystem.

## Alternatives Considered

| Alternative | Reason not chosen |
|---|---|
| Always require PostgreSQL | Blocks development without Docker; violates task requirement |
| Use SQLite for all tests, claim PostgreSQL compatible | Dishonest; hides PostgreSQL-specific failures |
| Use `pytest-postgresql` / `testcontainers` | Extra infrastructure dependency; adds complexity before CI is established |

## Trade-offs

- Integration tests will not run in this machine's environment (no Docker).
- Unit tests are slightly less authoritative for DB-level constraints.

## Consequences

- `aiosqlite>=0.20.0` added as a dev dependency.
- Integration tests in `tests/integration/` are marked with `skipif`.
- CI must set `TEST_DATABASE_URL` to get full PostgreSQL coverage.

## Affected Components

- `apps/coordinator/tests/`
- `apps/coordinator/tests/integration/`

## Date / Phase

Database Foundation — Phase 3.2

---

# ADR-004 — Job Control Plane & MVP Scheduler Design

**Status:** Accepted

**Phase:** Person 1 — Coordinator + Database + Scheduler

## Context

CrowdGPU requires an end-to-end control-plane mechanism to:
1. Accept computational GPU workloads from consumers.
2. Discover and evaluate eligible peer provider machines with appropriate GPU hardware capabilities.
3. Atomically assign and reserve peers to avoid duplicate assignment race conditions.
4. Track workload lifecycle state from submission to completion or failure.
5. Provide fault tolerance against unresponsive or disconnected workers.

## Decision

1. **Worker ↔ Peer Identity**: A Worker node is identified as a `Peer`. We reuse the existing `peers` and `gpu_capabilities` tables without duplicating models or registration endpoints.
2. **State Machine**: All job state transitions pass through a centralized `transition_job_status` validator enforcing allowed transitions (`QUEUED -> MATCHING -> ASSIGNED -> RUNNING -> COMPLETED/FAILED` and `QUEUED -> CANCELLED`) and actor permissions (`client`, `scheduler`, `worker`, `reaper`).
3. **Atomic Reservation**: The scheduler uses PostgreSQL row-level locks (`SELECT ... FOR UPDATE SKIP LOCKED`) combined with a partial unique index `UNIQUE (assigned_peer_id) WHERE status IN ('ASSIGNED', 'RUNNING')` to guarantee zero double-allocations even under concurrent scheduler execution.
4. **MVP Modular Scheduler**: Implemented with a pluggable `ScoringStrategy` ABC and `DefaultScoringStrategy` combining tight-fit VRAM heuristic (50%), heartbeat freshness (30%), and latency (20%, only if measured RTT exists; otherwise normalized between VRAM and freshness without fabricating data).
5. **Reaper**: A background reconciliation routine that detects stale heartbeats (>30s) to mark peers offline and safely requeue unacknowledged `ASSIGNED` jobs or fail crashed `RUNNING` jobs.

## Consequences

- Full control-plane lifecycle is operational and testable.
- Future advanced schedulers (Castor, Wise, Dally) can drop in by implementing `ScoringStrategy` without altering database schemas or API routes.
