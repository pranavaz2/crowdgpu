# CrowdGPU — API Specification

## 1. Document Information

**Project:** CrowdGPU  
**Document:** API Specification  
**Status:** Baseline — Peer Registration API Implemented

This document defines the HTTP and real-time API contracts of the CrowdGPU Coordinator.

The API must remain consistent with:

- `PRD.md`
- `REQUIREMENTS.md`
- `ARCHITECTURE.md`
- `ARCHITECTURE_DECISIONS.md`
- `TECH_STACK.md`
- `DATABASE_DESIGN.md`

---

# 2. API Architecture

The CrowdGPU Coordinator exposes application APIs to:

- Web Client
- CLI
- Worker Daemon
- Prometheus Monitoring

```text
Web Client / CLI                Worker Daemon
      │                               │
      │ REST                          │ REST
      ▼                               ▼
┌──────────────────────────────────────────────┐
│             CrowdGPU Coordinator             │
│                                              │
│  /api/v1/jobs               /api/v1/peers    │
│  /api/v1/workers            /health, /metrics│
│  JobService                 PeerService      │
│  Scheduler                  Reaper           │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
                  PostgreSQL
```

---

# 3. API Endpoints

## 3.1 System Endpoints
| Method | Path | Description | Response |
|---|---|---|---|
| `GET` | `/health` | Liveness / health probe | `{"status": "ok", "version": "0.1.0"}` |
| `GET` | `/metrics` | Prometheus metrics scrape endpoint | Prometheus text format |
| `GET` | `/docs` | OpenAPI Swagger documentation | Interactive UI |

## 3.2 Peer Endpoints (`/api/v1/peers`)
| Method | Path | Description | Success | Errors |
|---|---|---|---|---|
| `POST` | `/api/v1/peers` | Register a new provider node with GPU capabilities | 201 Created | 404 (Owner), 422 |
| `GET` | `/api/v1/peers/{id}` | Retrieve peer status and registered GPUs | 200 OK | 404 |
| `PATCH` | `/api/v1/peers/{id}/heartbeat` | Update heartbeat timestamp and optional status | 200 OK | 404 |
| `POST` | `/api/v1/peers/{id}/deregister` | Mark peer offline (soft-deregistration) | 200 OK | 404 |

## 3.3 Job Endpoints (`/api/v1/jobs`)
All client routes require the `X-User-Id` header (UUID of caller).

| Method | Path | Description | Success | Errors |
|---|---|---|---|---|
| `POST` | `/api/v1/jobs` | Submit a computational workload | 201 Created | 401, 404, 422 |
| `GET` | `/api/v1/jobs` | List caller's jobs (`?status=&limit=&offset=`) | 200 OK | 401 |
| `GET` | `/api/v1/jobs/{id}` | Retrieve job details (caller must own job) | 200 OK | 401, 404 |
| `POST` | `/api/v1/jobs/{id}/cancel` | Cancel a job while in QUEUED state | 200 OK | 401, 404, 409 |
| `POST` | `/api/v1/jobs/{id}/status` | Worker updates execution status (`RUNNING` / `FAILED`) | 200 OK | 401, 403, 404, 409 |
| `POST` | `/api/v1/jobs/{id}/result` | Worker submits completed output (`COMPLETED`) | 200 OK | 401, 403, 404, 409 |

## 3.4 Worker Endpoints (`/api/v1/workers`)
| Method | Path | Description | Success | Errors |
|---|---|---|---|---|
| `GET` | `/api/v1/workers/{id}/jobs/next` | Worker polls for pending assigned job | 200 OK / 204 No Content | 404 |
| `POST` | `/api/v1/workers/register` | Alias for peer registration | 201 Created | 404, 422 |
| `POST` | `/api/v1/workers/{id}/heartbeat` | Alias for peer heartbeat | 200 OK | 404 |