# CrowdGPU — Security Architecture, Hardening, and Limitations

**Document Purpose**: Comprehensive security audit, risk assessment, and operational boundary specification for the CrowdGPU academic release candidate.

---

## 1. Security Architecture & Threat Model

CrowdGPU coordinates compute jobs between arbitrary client users and distributed GPU provider worker nodes. The primary security objectives are:
1. **Tenant Isolation**: A user cannot inspect, cancel, alter, or hijack jobs belonging to another user.
2. **Worker Authenticity**: A worker node can only poll jobs assigned to it, report its own status, and submit results for jobs it was legitimately scheduled to execute.
3. **Execution Safety**: Untrusted users cannot execute arbitrary system shell commands or escape container boundaries on provider machines.
4. **Signaling Integrity**: Attackers cannot flood the WebRTC signaling gateway, forge SDP descriptions, impersonate other peers, or snoop on private data channels.
5. **Configuration Hygiene**: Secrets and sensitive connection strings must never leak to logs, client bundles, or version control.

---

## 2. Implemented Security Controls

### 2.1 Identity Authentication & Anti-Impersonation

| Identity Type | Mechanism | Implementation Details |
| :--- | :--- | :--- |
| **Worker Identity** | Deterministic HMAC-SHA256 Token | On registration (`POST /api/v1/workers/register`), coordinator returns `peer_token = HMAC(secret_key, "worker-auth:" + peer_id)`. The worker client caches this token and sends `X-Peer-Token` and `Authorization: Bearer <token>` on all requests. In production, requests without a valid matching token are rejected with HTTP 401/403. |
| **User Identity** | Deterministic HMAC-SHA256 Token | Generated via `HMAC(secret_key, "user-auth:" + user_id)`. In production, plain `X-User-Id` header spoofing without the corresponding HMAC token is rejected with HTTP 401/403. |
| **Signaling Identity** | Deterministic HMAC-SHA256 Token | WebSockets connecting to `/ws/signaling?peer_id=...&token=...` must present `HMAC(secret_key, peer_id)`. Unauthenticated handshakes are terminated immediately with close code `1008 Policy Violation`. |
| **Cross-User Protection** | Owner Scoping in ORM Queries | `JobService.get_job` and `cancel_job` query by `(Job.id == job_id, Job.owner_id == caller_id)`. Attempting to access another user's job returns HTTP 404 (JobNotFoundError), completely concealing the existence of foreign workloads. |
| **Peer Hijacking Protection** | Ownership Validation on Registration | Re-registering an existing `peer_id` verifies `existing_peer.owner_id == data.owner_id`. Cross-user hijacking attempts raise `UnauthorizedPeerError` returning HTTP 403 Forbidden. |

### 2.2 Production Configuration Safety

