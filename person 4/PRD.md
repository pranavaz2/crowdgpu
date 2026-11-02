# CrowdGPU — Product Requirements Document (PRD)

## 1. Product Information

**Product Name:** CrowdGPU

**Full Name:** CrowdGPU: Intelligent Peer-to-Peer Distributed GPU Resource Sharing Platform

**Project Type:** Academic Main Project / Distributed Systems / GPU Computing / P2P Computing

---

## 2. Product Vision

CrowdGPU is a peer-to-peer GPU resource-sharing platform designed to connect users requiring GPU compute with available consumer GPU resources.

The platform supports two primary workload categories:

1. Batch / distributed GPU computing
2. Interactive remote GPU rendering

CrowdGPU combines centralized coordination for peer discovery, matchmaking, scheduling, signaling, trust and accounting with peer-to-peer execution, data transfer and media communication where appropriate.

The ultimate goal is to securely utilize otherwise underused consumer GPU resources for useful computational workloads while providing users with access to GPU computing without requiring dedicated high-end hardware.

---

## 3. Problem Statement

High-performance GPU computing is increasingly required for deep learning, scientific workloads, rendering and other compute-intensive applications.

However:

- High-end GPUs and commercial cloud GPU instances can be expensive.
- Consumer GPUs may remain significantly underutilized.
- Existing remote desktop and streaming systems primarily focus on interactive remote access.
- Traditional schedulers such as Slurm and Kubernetes are primarily designed for centralized cluster environments.
- Heterogeneous consumer GPUs make resource selection and workload scheduling difficult.
- Residential networks introduce NAT traversal and connectivity challenges.
- Untrusted workloads create host security and isolation concerns.
- Distributed workloads can suffer from network latency and resource contention.
- A unified P2P platform combining batch GPU computing and low-latency interactive rendering is needed.

CrowdGPU addresses this gap through an intelligent peer-to-peer GPU resource-sharing architecture.

---

## 4. Target Users

### 4.1 GPU Consumer

A user who requires access to GPU resources.

Potential use cases include:

- Deep learning experimentation
- Academic research
- Machine learning workloads
- 3D rendering
- Game development workloads
- Remote GPU-powered applications

### 4.2 GPU Provider

A user who owns a compatible GPU and chooses to contribute available GPU resources to the CrowdGPU network.

The provider should be able to:

- Register the GPU
- Monitor resource usage
- Allow controlled workloads to execute
- Provide remote rendering sessions
- Receive compute contribution credits
- Build reputation based on successful contribution

---

## 5. System Actors

| Actor | Responsibility |
|---|---|
| Consumer | Submit GPU workloads and request remote sessions |
| Provider | Contribute GPU resources |
| Central Coordinator | Discovery, matchmaking, scheduling, signaling, trust and accounting |
| Worker Daemon | GPU telemetry, execution, sandboxing and streaming |
| Monitoring System | Metrics, telemetry and operational visibility |

---

# 6. Product Goals

CrowdGPU has five primary goals.

## Goal 1 — P2P Network and Discovery

Establish a peer network capable of discovering available GPU resources and creating secure peer-to-peer connections.

## Goal 2 — Heterogeneity-Aware Scheduling

Match workloads with suitable peer GPUs based on:

- GPU capability
- VRAM
- Availability
- Network quality
- Workload requirements
- Resource contention where applicable

## Goal 3 — Secure Containerized Execution

Run guest workloads inside isolated execution environments with controlled:

- CPU
- RAM
- GPU
- Disk
- Privileges

## Goal 4 — Low-Latency Remote Rendering

Provide interactive remote access to GPU-powered applications using WebRTC and hardware-accelerated video encoding.

## Goal 5 — Verification and Accounting

Verify workload outputs and track provider contribution through credits and reputation.

---

# 7. Product Scope

CrowdGPU consists of the following major subsystems:

1. Client Portal & CLI
2. Central Coordinator
3. Peer Matchmaker
4. Heterogeneity-Aware Scheduler
5. Signaling Gateway
6. Trust & Accounting subsystem
7. Host Worker Daemon
8. Hardware Monitor
9. Container Sandbox Engine
10. Local Task Executor
11. NVENC Streaming Daemon
12. P2P/WebRTC networking
13. Output Verification
14. PostgreSQL persistence
15. Monitoring and observability infrastructure

---

# 8. High-Level Architecture

The architecture follows a control-plane / execution-plane separation.

## 8.1 Client Layer

The client layer contains:

- React Web Portal
- Python CLI / SDK
- Interactive WebRTC Client
- Output Verification Client

Responsibilities:

- Submit workloads
- Request remote sessions
- Display job/session state
- Display logs
- Retrieve results
- Verify results

---

## 8.2 Central Coordinator

The coordinator acts as the control-plane brain of CrowdGPU.

Responsibilities:

### Peer Matchmaker

Maintains a live catalog of:

- registered peers
- GPU capabilities
- availability
- health state
- resource information

### Signaling Gateway

Coordinates:

- WebRTC SDP offer/answer exchange
- ICE candidate exchange
- session negotiation

### Heterogeneity Scheduler

Selects suitable GPUs based on:

- VRAM
- compute capability
- availability
- network characteristics
- workload requirements
- resource-sharing constraints

### Trust & Accounting

Tracks:

- compute contribution
- job completion
- verification state
- peer reputation
- internal credits

---

# 9. Host Worker Daemon

Every provider machine runs a CrowdGPU Worker Daemon.

The worker contains:

## 9.1 Hardware Monitor

Uses NVIDIA NVML / PyNVML to collect:

- GPU model
- driver information
- total VRAM
- free VRAM
- GPU utilization
- temperature
- power
- health information

Target telemetry interval:

**2 seconds**

## 9.2 Container Sandbox Engine

Responsible for:

- creating isolated execution environments
- GPU passthrough
- CPU limits
- RAM limits
- GPU resource limits
- disk I/O restrictions
- non-root execution

## 9.3 Local Task Executor

Responsible for:

- receiving job instructions
- obtaining the job package
- starting execution
- monitoring execution
- collecting results
- reporting completion/failure

## 9.4 NVENC Streaming Daemon

Responsible for:

- screen/application capture
- hardware video encoding
- WebRTC media streaming
- session lifecycle

---

# 10. Two Primary Execution Modes

CrowdGPU has two distinct operational modes.

---

## 10.1 Batch Compute Mode

### Workflow

```text
Consumer
    ↓
Submit Job
    ↓
Central Coordinator
    ↓
Capability Filtering
    ↓
Peer Matching
    ↓
Scheduling
    ↓
P2P / Job Dispatch
    ↓
Worker Daemon
    ↓
Container Sandbox
    ↓
GPU Execution
    ↓
Output
    ↓
Verification
    ↓
Result Retrieval
    ↓
Accounting / Reputation