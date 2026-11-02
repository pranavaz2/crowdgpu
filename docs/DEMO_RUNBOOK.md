# CrowdGPU — Academic Demonstration Runbook

This runbook provides a reliable, reproducible, step-by-step procedure for demonstrating the **CrowdGPU** distributed peer-to-peer GPU computing platform.

---

## 1. System Architecture & Prerequisites

### Architecture Overview
CrowdGPU is composed of three integrated subsystems:
1. **Canonical Coordinator (`apps/coordinator`)**: FastAPI service with PostgreSQL database, Alembic schema versioning, peer capability discovery, and an intelligent VRAM-aware scheduler. Runs on port `8000`.
2. **NVIDIA GPU Worker (`apps/worker`)**: PyNVML GPU hardware detector, state machine (`STARTING` $\rightarrow$ `AVAILABLE` $\rightarrow$ `BUSY`), heartbeat loop, job polling loop, and controlled PyTorch CUDA executor (`matrix_multiply`, `vector_add`, `benchmark`).
3. **React Web Portal (`apps/web`)**: Modern React 18 dashboard built with Vite and Tailwind CSS. Interfaces directly with coordinator REST endpoints via proxy, providing real-time peer telemetry and job execution status. Runs on port `5173`.

```
[ Browser / React Web ] (Port 5173)
           │
      REST │ (Vite Proxy: /api, /health)
           ▼
[ Coordinator & Scheduler ] (Port 8000) ── asyncpg ──▶ [ PostgreSQL DB ] (Port 5432)
           ▲
      REST │ (Register, Heartbeat, Poll, Result)
           │
  [ GPU Worker Daemon ] ── PyNVML / PyTorch ──▶ [ NVIDIA GPU (CUDA) ]
```

### System Prerequisites
- **Operating System**: Windows 10/11 or Linux
- **Python**: 3.11+
- **Node.js**: v18.0+ / npm v9.0+
- **PostgreSQL**: PostgreSQL 15+ running on port `5432` with database `crowdgpu`
- **NVIDIA GPU**: CUDA-capable GPU with drivers installed (e.g., NVIDIA GeForce RTX series) and PyTorch with CUDA support (`torch.cuda.is_available() == True`).

---

## 2. Environment Configuration

### Frontend Configuration (`apps/web/.env.local`)
Create or verify `apps/web/.env.local`:
```ini
# Real backend integration mode
VITE_USE_MOCK=false
VITE_API_BASE_URL=
VITE_DEMO_USER_ID=00000000-0000-0000-0000-000000000001
```

### Coordinator Configuration
Settings are configured in `apps/coordinator/coordinator/config.py` and can be overridden via environment variables:
- `DATABASE_URL`: `postgresql+asyncpg://crowdgpu:changeme@localhost:5432/crowdgpu`
- `DEMO_AUTH_ENABLED`: `False` (header authentication enabled by default)
- `DEMO_USER_ID`: `00000000-0000-0000-0000-000000000001`
- `DEMO_USER_EMAIL`: `demo@crowdgpu.local`
- `COORDINATOR_PORT`: `8000`

### Worker Configuration
Worker loads settings from environment variables with sensible defaults:
- `COORDINATOR_URL`: `http://127.0.0.1:8000`
- `GPU_ID`: `0`
- `HEARTBEAT_INTERVAL`: `5` (seconds)
- `POLL_INTERVAL`: `1.0` (seconds)
- `VRAM_SAFETY_MARGIN_MIB`: `256`

---

## 3. Exact Startup Commands

Open three separate terminal windows in the project directory:

### Terminal 1: Coordinator Server
```powershell
cd "apps\coordinator"
python -m uvicorn coordinator.main:app --host 127.0.0.1 --port 8000
```
*Expected Output:*
```
INFO: Started server process
INFO: Waiting for application startup.
INFO: CrowdGPU Coordinator starting up
INFO: Application startup complete.
INFO: Uvicorn running on http://127.0.0.1:8000
```