The Coordinator configuration ([apps/coordinator/coordinator/config.py](file:///c:/Users/prana/OneDrive/Desktop/crowdgpu%20integrated/apps/coordinator/coordinator/config.py)) implements a strict `@model_validator`:
- **Demo Auth Ban**: When `ENVIRONMENT=production`, setting `DEMO_AUTH_ENABLED=True` raises a startup `ValidationError`.
- **Default Key Ban**: When `ENVIRONMENT=production`, setting `SECRET_KEY` to any value containing `"changeme"` or `"secret"` halts startup.
- **Default Database Password Ban**: When `ENVIRONMENT=production`, setting `DATABASE_URL` containing `"changeme"` or `"postgres:postgres"` halts startup.
- **CORS Restrictions**: `CORSMiddleware` allows only explicitly configured origins in `CORS_ALLOWED_ORIGINS` (defaulting to local Vite and dev ports). Wildcard origins (`*`) are prohibited when supporting credentials.

### 2.3 WebRTC Signaling Hardening

The WebSocket signaling gateway ([apps/coordinator/coordinator/signaling/router.py](file:///c:/Users/prana/OneDrive/Desktop/crowdgpu%20integrated/apps/coordinator/coordinator/signaling/router.py)) enforces:
1. **Token Verification**: Handshakes are validated prior to accepting the connection.
2. **Anti-Spoofing**: Outgoing envelopes force `sender_id = authenticated_peer_id`.
3. **Anti-Self-Relay**: Relaying messages to one's own peer ID is rejected.
4. **Token-Bucket Rate Limiting**: Per-peer rate limiter caps signaling traffic at 180 messages per minute. Excess frames receive error code `RATE_LIMITED`.
5. **Payload Bounds Validation**:
   - SDP offer/answer text: 3 to 32,768 characters.
   - ICE candidate string: 3 to 2,048 characters.
6. **Zero Content Logging**: Session tokens and SDP crypto parameters are omitted from server console logs.

### 2.4 GPU Workload Execution Isolation

The Worker executor ([apps/worker/worker/executor/](file:///c:/Users/prana/OneDrive/Desktop/crowdgpu%20integrated/apps/worker/worker/executor/)) implements two execution layers:

1. **In-Process CUDA Workloads (Default)**:
   - Untrusted shell execution (`shell=True`, `eval`, or arbitrary subprocesses) is strictly prohibited.
   - Supported compute routines are restricted to a verified allowlist: `matrix_multiply`, `vector_add`, and `benchmark`.
   - Workload parameters (matrix dimensions, vector lengths) are clamped to prevent physical GPU out-of-memory crashes.
   - A 256 MiB safety margin is reserved for system GPU buffers.

2. **Docker GPU Execution (Optional Isolation)**:
   - When configured with `EXECUTION_BACKEND=docker`, the worker runs workloads inside isolated containers.
   - Image allowlist: `ALLOWED_IMAGE_PREFIXES` restricts container images.
   - Runtime security flags:
     - `read_only=True`: Root filesystem mounted read-only.
     - `network_disabled=True`: Zero network access from inside the workload.
     - Memory limits: Containers constrained to configured RAM limits.
     - Finite timeout: Containers are terminated after `job_timeout_seconds`.

3. **Secrets Sanitization**:
   - The worker's `sanitize_text()` filter scans all stdout tails and stack traces before reporting to the coordinator.
   - Database connection strings (`postgresql://user:***@host`), passwords, and API tokens are masked with `***`.

---

## 3. Deployment Hygiene & Repository Audit

- **Environment Files**: Root `.env.example` provides safe development placeholders. Live `.env` and `.env.local` files are ignored via `.gitignore` and never committed.
- **Frontend Variables**: No sensitive backend secrets, signing keys, or database passwords are exposed via `VITE_*` variables.
- **Database Safety**: Database migrations are managed through canonical Alembic revisions. Production operations never drop or truncate tables.

---

## 4. Operational Boundaries & Known Limitations

For academic review, the following boundaries and limitations are explicitly noted:

### 1. Docker Containment is Not a MicroVM Boundary
- *Current Design*: Docker containerization provides filesystem isolation and resource limits.
- *Limitation*: Container processes share the host Linux or Windows kernel. In an adversarial multi-tenant public network, container escapes (e.g. via kernel vulnerabilities) are possible. Production enterprise deployments require microVM virtualization (e.g. AWS Firecracker or gVisor).

### 2. NAT Traversal & STUN/TURN Dependency
- *Current Design*: WebRTC peer-to-peer data channels function seamlessly over local loopback and LAN host candidates (`typ host`).
- *Limitation*: When peers reside behind symmetric NATs or strict enterprise firewalls, direct UDP hole-punching fails. External WAN operation requires provisioning a dedicated TURN relay server (such as Coturn).

### 3. Prototype Token Scheme vs Enterprise OIDC
- *Current Design*: Uses deterministic HMAC-SHA256 tokens signed with `settings.secret_key` for user, worker, and signaling authentication.
- *Limitation*: Tokens are generated from a single shared secret key on the coordinator. For large-scale multi-organization deployments, an industry-standard OAuth2/OIDC identity provider (e.g. Keycloak or Auth0) with asymmetric RSA/ECDSA key pairs and token expiration/refresh rotation should be integrated.

### 4. Single-Coordinator Topology
- *Current Design*: Single FastAPI coordinator instance backed by PostgreSQL.
- *Limitation*: High-availability coordinator clustering with distributed leader election is not implemented in this release candidate.
