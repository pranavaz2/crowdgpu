# CrowdGPU — Final Demonstration Runbook (Stage 7 Release Candidate)

This runbook provides the definitive, step-by-step instructions for conducting an academic evaluation and live demonstration of **CrowdGPU**.

---

## 1. System Prerequisites

- **Operating System**: Windows 10/11 or Ubuntu Linux 22.04+
- **Python Runtime**: Python 3.11.x (with `torch` CUDA 12.1+ support)
- **Node.js**: v18.0.0+ / npm v9.0.0+
- **Database**: PostgreSQL 15+ running on port `5432` with database `crowdgpu`
- **NVIDIA GPU**: Physical CUDA-capable GPU (tested on NVIDIA GeForce RTX 3050 Laptop GPU, driver 591.91)
- **Network**: Local loopback (`127.0.0.1` / `localhost`)

---

## 2. Environment Setup

### 2.1 Database Verification
Ensure PostgreSQL is active and accessible:
```powershell
python -c "import psycopg2; conn = psycopg2.connect('postgresql://crowdgpu:changeme@127.0.0.1:5432/crowdgpu'); print('PostgreSQL connection verified'); conn.close()"
```

### 2.2 Environment Files
- Ensure `apps/web/.env.local` contains:
  ```ini
  VITE_USE_MOCK=false
  VITE_API_BASE_URL=
  VITE_DEMO_USER_ID=00000000-0000-0000-0000-000000000001
  ```
