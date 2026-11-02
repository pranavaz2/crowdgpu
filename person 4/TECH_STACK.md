# CrowdGPU — Technology Stack

## 1. Document Information

**Project:** CrowdGPU  
**Document:** Technology Stack Specification  
**Status:** Baseline

This document defines the technologies selected for the current CrowdGPU architecture, their responsibilities, boundaries, and intended usage.

Technology choices must remain consistent with:

- `PRD.md`
- `REQUIREMENTS.md`
- `ARCHITECTURE.md`
- `ARCHITECTURE_DECISIONS.md`

New technologies should not be introduced without a documented reason.

---

# 2. Technology Stack Overview

| Layer | Technology | Primary Responsibility |
|---|---|---|
| Web Frontend | React | User interface |
| Frontend Tooling | Vite | Development/build tooling |
| Styling | Tailwind CSS | UI styling |
| Coordinator Backend | Python | Core backend language |
| API Framework | FastAPI | REST/API layer |
| Validation | Pydantic | Request/response/data validation |
| Real-Time Communication | WebSockets | Telemetry, status and signaling |
| Task Queue | Celery | Background task execution |
| Message Broker / Ephemeral State | Redis | Queue/broker/transient coordination |
| Database | PostgreSQL | Persistent relational state |
| ORM / DB Access | SQLAlchemy | Database access layer |
| Database Migrations | Alembic | Schema migrations |
| Worker Daemon | Python | Provider-side orchestration |
| GPU Monitoring | PyNVML / NVIDIA NVML | GPU telemetry |
| GPU Compute | CUDA | NVIDIA GPU runtime |
| GPU Framework | PyTorch | Deep-learning workloads |
| GPU Container Runtime | NVIDIA Container Toolkit | GPU passthrough |
| Sandbox | Docker | Workload isolation |
| Provider Environment | WSL2 | Windows Linux execution environment |
| P2P Transport | WebRTC | Direct peer communication |
| NAT Traversal | STUN | NAT discovery |
| Relay | TURN / Coturn | Connectivity fallback |
| Video Encoding | NVIDIA NVENC | Hardware video encoding |
| Video Decoding | NVIDIA NVDEC | Hardware video decoding where required |
| Remote Rendering | WebRTC Media | Interactive streaming |
| Rendering Engine | Blender CLI | Headless 3D rendering where applicable |
| Monitoring | Prometheus | Metrics collection |
| Dashboards | Grafana | Metrics visualization |
| Infrastructure | Docker Compose | Local development orchestration |
| Version Control | Git | Source control |
| Repository Hosting | GitHub | Collaboration and CI |
| Testing | Pytest / appropriate frontend tooling | Automated testing |

---

# 3. Frontend Stack

## 3.1 React

**Role:** Main web application framework.

Responsibilities:

- Dashboard
- Job submission
- Job monitoring
- Peer/resource visualization
- Result retrieval
- Remote rendering interface
- Authentication UI
- Error/loading/empty states

React should contain presentation and client-side interaction logic.

Business rules that belong to the coordinator must not be duplicated inside the frontend.

---

## 3.2 Vite

**Role:** Frontend development and build tooling.

Responsibilities:

- Local development server
- Frontend build
- Development-time module handling
- Production asset generation

Vite should remain a tooling concern and should not be coupled to backend business logic.

---

## 3.3 Tailwind CSS

**Role:** Frontend styling system.

Responsibilities:

- Layout
- Responsive design
- Component styling
- Consistent visual system

The project should establish reusable UI patterns rather than scattering arbitrary styles throughout components.

---

# 4. Backend Stack

## 4.1 Python

**Role:** Primary coordinator and worker implementation language.

Reason:

- FastAPI ecosystem
- PyTorch
- NVML/PyNVML
- scheduling research
- scientific computing ecosystem
- machine-learning integration

Python is the primary language for the control plane and worker daemon.

---

## 4.2 FastAPI

**Role:** Main Coordinator API framework.

Responsibilities:

- REST APIs
- authentication endpoints
- job endpoints
- peer endpoints
- result endpoints
- administrative/control endpoints where required
- WebSocket endpoints

FastAPI should remain the primary HTTP application boundary.

---

## 4.3 Pydantic

**Role:** Data validation and serialization.

Responsibilities:

- API request schemas
- API response schemas
- job metadata validation
- worker messages
- configuration models
- internal DTO validation where useful

Pydantic models should be treated as explicit contracts.

---

# 5. Real-Time Communication

## 5.1 WebSockets

**Role:** Persistent bidirectional application communication.

Primary uses:

- Worker heartbeat
- Worker telemetry
- Job state updates
- Real-time client updates
- WebRTC signaling

WebSockets are not a replacement for WebRTC.

They are primarily part of the CrowdGPU control/signaling plane.

---

# 6. Background Task Processing

## 6.1 Celery

**Role:** Background task execution.

Potential uses:

- asynchronous job processing
- result processing
- verification jobs
- accounting jobs
- cleanup tasks
- scheduled background operations

Long-running or asynchronous operations should not unnecessarily block HTTP request handlers.

---

## 6.2 Redis

**Role:**

- Celery broker
- transient coordination state
- temporary locks
- pub/sub where useful
- caching where appropriate

Redis is not the authoritative database for CrowdGPU business state.

Persistent state belongs in PostgreSQL.

---

# 7. Database Stack

## 7.1 PostgreSQL

**Role:** Primary persistent relational database.

Expected persistent domains include:

```text
users
peers
gpu_capabilities
jobs
job_attempts
sessions
results
verification_records
credit_transactions
reputation_records
```