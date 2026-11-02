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