- Safe reference environment variables are provided in [.env.example](file:///c:/Users/prana/OneDrive/Desktop/crowdgpu%20integrated/.env.example).

---

## 3. Live Demonstration Sequence

### Step 1: Start the Coordinator (Terminal 1)
```powershell
cd "apps\coordinator"
python -m uvicorn coordinator.main:app --host 127.0.0.1 --port 8000
```
*Expected Output:*
```
INFO:coordinator.main:CrowdGPU Coordinator starting up
INFO:coordinator.database.session:Database connection pool established
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Verify health in a separate terminal:
```powershell
curl -s http://127.0.0.1:8000/health
# Response: {"status": "ok", "version": "0.1.0"}
```

---

### Step 2: Start the Physical GPU Worker Daemon (Terminal 2)
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
[INFO] worker.gpu.detector — GPU detected: NVIDIA GeForce RTX 3050 Laptop GPU — 4096 MiB VRAM
[INFO] worker.coordinator.client — Registering with Coordinator: http://127.0.0.1:8000/api/v1/workers/register
[INFO] worker.coordinator.client — Registration successful (assigned peer_id=..., token_set=True)
[INFO] worker.state — WorkerState.AVAILABLE
[INFO] worker.worker — Worker is AVAILABLE and ready for jobs.
```

---

### Step 3: Launch the React Web Portal (Terminal 3)
```powershell
cd "apps\web"
npm run dev
```
Open browser at `http://localhost:5173/`:
1. **Peers View**: Confirm the physical NVIDIA RTX 3050 peer is listed as `AVAILABLE` with 4096 MiB VRAM.
2. **Jobs View**: Submit a workload using the preset `matrix_multiply` (CUDA Matrix Multiplication).
3. **Execution**: Observe the job transition: `QUEUED` $\rightarrow$ `ASSIGNED` $\rightarrow$ `RUNNING` $\rightarrow$ `COMPLETED`.
4. **Results**: Click on the completed job card to view genuine execution time, tensor mean, standard deviation, and output shape `[1024, 1024]`.

---

### Step 4: CLI Inspection and Job Submission (Terminal 4)
Verify coordinator health and list registered peers:
```powershell
crowdgpu-cli health
crowdgpu-cli peers list
```

Submit a CUDA matrix multiplication job via CLI:
```powershell
crowdgpu-cli jobs submit --preset matrix_multiply
```
*Expected Output:*
```
[+] Job submitted successfully!
Job ID:        <JOB_UUID>
Name:          CUDA Matrix Multiplication
Status:        ASSIGNED
Assigned Peer: <PEER_UUID>
```

Inspect the job status and execution result:
```powershell
crowdgpu-cli jobs status <JOB_UUID>
```
*Expected Output:*
```
=== Job Details ===
Status:        COMPLETED
GPU Hardware:  NVIDIA GeForce RTX 3050 Laptop GPU
Duration:      0.0325s
Output Data:
    device: cuda:0
    output:
      matrix_dim: 1024
      result_std: 32.07
      result_shape: [1024, 1024]
    success: True
    workload_type: matrix_multiply
    execution_time_s: 0.0088s
```

---

### Step 5: WebRTC Direct Peer-to-Peer Data Channel Demo

Open two dedicated terminal windows to demonstrate direct browser/node WebRTC communication:

**In Terminal A (Receiver Peer):**
```powershell
crowdgpu-cli webrtc listen --peer-id demo-rx-peer --timeout 15
```
*Receiver waits for remote connection:*
```
[*] Starting WebRTC Receiver Peer: 'demo-rx-peer'
[+] Registered with signaling gateway as 'demo-rx-peer'
[*] Waiting for remote peer connection and data channel...
```

**In Terminal B (Initiator Peer):**
```powershell
crowdgpu-cli webrtc connect --peer-id demo-tx-peer --target-id demo-rx-peer --message "CrowdGPU Academic Demonstration"
```
*Initiator negotiates and exchanges payload:*
```
[+] Registered with signaling gateway as 'demo-tx-peer'
[*] Dispatched SDP offer to 'demo-rx-peer'. Awaiting handshake...
[+] RTCDataChannel opened in 0.79s!
[*] Sending structured P2P payload directly over data channel...
[<] Direct P2P Acknowledgement received in 1.2ms!
    - Verified Hash: <SHA-256> (INTEGRITY MATCH)
    - Status: verified
[+] Bi-directional WebRTC peer-to-peer data channel VERIFIED (Zero HTTP payload relay)!
```

---

### Step 6: Security & Isolation Verification

1. **Cross-User Protection**: Attempt to inspect another user's job:
   ```powershell
   crowdgpu-cli --user-id 99999999-9999-9999-9999-999999999999 jobs status <JOB_UUID>
   # Output: Error: Job '<JOB_UUID>' not found. (HTTP 404 tenant isolation)
   ```
2. **Resource Constraint Handling**: Submit an oversized job (e.g., 100,000 MiB VRAM):
   ```powershell
   crowdgpu-cli jobs submit --name "Huge VRAM Job" --command "benchmark" --vram 100000
   # Status remains QUEUED because no peer can satisfy requirement.
   ```
3. **Job Cancellation**: Cancel the queued job:
   ```powershell
   crowdgpu-cli jobs cancel <HUGE_JOB_UUID>
   # Status transitions to CANCELLED.
   ```
4. **Coordinator Restart Recovery**:
   - Terminate the coordinator process in Terminal 1 (Ctrl+C).
   - Observe worker daemon in Terminal 2 retrying connections gracefully without crashing.
   - Restart coordinator in Terminal 1.
   - Observe worker automatically reconnecting and dispatching heartbeats within 5 seconds.

---

---

## 4. Multi-Machine LAN Demonstration (Two-Computer Setup)

When two physical computers are available on the same trusted local area network, use this procedure to validate genuine distributed execution.

```
[ Computer B: Remote GPU Worker ]                [ Computer A: Coordinator & Host ]
   IP: 10.131.126.x                                 IP: 10.131.126.15
   │                                                │
   ├── REST Heartbeats / Polls (Port 8000) ───────▶ ├── Coordinator (Uvicorn 0.0.0.0:8000)
   ├── WebRTC Signaling (ws://...:8000) ──────────▶ ├── PostgreSQL 16 (127.0.0.1:5432 ONLY)
   │                                                └── Web Portal (Port 5173, optional)
   └── WebRTC DataChannel (Direct P2P UDP) ◀──────▶ (Direct P2P payload exchange)
```

### 4.1 Safe LAN Preparation on Computer A (Coordinator Host)

1. **Identify LAN IP Address**:
   ```powershell
   ipconfig
   # Identify your IPv4 Address (e.g. 10.131.126.15)
   ```

2. **Configure Windows Firewall (Restrict to Private Subnet)**:
   Allow port 8000 TCP traffic only from your trusted local subnet:
   ```powershell
   New-NetFirewallRule -DisplayName "CrowdGPU Coordinator LAN" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -RemoteAddress "10.131.126.0/24"
   ```
   > [!IMPORTANT]
   > Do **NOT** open port 5432 (PostgreSQL) to the network. The coordinator connects to PostgreSQL over `127.0.0.1:5432`; the database must remain completely inaccessible from the external LAN.

3. **Start Coordinator Bound to LAN Interface**:
   ```powershell
   cd "apps\coordinator"
   python -m uvicorn coordinator.main:app --host 0.0.0.0 --port 8000
   ```
   Verify health check from another shell or browser:
   ```powershell
   curl -s http://10.131.126.15:8000/health
   # Response: {"status": "ok", "version": "0.1.0"}
   ```

---

### 4.2 Worker Setup on Computer B (Remote GPU Worker)

1. **Verify Connectivity to Computer A**:
   From Computer B's terminal:
   ```powershell
   curl -s http://10.131.126.15:8000/health
   ```

2. **Start the Remote Worker Daemon**:
   Set `COORDINATOR_URL` to Computer A's LAN IP:
   ```powershell
   cd "apps\worker"
   $env:COORDINATOR_URL='http://10.131.126.15:8000'
   $env:WORKER_ID='remote-b-gpu-worker'
   $env:GPU_ID='0'
   $env:HEARTBEAT_INTERVAL='5'
   $env:POLL_INTERVAL='1.0'
   python -m worker.worker
   ```
   *Expected Output on Computer B:*
   ```
   [INFO] worker.gpu.detector — GPU detected: NVIDIA GeForce RTX ... — ... MiB VRAM
   [INFO] worker.coordinator.client — Registering with Coordinator: http://10.131.126.15:8000/api/v1/workers/register
   [INFO] worker.coordinator.client — Registration successful (assigned peer_id=..., token_set=True)
   [INFO] worker.state — WorkerState.AVAILABLE
   ```

---

### 4.3 Distributed Job Execution from Computer A

1. **Submit Job Targeting Computer B**:
   From Computer A (or Computer B CLI):
   ```powershell
   python -m cli.main --coordinator-url http://10.131.126.15:8000 jobs submit --preset matrix_multiply --name "lan-remote-execution"
   ```
2. **Observe Real Remote Execution**:
   - The coordinator assigns the job to Computer B's worker UUID.
   - Computer B's worker logs show:
     ```
     [INFO] worker.coordinator.client — Job claimed from Coordinator: id=...
     [INFO] worker.executor.cuda_executor — Executing CUDA workload: type=matrix_multiply device=cuda:0
     [INFO] worker.executor.cuda_executor — CUDA workload done: elapsed=...s
     [INFO] worker.coordinator.client — Posting result for job ... (status=success)
     ```
   - Execution occurs solely on Computer B's GPU.
3. **Verify Result Retrieval**:
   ```powershell
   python -m cli.main --coordinator-url http://10.131.126.15:8000 jobs status <JOB_UUID>
   ```

---

### 4.4 WebRTC Direct Data Channel over LAN

Demonstrate direct P2P data exchange between Computer A and Computer B without relaying data through HTTP:

1. **On Computer B (Receiver)**:
   ```powershell
   cd "apps\cli"
   python -m cli.main --coordinator-url http://10.131.126.15:8000 webrtc listen --peer-id computer-b-rx
   ```

2. **On Computer A (Initiator)**:
   ```powershell
   cd "apps\cli"
   python -m cli.main --coordinator-url http://10.131.126.15:8000 webrtc connect --peer-id computer-a-tx --target-id computer-b-rx --message "CrowdGPU Multi-Machine LAN Direct Payload"
   ```

3. **Observed Outcome**:
   - WebSocket signaling negotiates SDP offer/answer through Computer A coordinator (`ws://10.131.126.15:8000/api/v1/signaling/ws`).
   - `RTCPeerConnection` connects directly across LAN using host ICE candidates.
   - Direct `RTCDataChannel` delivers payload and receives SHA-256 verified ACK in < 5ms.

---

### 4.5 Reverting to Single-Machine Loopback Configuration

When the multi-machine test concludes, safely revert back to local development mode:

1. Stop Uvicorn on Computer A (`Ctrl+C`).
2. Remove the temporary Windows Firewall rule:
   ```powershell
   Remove-NetFirewallRule -DisplayName "CrowdGPU Coordinator LAN"
   ```
3. Restart the Coordinator bound strictly to `127.0.0.1`:
   ```powershell
   python -m uvicorn coordinator.main:app --host 127.0.0.1 --port 8000
   ```
4. Reset `COORDINATOR_URL` on local workers to `http://127.0.0.1:8000`.

---

## 5. Orderly Shutdown Sequence

1. **Web Portal**: Press `Ctrl+C` in Terminal 3.
2. **GPU Worker**: Press `Ctrl+C` in Terminal 2. The worker catches `SIGINT` and transitions `AVAILABLE` $\rightarrow$ `OFFLINE`.
3. **Coordinator**: Press `Ctrl+C` in Terminal 1. The coordinator closes database connections cleanly.
4. **PostgreSQL**: Leave running or stop service if maintenance is needed.

---

## 6. Troubleshooting Guide

| Issue | Cause | Resolution |
| :--- | :--- | :--- |
| **Port 8000 Conflict** | Stale coordinator or python process running | `netstat -ano \| findstr :8000` to find PID, then `taskkill /F /PID <PID>`. |
| **Database Connection Refused** | PostgreSQL service stopped | Run `Get-Service -Name "*postgres*"` and start service in Windows Services manager. |
| **Worker Registration Error** | Coordinator not started or wrong URL | Ensure Coordinator in Terminal 1 is started before starting Worker. |
| **CUDA Not Detected** | Missing NVIDIA driver or CPU PyTorch | Verify `nvidia-smi` and confirm `torch.cuda.is_available() == True`. |
| **LAN Connection Timed Out** | Windows Firewall blocking port 8000 | Verify firewall rule on Computer A (`Get-NetFirewallRule -DisplayName "*CrowdGPU*"`). |
| **PostgreSQL Exposed Warning** | Port 5432 listening on external interface | Check `netstat -an \| findstr 5432`. Ensure local address is `127.0.0.1:5432` or `localhost`. |

