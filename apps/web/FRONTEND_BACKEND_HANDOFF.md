# CrowdGPU — Frontend / Backend Handoff Document

> **Status:** Frontend is feature-complete and ready for Coordinator job API integration.
>
> This document is addressed to the Coordinator backend team.
> It describes exactly what the frontend expects, what is already integrated, and what
> steps are required to complete the full-stack connection.

---

## 1. Currently Integrated (Real) Endpoint

### `GET /health`

- **Implementation:** [`apps/coordinator/coordinator/api/health.py`](apps/coordinator/coordinator/api/health.py)
- **Used by:** `Navbar` health indicator, `Dashboard` coordinator status widget
- **Frontend consumer:** `src/services/healthService.js` → `src/hooks/useHealth.js`
- **Expected response:**
  ```json
  { "status": "ok", "version": "0.1.0" }
  ```
- **Status:** ✅ Working

---

## 2. Required Peer Endpoint

### `GET /api/v1/peers`

> This endpoint **does not yet exist** in the Coordinator. The frontend uses
> mock data from `peersService.js` when `VITE_USE_MOCK=true`.

- **Purpose:** List all registered GPU providers with their GPU capabilities
- **Frontend consumer:** `src/services/peersService.js → listPeers()` → `src/hooks/usePeers.js`

**Expected integration shape** *(frontend assumes this structure — confirm against final Coordinator schema before adapting)*:

```json
[
  {
    "id": "uuid-string",
    "owner_id": "uuid-string",
    "hostname": "rig-alpha.local",
    "status": "available",
    "registered_at": "2026-10-01T08:00:00Z",
    "last_seen_at": "2026-10-08T20:00:00Z",
    "created_at": "2026-10-01T08:00:00Z",
    "updated_at": "2026-10-08T20:00:00Z",
    "gpu_capabilities": [
      {
        "id": "uuid-string",
        "peer_id": "uuid-string",
        "gpu_name": "NVIDIA GeForce RTX 4090",
        "vram_mb": 24576,
        "driver_version": "535.104.05",
        "cuda_version": "12.2",
        "compute_capability": "8.9",
        "created_at": "2026-10-01T08:00:00Z",
        "updated_at": "2026-10-08T20:00:00Z"
      }
    ]
  }
]
```

**Peer `status` enum values the frontend handles:**
- `"available"` — green badge, included in stat counts
- `"busy"` — amber badge
- `"offline"` — gray badge, excluded from GPU resource grid

**GPU fields the frontend renders:**
| Field | Used for |
|-------|---------|
| `gpu_name` | Card title, search |
| `vram_mb` | Primary metric (formatted as GB/MB) |
| `cuda_version` | Capability detail row |
| `compute_capability` | Capability detail row |
| `driver_version` | Capability detail row |

**Fields the frontend does NOT expect** (do not fabricate in the response):
- GPU utilization percentage
- GPU temperature
- Free VRAM at runtime
- Power draw

These are static registration fields only.

**Integration step:** When `GET /api/v1/peers` is implemented, in `src/services/peersService.js`:
1. Remove the `if (isMockMode())` block inside `listPeers()`
2. Keep the `normalizePeerResponse()` call on the result
3. Remove `MOCK_PEERS`, `ago()`, `daysAgo()`, `NOW` constants

---

## 3. Required Job Endpoints

> **None of these exist yet.** All job functions are mocked.
> When real endpoints are available, update `src/services/jobsService.js` only.
> No page or hook changes are required.

### `POST /api/v1/jobs`

- **Purpose:** Submit a new GPU workload
- **Frontend consumer:** `createJob(payload)` → `SubmitJobPage`

**Request body** *(fields currently sent by the frontend)*:
```json
{
  "name": "MNIST Training Run",
  "docker_image": "pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
  "command": "python train.py --epochs 10",
  "vram_required_mb": 8192,
  "workload_type": "batch"
}
```

> ⚠️ The `owner_id` / authentication field is **not yet sent** — authentication is not implemented in the frontend. The backend must define the auth mechanism before this field is added.

**Expected response:** Created job object (see job shape below)

---

### `GET /api/v1/jobs`

- **Purpose:** List all jobs for the current session/user
- **Frontend consumer:** `listJobs()` → `useJobs()` → `JobsPage`, `DashboardPage`

**Expected response:** Array of job objects, ordered newest-first (or paginated — the frontend currently renders all results without pagination)

---

### `GET /api/v1/jobs/{job_id}`

- **Purpose:** Retrieve a single job with full status and timeline
- **Frontend consumer:** `getJob(jobId)` → `JobDetailPage`

**Expected response:** Single job object

---

### `POST /api/v1/jobs/{job_id}/cancel`

- **Purpose:** Cancel a queued, matching, or assigned job
- **Frontend consumer:** `cancelJob(jobId)` → Cancel button in `JobDetailPage`
- **Expected response:** Updated job object with `status: "failed"` and `error: "Cancelled by user."`

> The frontend currently only allows cancel for `queued`, `matching`, `assigned` statuses.
> If the backend enforces different cancellability rules, update the cancel button condition in `JobDetailPage.jsx`.

---

## 4. Frontend Job Model

> **These are frontend mock fields, not a committed backend contract.**
> The frontend must adapt to the final Coordinator schema rather than
> requiring the backend to exactly copy the mock schema.

