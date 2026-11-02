# CrowdGPU — Database Design

## 1. Document Information

**Project:** CrowdGPU  
**Document:** Database Design Specification  
**Status:** Baseline — Initial Schema Implemented

This document defines the persistent relational data model currently implemented for CrowdGPU.

It must remain consistent with:

- `PRD.md`
- `REQUIREMENTS.md`
- `ARCHITECTURE.md`
- `ARCHITECTURE_DECISIONS.md`
- `TECH_STACK.md`

---

# 2. Database Technology

## Primary Database

**PostgreSQL**

PostgreSQL is the authoritative persistent database for CrowdGPU.

The Coordinator accesses PostgreSQL through:

- SQLAlchemy
- SQLAlchemy AsyncIO
- asyncpg

Database migrations are managed through:

- Alembic

---

# 3. Current Schema

The database schema contains four core entities:

```text
users
   │
   ├── 1:N ────────┐
   ▼               ▼
 peers           jobs
   │               │
   │ 1:N           │ N:1 (assigned_peer_id)
   ▼               ▼
gpu_capabilities ◄─┘
```

---

# 4. Entities

## 4.1 `users`
Represents consumers and providers on the platform.

## 4.2 `peers`
Represents provider nodes hosting the worker daemon.

## 4.3 `gpu_capabilities`
Static hardware specifications of GPUs attached to each peer.

## 4.4 `jobs`
Tracks submitted computational tasks, GPU resource requirements, scheduling assignments, and lifecycle states.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `UUID` | Primary Key, default `gen_random_uuid()` | Unique job identifier |
| `owner_id` | `UUID` | Foreign Key -> `users.id`, `ON DELETE RESTRICT` | Owning consumer user |
| `name` | `VARCHAR(120)` | NOT NULL | Task name |
| `command` | `TEXT` | NOT NULL | Execution entrypoint / command |
| `requirements` | `JSONB` | NOT NULL, default `'{}'::jsonb` | Resource needs (`required_vram_mb`, etc.) |
| `status` | `VARCHAR(32)` | NOT NULL, default `'QUEUED'` | Lifecycle status |
| `assigned_peer_id` | `UUID` | Foreign Key -> `peers.id`, `ON DELETE SET NULL` | Target worker peer |
| `attempt_count` | `INTEGER` | NOT NULL, default `0` | Scheduling/execution attempt counter |
| `started_at` | `TIMESTAMPTZ` | NULLABLE | Timestamp when worker acknowledges RUNNING |
| `completed_at` | `TIMESTAMPTZ` | NULLABLE | Timestamp when terminal state is reached |
| `result` | `JSONB` | NULLABLE | Output metadata (`exit_code`, `stdout_tail`, etc.) |
| `error` | `TEXT` | NULLABLE | Error message if failed |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Submission timestamp |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Last modification timestamp |

### Indexes & Constraints
- `ix_jobs_owner_created`: `(owner_id, created_at)`
- `ix_jobs_status_created`: `(status, created_at)`
- `ix_jobs_assigned_peer_status`: `(assigned_peer_id, status)`
- Partial unique index: `uq_jobs_assigned_peer_active` on `(assigned_peer_id)` WHERE `status IN ('ASSIGNED', 'RUNNING')` (prevents double-allocation).

---

# 5. Job Lifecycle States
- `QUEUED`: Submitted workload awaiting matching.
- `MATCHING`: Actively being evaluated by scheduler against available peers.
- `ASSIGNED`: Peer reserved and workload queued for worker pick-up.
- `RUNNING`: Worker daemon has acknowledged workload and execution is underway.
- `COMPLETED`: Workload finished successfully, results stored.
- `FAILED`: Workload failed (matching failure, worker error, or heartbeat timeout).
- `CANCELLED`: Workload cancelled by owner while in QUEUED state.