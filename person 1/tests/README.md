# Tests

Cross-cutting tests that span multiple applications or test full system behaviour.

## Directory Layout

```
tests/
├── integration/    # Integration tests (cross-service, real infrastructure)
├── e2e/            # End-to-end tests (full user flows)
├── performance/    # Load and performance tests
├── security/       # Security and penetration tests
└── fixtures/       # Shared test fixtures and data
```

Unit tests for individual applications live alongside those applications:
- `apps/coordinator/tests/`
- `apps/worker/tests/`
- `apps/cli/tests/`
