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

The initial database schema contains three core entities:

```text
users
   │
   │ 1:N
   ▼
peers
   │
   │ 1:N
   ▼
gpu_capabilities