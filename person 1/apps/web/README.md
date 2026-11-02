# CrowdGPU Web Portal

Consumer-facing web application for the CrowdGPU platform.

**Status: Bootstrap phase** — Placeholder dashboard only. Actual functionality
will be implemented in later phases.

**Stack:** React 18 · Vite 5 · Tailwind CSS 3

---

## Development

```bash
npm install
npm run dev
# Open http://localhost:5173
```

API calls are proxied to the coordinator at `http://localhost:8000`.

---

## Build

```bash
npm run build
# Output: dist/
```

---

## Lint

```bash
npm run lint
```

---

## Planned Features (not yet implemented)

- Job submission form
- Job status and log viewer
- Peer / resource browser
- Remote rendering session viewer
- Authentication
- Credit and reputation display
