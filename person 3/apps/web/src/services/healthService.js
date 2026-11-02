/**
 * Health service.
 *
 * Wraps the only coordinator liveness endpoint currently implemented:
 *   GET /health  →  { status: string, version: string }
 *
 * Reference: apps/coordinator/coordinator/api/health.py
 */

import { apiFetch } from './api.js';

/**
 * Fetch coordinator health status.
 *
 * @returns {Promise<{ status: string, version: string }>}
 */
export async function getHealth() {
  return apiFetch('/health');
}
