# CrowdGPU — Development Environment Specification

## 1. Document Information

**Project:** CrowdGPU  
**Document:** Development Environment Specification  
**Status:** Baseline

This document defines the development environment required to build, test and run CrowdGPU consistently.

It complements:

- `PRD.md`
- `REQUIREMENTS.md`
- `ARCHITECTURE.md`
- `ARCHITECTURE_DECISIONS.md`
- `TECH_STACK.md`
- `REPOSITORY_STRUCTURE.md`

The goal is reproducible development across team members and AI coding agents.

---

# 2. Development Environment Goals

The development environment must:

- be reproducible
- minimize "works on my machine" problems
- separate infrastructure from application development
- support the NVIDIA GPU Worker environment
- support backend and frontend development
- support automated testing
- support local observability
- allow the project to be developed incrementally

---

# 3. Supported Development Platforms

## 3.1 Primary Developer Platform

The primary development environment is:

```text
Windows 11