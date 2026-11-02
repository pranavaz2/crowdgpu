/**
 * CrowdGPU frontend environment utilities.
 *
 * Single source of truth for all environment-driven behaviour.
 * Import from here — do NOT read import.meta.env directly in pages, hooks,
 * or components.
 *
 * ── Supported environment variables ──────────────────────────────────────────
 *
 *   VITE_USE_MOCK
 *     'true'  → Use mock/demo data for peers and jobs.
 *               The Coordinator's real peer list and jobs endpoints are not
 *               called. Useful for development and project demonstration.
 *     'false' (or unset) → Use real Coordinator endpoints. Mock data is
 *               not substituted if a request fails — real errors are shown.
 *
 *   VITE_API_BASE_URL
 *     Empty (default) → Vite's dev-proxy handles /api/* → http://localhost:8000
 *     Set to a full origin (e.g. https://coordinator.crowdgpu.example.com)
 *     to target a remote Coordinator in staging or production.
 *
 * ── Do NOT add credentials or secrets to .env files committed to the repo.
 */

/**
 * Returns true when the application is running in mock / demo mode.
 *
 * Mock mode:
 *   - Peer list returns local mock data (GET /api/v1/peers does not exist yet)
 *   - Job functions use sessionStorage mock state
 *
 * @returns {boolean}
 */
export function isMockMode() {
  return import.meta.env.VITE_USE_MOCK === 'true';
}

/**
 * Returns the configured API base URL.
 *
 * Empty string (default) → requests are relative, handled by Vite proxy in dev
 * or served from the same origin in production.
 *
 * @returns {string}
 */
export function getApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL ?? '';
}

/**
 * Returns true when running in Vite's development server (npm run dev).
 * Useful for dev-only tooling — do not use for mock/real branching.
 *
 * @returns {boolean}
 */
export function isDev() {
  return import.meta.env.DEV === true;
}
