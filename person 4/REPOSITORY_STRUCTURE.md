# CrowdGPU — Repository Structure & Development Environment

## 1. Document Information

**Project:** CrowdGPU  
**Document:** Repository Structure Specification  
**Status:** Baseline

This document defines the repository organization, component boundaries, development environments, shared contracts, infrastructure layout, testing locations, and rules for AI coding agents.

The repository structure must remain consistent with:

- `PRD.md`
- `REQUIREMENTS.md`
- `ARCHITECTURE.md`
- `ARCHITECTURE_DECISIONS.md`
- `TECH_STACK.md`

---

# 2. Repository Architecture

CrowdGPU will use a **modular monorepo**.

The repository separates runtime applications, shared contracts, infrastructure, research code, tests, scripts, and documentation.

High-level structure:

```text
crowdgpu/
│
├── apps/
│   ├── coordinator/
│   ├── worker/
│   ├── web/
│   └── cli/
│
├── packages/
│   └── shared/
│
├── infrastructure/
│   ├── docker/
│   ├── postgres/
│   ├── redis/
│   ├── turn/
│   └── monitoring/
│
├── research/
│
├── tests/
│
├── scripts/
│
├── docs/
│
├── .github/
│
├── .env.example
├── .gitignore
├── docker-compose.yml
├── README.md
└── ...