```json
{
  "id": "uuid-string",
  "name": "MNIST Training Run",
  "status": "queued",
  "workload_type": "batch",
  "docker_image": "pytorch/pytorch:latest",
  "command": "python train.py",
  "vram_required_mb": 8192,
  "submitted_at": "2026-10-08T10:00:00Z",
  "matching_at": null,
  "assigned_at": null,
  "started_at": null,
  "completed_at": null,
  "peer_id": null,
  "peer_hostname": null,
  "gpu_name": null,
  "result": null,
  "error": null
}
```

**Job `status` enum values the frontend handles:**

| Status | Badge colour | Meaning |
|--------|-------------|---------|
| `queued` | Violet | Submitted, waiting for scheduling |
| `matching` | Sky blue | Searching for a suitable peer |
| `assigned` | Indigo | Peer found, execution starting |
| `running` | Blue | Currently executing |
| `completed` | Emerald | Finished successfully |
| `failed` | Red | Execution failed or cancelled |

**Timeline fields:**
| Field | Stage label |
|-------|------------|
| `submitted_at` | Submitted |
| `matching_at` | Matching |
| `assigned_at` | Assigned |
| `started_at` | Started |
| `completed_at` | Completed / Failed |

**Result/error fields:**
- `result` — non-null string shown in green section when `status === "completed"`
- `error` — non-null string shown in red section when `status === "failed"`

**Fields that must be confirmed when the real backend is implemented:**
- [ ] Exact field names (`submitted_at` vs `created_at`, `peer_hostname` vs nested peer object, etc.)
- [ ] Whether `matching_at` / `assigned_at` exist as separate timestamps or are derived
- [ ] Whether `peer_hostname` / `gpu_name` are inlined or require a nested object
- [ ] Result format (string? object? URL?)
- [ ] Error format (string? structured?)
- [ ] Pagination parameters for `GET /api/v1/jobs`

---

## 5. Backend Integration Checklist

```
[ ] GET  /api/v1/peers                   implemented
[ ] POST /api/v1/jobs                    implemented
[ ] GET  /api/v1/jobs                    implemented
[ ] GET  /api/v1/jobs/{id}               implemented
[ ] POST /api/v1/jobs/{id}/cancel        implemented
[ ] Final job response schema confirmed  (field names, types, nullability)
[ ] Job status enum confirmed            (queued / matching / assigned / running / completed / failed)
[ ] Timestamp fields confirmed           (submitted_at, matching_at, assigned_at, started_at, completed_at)
[ ] Peer/GPU assignment fields confirmed (peer_id, peer_hostname, gpu_name — inline or nested?)
[ ] Result/error format confirmed        (string? structured object?)
[ ] Authentication requirements confirmed (owner_id, session token, header?)
[ ] Pagination confirmed for GET /api/v1/jobs (cursor? offset? none?)
```

---

## 6. Exact Frontend Integration Procedure

When backend endpoints are ready:

```
1. Set VITE_USE_MOCK=false in apps/web/.env.local

2. Configure VITE_API_BASE_URL if targeting a remote Coordinator:
   VITE_API_BASE_URL=https://coordinator.crowdgpu.example.com

3. Open src/services/jobsService.js
   In each function (listJobs, getJob, createJob, cancelJob):
     - Remove the `if (isMockMode()) { ... }` mock block
     - Replace with the corresponding apiFetch() call documented in the comments
     - Keep the normalizeJobResponse() call on the result

4. Remove mock persistence helpers once real integration is confirmed:
   SESSION_KEY, SEED_JOBS, loadJobs(), saveJobs(), getJobs(), putJobs(), generateId()

5. Update normalizeJobResponse() in jobsService.js if backend field names differ
   from the frontend mock model (this is the ONLY file that needs changing)

6. Similarly update normalizePeerResponse() in peersService.js if backend
   field names differ; remove MOCK_PEERS and the listPeers() mock branch

7. Run the full demo flow and verify all routes:
   /
   /peers
   /jobs
   /jobs/submit
   /jobs/<valid-id>
   /jobs/does-not-exist

8. Run: npm run build
   Expected: 0 errors, 0 warnings
```

---

## 7. Architecture Reference

```
Page
 └─ Hook (useJobs / usePeers / useHealth)
     └─ Service (jobsService / peersService / healthService)
         ├─ Mock path:  isMockMode() → sessionStorage / SEED data
         └─ Real path:  apiFetch(path)
                         └─ fetch() with 10s AbortController timeout
                             └─ Coordinator HTTP API
```

All network calls are isolated to `src/services/`. No page or hook calls `fetch()` directly.

---

## 8. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_USE_MOCK` | `true` | `true` → mock data; `false` → real endpoints |
| `VITE_API_BASE_URL` | `''` | Coordinator origin; empty → Vite proxy → `localhost:8000` |

Copy `apps/web/.env.example` to `apps/web/.env.local` to configure.

---

## 9. Error Handling Guarantees

The frontend provides user-readable messages for all these backend scenarios:

| Scenario | Message shown |
|----------|--------------|
| Network unreachable | "Unable to reach the Coordinator. Check your network connection." |
| Request timeout (>10s) | "Request timed out. Please try again." |
| HTTP 400 | "Invalid request. Check the submitted values and try again." |
| HTTP 404 | "Resource not found." |
| HTTP 422 (validation) | "Validation error. Check the request fields." |
| HTTP 500 | "Coordinator returned an internal server error." |
| FastAPI `{ "detail": "…" }` | Surfaced directly from the backend response |

No raw stack traces are ever shown to users.
