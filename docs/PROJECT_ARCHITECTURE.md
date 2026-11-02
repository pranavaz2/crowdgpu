# CrowdGPU — System Architecture & Component Responsibilities

**Project**: CrowdGPU Distributed Peer-to-Peer GPU Computing Platform  
**Document**: Project Architecture & Component Responsibilities  
**Release**: Stage 7 Academic Release Candidate

---

## 1. System Architecture Diagram

```
                                  +------------------------------------+
                                  |         Web Browser Client         |
                                  |       React 18 / Tailwind CSS      |
                                  |         (apps/web: Port 5173)      |
                                  +-----------------+------------------+
                                                    |
                                                    | HTTP REST / JSON
                                                    | (Vite Proxy: /api, /health)
                                                    v
+-----------------------+         +-----------------+------------------+
|      CrowdGPU CLI     |         |     FastAPI Coordinator Gateway    |
|   (apps/cli: Python)  +-------->|      (apps/coordinator: Port 8000)  |
+-----------+-----------+  REST   +--------+--------+--------+---------+
            |                              |        |        |
            | P2P Data Channel             |        |        | WebSocket
            | (Direct WebRTC)              |        |        | Signaling
            v                              |        |        v
+-----------+-----------+                  |        |  +-----+------------------+
|      Remote Peer      |<-----------------+        |  |  Signaling Router      |
|    WebRTC Endpoint    |  SDP / ICE Signaling      |  |  HMAC Token Auth       |
+-----------------------+                           |  |  180 msgs/min Rate Lim |
                                                    |  +------------------------+
                                                    |
                       +----------------------------+---------------------------+
                       |                                                        |
                       v                                                        v
       +---------------+----------------+                      +----------------+---------------+
       |       PostgreSQL 16 DB         |                      |       GPU Worker Daemon        |
       |  (SQLAlchemy / asyncpg: 5432)  |                      |      (apps/worker: Python)     |
       +--------------------------------+                      +----------------+---------------+
       |  - users                       |                                       |
       |  - peers                       |                                       | PyNVML Telemetry
       |  - gpu_capabilities            |                                       | PyTorch CUDA Execution
       |  - jobs                        |                                       v
       |  - canonical Alembic revisions |                      +----------------+---------------+
       +--------------------------------+                      |   Physical NVIDIA Hardware     |
                                                               |   GeForce RTX 3050 Laptop GPU  |
                                                               |   (4096 MiB VRAM / Driver 591) |
                                                               +--------------------------------+
```

---

## 2. Component Breakdown & Responsibilities

### 2.1 React Web Portal (`apps/web`)
- **Technology**: React 18, Vite, Tailwind CSS, Lucide icons.
- **Port**: `5173` (proxies `/api/v1/*` and `/health` to coordinator).
- **Responsibilities**:
  - Live hardware capability visualization (GPU model, total VRAM, driver version, peer status).
  - Workload submission UI with standard presets (`matrix_multiply`, `vector_add`, `benchmark`).
  - Real-time job lifecycle tracking (`QUEUED` $\rightarrow$ `ASSIGNED` $\rightarrow$ `RUNNING` $\rightarrow$ `COMPLETED` / `FAILED`).
  - Result inspection modal displaying execution time, standard deviation, and tensor output dimensions.
  - Safe development mode (`VITE_USE_MOCK=false` uses genuine coordinator backend; `VITE_USE_MOCK=true` simulates offline preview).

### 2.2 Canonical Coordinator (`apps/coordinator`)
- **Technology**: FastAPI, Pydantic v2, asyncpg, Starlette WebSockets.
- **Port**: `8000`.
- **Sub-Modules**:
  - **Core Auth (`core/auth.py`)**: Cryptographic HMAC-SHA256 user and worker token validation. Enforces strict authentication in production while permitting local demo workflows.
  - **Scheduler (`scheduler/scheduler.py`)**: Intelligent, VRAM-aware greedy matching algorithm. Evaluates GPU capability records, filters stale peers, and assigns pending jobs to optimal hardware.
  - **Job Service (`jobs/service.py`)**: Concurrency-safe job status transitions governed by `JobStateMachine`. Enforces tenant isolation (a user only sees their own jobs).
  - **Peer Service (`peers/service.py`)**: Atomic registration of peer hardware capabilities, heartbeat updates, and deregistration.
  - **Reaper Background Task (`scheduler/reaper.py`)**: Periodic sweeper identifying stale workers (no heartbeat $>30$s), marking peers offline, and requeueing orphaned jobs.
  - **Signaling Router (`signaling/router.py`)**: WebRTC signaling gateway for SDP offer/answer exchange and ICE candidate routing. Enforces per-peer rate limiting (180 msgs/min) and anti-spoofing checks.

