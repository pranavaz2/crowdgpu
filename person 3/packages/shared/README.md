# crowdgpu-shared

Cross-application shared contracts for the CrowdGPU platform.

**Status: Bootstrap phase** — Package structure created. No shared business
contracts have been added yet.

This package will provide shared Pydantic models, type aliases, and constants
that are used by both the coordinator and worker. Adding shared logic here
avoids duplication and ensures consistent data contracts across the system.

---

## Planned Contents (not yet implemented)

```
shared/
├── schemas/       # Shared Pydantic API schemas (jobs, peers, sessions)
├── types/         # Common type aliases and enums
└── constants/     # Platform-wide constants
```

---

## Usage

```bash
# Install from the packages/shared directory
pip install -e packages/shared/
```

Other apps can then import:

```python
from shared import __version__
# future: from shared.schemas.jobs import JobSubmission
```
