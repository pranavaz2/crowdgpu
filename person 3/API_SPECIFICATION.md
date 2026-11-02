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
- future integrations

The initial API architecture is:

```text
Web Client
     │
     │ REST / WebSocket
     ▼
┌────────────────────────┐
│   CrowdGPU Coordinator │
│                        │
│ API / Application      │
│ Services               │
│ Database Layer         │
└────────────┬───────────┘
             │
             ▼
        PostgreSQL