### 2.3 PostgreSQL Database & Migrations
- **Engine**: PostgreSQL 16 on port `5432`.
- **ORM**: SQLAlchemy 2.0 async engine (`postgresql+asyncpg://`).
- **Canonical Schema**:
  - `users`: Core identity table with UUID primary keys and email index.
  - `peers`: Registered provider nodes, hostname, status (`available`, `busy`, `offline`), and heartbeat timestamps.
  - `gpu_capabilities`: 1-to-many relationship with peers, recording GPU model, VRAM (MiB), driver version, and CUDA version.
  - `jobs`: Submitted computational workloads, requirements JSON, status, assigned peer reference, and execution output data.
- **Alembic Revisions**: Canonical migration chain (`0001_initial_schema.py`, `0002_jobs_and_scheduling.py`) ensuring non-destructive schema upgrades.

### 2.4 NVIDIA GPU Worker Daemon (`apps/worker`)
- **Technology**: Python 3.11, PyNVML, PyTorch (CUDA 12.1+).
- **Sub-Modules**:
  - **Detector (`gpu/detector.py`)**: Direct hardware interrogation via PyNVML, querying physical GPU model, total VRAM, and driver release.
  - **Worker State Machine (`state.py`)**: Thread-safe state progression: `STARTING` $\rightarrow$ `AVAILABLE` $\leftrightarrow$ `BUSY` $\rightarrow$ `OFFLINE` / `ERROR`.
  - **Coordinator Client (`coordinator/client.py`)**: Resilient HTTP client with retry backoff, authenticated session management, and heartbeat dispatching.
  - **Job Handler (`executor/job_handler.py`)**: Validates job schema, enforces 256 MiB VRAM safety buffer, dispatches workloads to executor, and sanitizes secrets from results.
  - **CUDA Executor (`executor/cuda_executor.py`)**: Workload allowlist (`matrix_multiply`, `vector_add`, `benchmark`) executing on physical GPU tensors.
  - **Docker Executor (`executor/docker_executor.py`)**: Isolated container execution boundary with read-only rootfs and network disabled.

### 2.5 Command-Line Interface (`apps/cli`)
- **Technology**: Click, httpx, aiortc, WebSockets.
- **Commands**:
  - `crowdgpu-cli health`: Coordinator status check.
  - `crowdgpu-cli peers list / get`: GPU discovery and peer capability inspection.
  - `crowdgpu-cli jobs submit / list / status / cancel`: Workload lifecycle management.
  - `crowdgpu-cli webrtc listen / connect`: Direct peer-to-peer data channel communication.

### 2.6 WebRTC Peer-to-Peer Subsystem
- **Signaling Phase**: WebSocket handshake on coordinator (`/ws/signaling`). Peers exchange SDP offers, answers, and ICE candidates without the coordinator inspecting payload content.
- **P2P Transport Phase**: aiortc opens direct `RTCDataChannel`. Peers exchange structured protocol envelopes (`crowdgpu-p2p/1.0`).
- **Zero HTTP Relay**: Application data travels strictly peer-to-peer over UDP/DTLS/SCTP. Acknowledgements verify payload integrity via SHA-256 hashes with sub-2ms latency.

---

## 3. End-to-End Workflow Data Paths

### Flow A: Computational GPU Job Execution
1. **Submission**: User submits a job via React web portal or CLI $\rightarrow$ `POST /api/v1/jobs`.
2. **Persistence**: Coordinator persists job in `QUEUED` status in PostgreSQL.
3. **Scheduling**: Scheduler evaluates available peers and reserves matching peer $\rightarrow$ transitions job to `ASSIGNED`.
4. **Polling**: Worker queries `GET /api/v1/workers/{peer_id}/jobs/next`, retrieves job payload, and confirms `POST /api/v1/jobs/{id}/status` (`RUNNING`).
5. **Execution**: Worker executes CUDA kernel on physical GPU (PyTorch tensor operations).
6. **Reporting**: Worker reports sanitized output data to `POST /api/v1/jobs/{id}/result` $\rightarrow$ transitions job to `COMPLETED` and frees peer to `AVAILABLE`.
7. **Viewing**: Frontend poll / refresh retrieves completed result and displays GPU execution metrics to user.

### Flow B: Direct WebRTC P2P Data Channel
1. **Discovery**: Peer A and Peer B register on WebSocket signaling gateway (`/ws/signaling`).
2. **Negotiation**: Peer A sends SDP Offer $\rightarrow$ Coordinator relays to Peer B $\rightarrow$ Peer B replies with SDP Answer.
3. **ICE Candidates**: Peers exchange local host candidates via coordinator.
4. **Direct Channel**: Browsers / CLI peers establish DTLS handshake and open direct `RTCDataChannel`.
5. **Direct Transfer**: Peer A dispatches payload directly to Peer B; Peer B computes SHA-256 checksum and returns direct ACK (zero HTTP server involvement).