### Terminal 2: GPU Worker Daemon
```powershell
cd "apps\worker"
$env:COORDINATOR_URL='http://127.0.0.1:8000'
$env:WORKER_ID='demo-rtx3050-worker'
$env:GPU_ID='0'
$env:HEARTBEAT_INTERVAL='5'
$env:POLL_INTERVAL='1.0'
python -m worker.worker
```
*Expected Output:*
```
[INFO] worker.gpu.detector — GPU detected: NVIDIA GeForce RTX ... — 4096 MiB VRAM
[INFO] worker.coordinator.client — Registering with Coordinator: http://localhost:8000/api/v1/workers/register
[INFO] worker.coordinator.client — Registration successful (assigned peer_id=...)
[INFO] worker.state — State: STARTING -> AVAILABLE
[INFO] Worker is AVAILABLE and ready for jobs.
[INFO] Heartbeat loop started (interval=5s)
[INFO] Job polling loop started (interval=1.0s)
```

### Terminal 3: Vite React Web Portal
```powershell
cd "apps\web"
npm run dev -- --host 127.0.0.1 --port 5173
```
*Expected Output:*
```
  VITE v5.4.21 ready in 650 ms
  ➜ Local: http://127.0.0.1:5173/
```

**Browser Demo URL:** Open [http://localhost:5173](http://localhost:5173) in Chrome or Edge.

---

## 4. Five-Minute Reliable Demo Sequence

### Step 1: Platform Health & Discovery (Dashboard `/`)
1. Open [http://localhost:5173/](http://localhost:5173/).
2. Point out the top header:
   - Green indicator badge: **Coordinator Online v0.1.0** (fetched live from `GET /health`).
3. Highlight platform statistics cards:
   - **Active Peers**: Shows count of currently registered providers in `available` state.
   - **Available GPUs**: Total physical GPUs detected.
   - **Available VRAM**: Total compute memory across connected provider peers.

### Step 2: GPU Hardware Inspection (`/peers`)
1. Click **GPU Resources** in the top navigation bar (or *View all resources*).
2. Point out the registered provider card:
   - **Hostname**: Displays worker ID/hostname.
   - **Status Badge**: Green `Available` pill.
   - **Primary GPU**: `NVIDIA GeForce RTX 3050 Laptop GPU` (or detected model).
   - **Total VRAM**: e.g., `4 GB` (4,096 MiB).
   - **Last Seen**: Dynamic relative timestamp updated via live heartbeats.
3. Click the expand toggle (**▼**) on the card:
   - Reveals hardware telemetry: Driver version, CUDA version, compute capability, registration date, and UUID.

### Step 3: Workload Submission (`/jobs/submit`)
1. Click **+ Submit Job** in the navigation bar.
2. Under **Workload Type**, select **Matrix Multiplication (CUDA)** preset:
   - Notice the form pre-populates safe defaults:
     - Job Name: `CUDA Matrix Multiplication`
     - Command / Target: `matrix_multiply`
     - Minimum VRAM Required: `512 MiB — Lightweight`
3. Click **Submit Job** (`#btn-submit-job`).

### Step 4: Live GPU Execution & Real-Time Tracking (`/jobs/:id`)
1. The browser immediately redirects to `/jobs/<job-id>`.
2. Walk the audience through the real-time execution lifecycle:
   - Status begins as `Queued` or `Assigned` with the assigned worker hostname.
   - Worker retrieves the job via `GET /jobs/next`, marks status `RUNNING`, and claims local GPU.
   - PyTorch CUDA executor executes synchronized matrix multiplication on GPU.
   - Worker posts structured output back to coordinator.
   - Live frontend polling detects completion: badge transitions to **Completed** (green).
3. Review the **Execution Result** section:
   - **Duration**: ~`1.6s - 2.1s` (physical execution time).
   - **Exit Code**: `0`.
   - **Structured JSON Result**: Displays actual computed tensor statistics:
     ```json
     {
       "device": "cuda:0",
       "execution_time_s": 1.629,
       "output": {
         "matrix_dim": 1024,
         "result_mean": -0.0173,
         "result_shape": [1024, 1024],
         "result_std": 32.034
       },
       "success": true,
       "workload_type": "matrix_multiply"
     }
     ```

### Step 5: Capacity Constraints & Job Cancellation Demo (`/jobs/submit` $\rightarrow$ `/jobs/:id`)
1. Click **+ Submit Job** again.
2. Enter Job Name: `Overcapacity Job — Cancellation Test`.
3. Select Minimum VRAM Required: **16 GB — 16,384 MiB** (exceeding individual provider capacity).
4. Click **Submit Job**.
5. On the Job Detail page:
   - Notice the job status is **Queued** because no single worker has $\ge 16\text{ GB}$ VRAM.
   - The message reads: *"Searching for a provider that meets the VRAM requirement."*
6. Click the red **Cancel Job** button.
7. Observe immediate feedback:
   - Status badge transitions to **Cancelled**.
   - Cancellation message appears: *"Cancelled by user."*

### Step 6: Audit History & Filterable Job List (`/jobs`)
1. Click **Jobs** in the top navigation bar.
2. Confirm the centralized job table displays all jobs from the session:
   - Both the completed CUDA run and the cancelled run are listed.
3. Demonstrate instant client-side filtering by clicking the **Completed** and **Cancelled** filter pills.

---

## 5. CLI Demonstration Sequence

The platform provides a native Command-Line Interface (`crowdgpu-cli`) for headless and scriptable operations.

### Step 1: Coordinator Health Check
```powershell
crowdgpu-cli health
```
*Expected Output:*
```text
=== Coordinator Health ===
Coordinator URL: http://127.0.0.1:8000
Status:          ok
Version:         0.1.0
```

### Step 2: Inspect Connected GPU Provider Peers
```powershell
crowdgpu-cli peers list
```
*Expected Output shows peer UUID, hostname, status (AVAILABLE), and attached GPU specs.*

### Step 3: Submit Workload via CLI
```powershell
crowdgpu-cli jobs submit --preset matrix_multiply --name "CLI Demo Matrix Multiply"
```
*Expected Output confirms job submission with ID and assigned peer.*

### Step 4: Track Execution & Inspect Genuine CUDA Tensor Output
```powershell
crowdgpu-cli jobs status <JOB_ID>
```
*Expected Output displays status COMPLETED, duration ~1.5s, exit code 0, device cuda:0, and tensor statistics.*

### Step 5: Test Safe Cancellation of Overcapacity Workload
```powershell
# Submit a job requiring more VRAM than the host GPU has (e.g. 16 GB)
crowdgpu-cli jobs submit --preset benchmark --name "Large Job" --vram 16384

# Cancel the queued job
crowdgpu-cli jobs cancel <JOB_ID>
```
*Expected Output confirms transition to CANCELLED with no execution.*

---

## 6. Multi-Worker Scheduling & Simulation Distinction

When evaluating multi-worker scheduling:
- **Automated Multi-Peer Tests (`tests/test_multi_worker_scheduling.py`)**: 7 comprehensive automated tests verify concurrent claiming, tight-fit VRAM routing, one-active-job constraints, and reaper failure recovery across multiple simulated peers.
- **Single Physical GPU Host**: On this demonstration workstation, one physical NVIDIA GeForce RTX 3050 Laptop GPU is available and actively executed. Multi-node WAN clusters across distinct physical GPU chassis can be deployed by configuring separate worker daemons with unique `WORKER_ID` values.

---

## 7. WebRTC Peer-to-Peer Data Channel Demonstration

CrowdGPU Stage 5 introduces genuine WebRTC data-channel transport between peers, enabling direct, high-throughput, low-latency communication with zero payload relaying through the central coordinator.

### Architectural Boundary: WebRTC vs Coordinator
- **Authoritative Coordinator**: The coordinator remains the single source of truth for job lifecycle state (`QUEUED`, `ASSIGNED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`), GPU capability registration, worker heartbeats, and scheduling decisions. WebRTC peer connections do not execute arbitrary remote shell commands or bypass coordinator authentication.
- **Direct P2P Data Transport**: Once peers are discovered and signaling completes via the coordinator WebSocket (`/api/v1/signaling/ws`), an `RTCDataChannel` is opened directly between peers. Payloads (e.g., job inputs, tensor weights, telemetry packets) flow directly between peer endpoints over SCTP/DTLS. Every envelope includes a cryptographic SHA-256 checksum and requires a matching direct acknowledgement (ACK).

### WebRTC Prerequisites & Dependencies
- `aiortc` (v1.15.0+)
- `websockets` (v15.0+)
- Configurable STUN servers via `STUN_SERVER` environment variable (default: `stun:stun.l.google.com:19302`)
- Optional TURN servers via `TURN_SERVER_URL`, `TURN_USERNAME`, `TURN_PASSWORD`

### Exact Demonstration Procedure

#### Step 1: Check Signaling Gateway Status
```powershell
crowdgpu-cli webrtc status
```
*Expected Output:*
```
=== WebRTC Signaling Status ===
Connected Peers Count: 0
Connected Peers:       None

Configured ICE Servers:
  - URLs: stun:stun.l.google.com:19302
```

#### Step 2: Start Peer B (Receiver Listener)
In a new terminal window:
```powershell
crowdgpu-cli webrtc listen --peer-id demo-rx-peer --timeout 60
```
*Expected Output:*
```
[*] Starting WebRTC Receiver Peer: 'demo-rx-peer'
[*] Coordinator Signaling: http://127.0.0.1:8000
[*] Auto-ACK direct P2P messages: Enabled
[+] Registered with signaling gateway as 'demo-rx-peer'
[*] Waiting for remote peer connection and data channel...
```

#### Step 3: Start Peer A (Initiator Connect)
In a separate terminal window:
```powershell
crowdgpu-cli webrtc connect --peer-id demo-tx-peer --target-id demo-rx-peer --message "CrowdGPU P2P Direct WebRTC Test"
```
*Expected Output on Peer A (Initiator):*
```
[*] Starting WebRTC Initiator: 'demo-tx-peer' -> Target: 'demo-rx-peer'
[*] Coordinator Signaling: http://127.0.0.1:8000
[+] Registered with signaling gateway as 'demo-tx-peer'
[*] Dispatched SDP offer to 'demo-rx-peer'. Awaiting handshake...
[+] RTCDataChannel opened in 0.83s!
[*] RTCPeerConnection State: connected
[*] ICE Connection State:    completed
[*] Sending structured P2P payload directly over data channel...
[>] Dispatched message:
    - Request ID:     req-2d34ddb89d92
    - Payload SHA256: e697508c9d24e570e6833c3198469fd0acb62b01f7ed146774444be62826cb25
[<] Direct P2P Acknowledgement received in 1.0ms!
    - Response To:    req-2d34ddb89d92
    - Verified Hash:  e697508c9d24e570e6833c3198469fd0acb62b01f7ed146774444be62826cb25 (INTEGRITY MATCH)
    - Status:         verified
[+] Bi-directional WebRTC peer-to-peer data channel VERIFIED (Zero HTTP payload relay)!
[*] Initiator peer closed cleanly.
```

*Expected Output on Peer B (Receiver):*
```
[+] RTCDataChannel opened successfully with 'demo-tx-peer'!
[*] ICE Connection State: completed
[*] Listening for direct RTCDataChannel payloads (Press Ctrl+C to stop)...
[<] Direct P2P Message from 'demo-tx-peer':
    - Protocol:        crowdgpu-p2p/1.0
    - Request ID:      req-2d34ddb89d92
    - Type:            p2p_data_sync
    - SHA-256 Hash:    e697508c9d24e570e6833c3198469fd0acb62b01f7ed146774444be62826cb25 (VERIFIED)
    - Payload:         {'message': 'CrowdGPU P2P Direct WebRTC Test', 'session_nonce': '329b86fe', 'transport': 'WebRTC RTCDataChannel (Direct P2P)'}
[>] Direct P2P ACK dispatched over RTCDataChannel (Response To: req-2d34ddb89d92)
[*] Remote peer closed data channel or disconnected.
[*] Receiver peer closed cleanly.
```

### Verification of Zero HTTP Payload Relaying
1. Inspect the coordinator console / logs during the P2P transfer. The coordinator logs **only** WebSocket connection events and SDP / ICE candidate relay frames (`type="offer"`, `type="answer"`, `type="ice_candidate"`).
2. The application data (`message`, `session_nonce`, `req-2d34ddb89d92`, and SHA-256 ACK) is entirely absent from coordinator HTTP logs, proving direct data channel delivery.

### Known Limitations: NAT Traversal, STUN & TURN
- **Local Loopback & LAN Testing**: On local machines and local subnets, WebRTC host candidates (`typ host`) connect directly with sub-millisecond latencies.
- **Symmetric NATs**: When peers are behind strict enterprise firewalls or symmetric NATs, direct P2P hole-punching via public STUN servers may fail. In production WAN deployments, an external TURN relay server (e.g., Coturn) must be configured via environment variables.

---

## 8. Troubleshooting & Recovery Procedures

### 1. Port 8000 or 5173 Conflict
If a port is already in use from a prior session:
```powershell
# Identify processes using port 8000 or 5173
netstat -ano | findstr "8000 5173"

# Terminate process by PID (replace <PID> with output number)
taskkill /F /PID <PID>
```

### 2. Database Connectivity Failure
If coordinator fails with `OperationalError: connection to server on port 5432 failed`:
1. Check that PostgreSQL service is running:
   ```powershell
   Get-Service -Name "*postgres*"
   ```
2. Verify connectivity with credentials:
   ```powershell
   python -c "import psycopg2; conn = psycopg2.connect('postgresql://crowdgpu:changeme@localhost:5432/crowdgpu'); print('Connected'); conn.close()"
   ```

### 3. Worker Registration Fails (`Connection refused`)
If the worker logs show `Registration attempt 1/3 failed`:
- Ensure the Coordinator server in Terminal 1 is started **before** starting the Worker daemon.
- Verify `COORDINATOR_URL` is set to `http://127.0.0.1:8000`.

### 4. GPU / CUDA Unavailable
If PyTorch reports CUDA is unavailable (`torch.cuda.is_available() == False`):
- Verify NVIDIA driver installation using `nvidia-smi`.
- Confirm PyTorch is installed with CUDA support (`pip install torch --index-url https://download.pytorch.org/whl/cu121`).

---

## 9. Offline / Fallback Demonstration Mode

If presenting in an environment without access to a physical NVIDIA GPU or without a running PostgreSQL backend, the React frontend supports a complete **Mock Preview Mode**:

1. Edit `apps/web/.env.local`:
   ```ini
   VITE_USE_MOCK=true
   VITE_API_BASE_URL=
   ```
2. Restart Vite dev server:
   ```powershell
   cd "apps\web"
   npm run dev
   ```
3. Open `http://localhost:5173/`.
   - The UI simulates 7 provider peers (RTX 4090, A100 SXM4 80GB, RTX 3090, etc.) and full job lifecycle management using browser `sessionStorage`.
   - **Labeling Notice**: Clearly inform observers that *Mock Preview Mode* is enabled when running in this configuration.

---

## 10. Security, Reliability, and Deployment Hardening (Stage 6)

### 10.1 Security Controls Implemented

1. **Production Environment Safety Checks**:
   - In `coordinator/config.py`, setting `ENVIRONMENT=production` automatically triggers validation that:
     - `DEMO_AUTH_ENABLED` is strictly `False`.
     - Insecure secret keys containing `"changeme"` or `"secret"` are rejected on startup.
     - Insecure database URLs containing `"changeme"` or `"postgres:postgres"` are rejected on startup.

2. **Worker Identity & Anti-Impersonation**:
   - Workers send persistent peer identity headers (`X-Peer-Id` and `X-Worker-ID`).
   - The coordinator API (`coordinator/core/auth.py` and `coordinator/api/v1/workers.py`) enforces `verify_peer_authorization`:
     - A peer cannot poll jobs, send heartbeats, or post execution results for another registered peer ID (rejects with HTTP `403 Forbidden`).
     - Worker identities are verified against persistent database peer records.

3. **WebRTC Signaling Hardening**:
   - **HMAC Token Authentication**: In production (`SIGNALING_REQUIRE_TOKEN=true`), peers must present a deterministic HMAC-SHA256 signature generated with the coordinator's secret key (`/ws/signaling?peer_id=...&token=...`). Unauthenticated connections are closed immediately with code `1008 Policy Violation`.
   - **Rate Limiting**: Per-peer token bucket rate limiter enforces a maximum of 180 signaling messages per minute to prevent flooding and DoS.
   - **Bounds & Structure Validation**: SDP offer/answer strings (3..32,768 characters) and ICE candidates (3..2,048 characters) are verified prior to relay.
   - **Anti-Spoofing**: Outgoing message envelopes enforce `sender_id == authenticated_peer_id` and reject self-directed relays.
   - **Zero Sensitive Logging**: SDP session credentials and private candidate tokens are never dumped to server logs.

4. **Execution Isolation & Secrets Sanitization**:
   - In-process CUDA execution enforces strict allowlists (`matrix_multiply`, `vector_add`, `benchmark`) with validated numeric dimensions. Arbitrary shell commands are rejected.
   - Docker GPU execution enforces image prefix allowlists (`ALLOWED_IMAGE_PREFIXES`), command allowlists, read-only root filesystem, network isolation (`network_disabled=True`), and resource memory limits.
   - The worker's `sanitize_text` filter automatically masks database connection URLs (`postgresql://user:***@host`), tokens, and passwords from job error traces and `stdout_tail` before sending to the coordinator.

5. **Configuration & Deployment Hygiene**:
   - Root `.gitignore` excludes `.env`, `.env.local`, credentials, cache directories, and virtual environments.
   - Unified `.env.example` provides safe development placeholders.
   - Frontend environment variables (`VITE_*`) contain no server secrets or database passwords.
   - CORS origins are explicitly configurable via `CORS_ALLOWED_ORIGINS` (no credentialed wildcard origins).

### 10.2 Test Execution & Reconciled Counts

Run all automated test suites:
```powershell
# 1. Coordinator suite (from apps/coordinator)
cd "apps\coordinator"
pytest tests/ -v

# 2. Worker suite (from apps/worker)
cd "..\worker"
pytest tests/ -v

# 3. CLI suite (from apps/cli)
cd "..\cli"
pytest tests/ -v

# 4. Frontend lint and build (from apps/web)
cd "..\web"
npm run lint
npm run build
```

**Reconciled Test Results (Stage 6):**
| Suite | Passed | Skipped | Failed | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **Coordinator** | 131 | 6 | 0 | Multi-worker scheduling, signaling security, auth hardening |
| **GPU Worker** | 129 | 0 | 0 | CUDA executor, NVML detector, secrets sanitization |
| **CLI** | 24 | 0 | 0 | REST commands, WebRTC CLI, direct P2P data channel |
| **Total Python** | **284** | **6** | **0** | *Reconciled actual collected tests (Stage 5 math error resolved)* |
| **Web Frontend** | Pass | - | 0 | ESLint (0 errors, 0 warnings), Vite production build clean |

### 10.3 Clean-Start Demonstration Verification Status

| Stage 6 Requirement | Verification Method | Status |
| :--- | :--- | :--- |
| 1. PostgreSQL DB Start | Local Live Service | **VERIFIED** (Active on port 5432) |
| 2. Coordinator Health | Local Live Test | **VERIFIED** (`GET /health` -> `status: ok`) |
| 3. GPU Worker Registration | Local Live Service | **VERIFIED** (NVIDIA RTX 3050 Laptop GPU, 4096 MiB) |
| 4. Frontend Dashboard/Jobs | Local Live Test | **VERIFIED** (Vite dev server on port 5173, live REST proxy) |
| 5. CUDA Workload Execution | Local Live Test | **VERIFIED** (`matrix_multiply` completed in 0.034s on GPU) |
| 6. Result Verification | Local Live Test | **VERIFIED** (Accurate mean, std, and dimensions returned) |
| 7. CLI Peer/Job Inspection | Local Live Test | **VERIFIED** (`crowdgpu-cli peers list`, `jobs status`) |
| 8. WebRTC P2P Data Channel | Local Live Test | **VERIFIED** (Direct RTCDataChannel exchange, 1.2ms ACK, zero HTTP relay) |
| 9. Database & State Integrity | Local Live Test | **VERIFIED** (Coordinator restart retains peer/job records) |

### 10.4 Known Deployment Constraints & Future Work

1. **NAT Traversal & TURN Relays**: Direct P2P data channels are verified in local loopback and LAN environments. Symmetric NAT traversal requires testing against a provisioned Coturn TURN relay server.
2. **Docker Containment**: Local Docker execution provides best-effort resource throttling (read-only rootfs, no network), but is not a hardened multi-tenant virtualization boundary without kernel gVisor or Firecracker sandboxing.
3. **Production Authentication**: For multi-user enterprise deployments, integrate an OIDC / OAuth2 identity provider (e.g., Keycloak or Auth0) replacing the current header-based user token scheme.

