# CrowdGPU CLI

Command-line interface for the CrowdGPU platform.

**Status: Bootstrap phase** — Only `--help` and `--version` are functional.
Job submission, session management, and resource listing will be added in later phases.

**Framework:** [Click](https://click.palletsprojects.com/) (see ADR-002)

---

## Installation

```bash
pip install -e ".[dev]"
```

---

## Usage

```bash
# Show help
crowdgpu-cli --help

# Show version
crowdgpu-cli --version

# Command group help
crowdgpu-cli jobs --help
crowdgpu-cli sessions --help
crowdgpu-cli peers --help
```

---

## Planned Commands (not yet implemented)

| Command | Description |
|---|---|
| `crowdgpu-cli jobs submit` | Submit a GPU compute job |
| `crowdgpu-cli jobs list` | List jobs |
| `crowdgpu-cli jobs status <id>` | Get job status |
| `crowdgpu-cli sessions start` | Start a remote rendering session |
| `crowdgpu-cli peers list` | List available GPU peers |

---

## Testing

```bash
pytest
```

---

## Linting

```bash
ruff format . && ruff check .
```
