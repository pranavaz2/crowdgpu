/**
 * Peers service.
 *
 * Wraps coordinator peer endpoints.
 *
 * ── REAL endpoints (currently implemented in coordinator) ──────────────────
 *   GET  /api/v1/peers/{peer_id}            → PeerResponse
 *   POST /api/v1/peers                       → PeerResponse  (worker-facing)
 *   PATCH /api/v1/peers/{peer_id}/heartbeat  → PeerResponse  (worker-facing)
 *   POST /api/v1/peers/{peer_id}/deregister  → PeerResponse  (worker-facing)
 *
 * ── MOCKED (NOT implemented in coordinator) ────────────────────────────────
 *   GET /api/v1/peers  — no peer-list endpoint exists as of current backend.
 *                        listPeers() returns mock data when VITE_USE_MOCK=true.
 *
 *   To integrate with the real backend once it is available:
 *     1. Remove the USE_MOCK guard in listPeers()
 *     2. Remove the MOCK_PEERS constant
 *     3. Remove this comment block
 *
 * ── PeerResponse schema (from coordinator/peers/schemas.py) ────────────────
 * {
 *   id: string (UUID)
 *   owner_id: string (UUID)
 *   hostname: string
 *   status: 'offline' | 'available' | 'busy'
 *   registered_at: string (ISO datetime) | null
 *   last_seen_at: string (ISO datetime) | null
 *   created_at: string (ISO datetime)
 *   updated_at: string (ISO datetime)
 *   gpu_capabilities: GpuCapabilityResponse[]
 * }
 *
 * GpuCapabilityResponse:
 * {
 *   id: string (UUID)
 *   peer_id: string (UUID)
 *   gpu_name: string
 *   vram_mb: number   (MiB — NOT MB)
 *   driver_version: string | null
 *   cuda_version: string | null
 *   compute_capability: string | null
 *   created_at: string (ISO datetime)
 *   updated_at: string (ISO datetime)
 * }
 *
 * NOTE: No live telemetry fields (utilization, temperature, free_vram, etc.)
 * exist in the current PeerResponse. Do not display such values.
 */

import { apiFetch } from './api.js';
import { isMockMode } from '../utils/environment.js';

// ---------------------------------------------------------------------------
// Mock control — driven by VITE_USE_MOCK in .env.local.
// Use isMockMode() — do NOT read import.meta.env directly here.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Helper — stable relative timestamps anchored to module load time
// ---------------------------------------------------------------------------
const NOW = Date.now();
const ago = (ms) => new Date(NOW - ms).toISOString();
const daysAgo = (d) => ago(d * 86_400_000);

// ---------------------------------------------------------------------------
// MOCK_PEERS — representative dataset for demonstration.
// All values conform exactly to the PeerResponse + GpuCapabilityResponse schema.
// No live telemetry fields are included.
// ---------------------------------------------------------------------------
const MOCK_PEERS = [
  // ── Available peers ──────────────────────────────────────────────────────
  {
    id: 'a1b2c3d4-0001-0000-0000-000000000001',
    owner_id: 'usr-0000-0000-0000-000000000001',
    hostname: 'rig-alpha.local',
    status: 'available',
    registered_at: daysAgo(7),
    last_seen_at: ago(28_000),          // ~28s ago
    created_at: daysAgo(7),
    updated_at: ago(28_000),
    gpu_capabilities: [
      {
        id: 'gpu-0001-0000-0000-000000000001',
        peer_id: 'a1b2c3d4-0001-0000-0000-000000000001',
        gpu_name: 'NVIDIA GeForce RTX 4090',
        vram_mb: 24576,                 // 24 GB
        driver_version: '535.104.05',
        cuda_version: '12.2',
        compute_capability: '8.9',
        created_at: daysAgo(7),
        updated_at: daysAgo(7),
      },
    ],
  },
  {
    id: 'a1b2c3d4-0002-0000-0000-000000000002',
    owner_id: 'usr-0000-0000-0000-000000000002',
    hostname: 'gpu-cluster-delta',
    status: 'available',
    registered_at: daysAgo(3),
    last_seen_at: ago(9_000),           // ~9s ago
    created_at: daysAgo(3),
    updated_at: ago(9_000),
    gpu_capabilities: [
      {
        id: 'gpu-0002-0000-0000-000000000001',
        peer_id: 'a1b2c3d4-0002-0000-0000-000000000002',
        gpu_name: 'NVIDIA A100 SXM4 80GB',
        vram_mb: 81920,                 // 80 GB
        driver_version: '535.104.05',
        cuda_version: '12.2',
        compute_capability: '8.0',
        created_at: daysAgo(3),
        updated_at: daysAgo(3),
      },
    ],
  },
  {
    id: 'a1b2c3d4-0003-0000-0000-000000000003',
    owner_id: 'usr-0000-0000-0000-000000000003',
    hostname: 'devbox-epsilon',
    status: 'available',
    registered_at: daysAgo(1),
    last_seen_at: ago(5_000),           // ~5s ago
    created_at: daysAgo(1),
    updated_at: ago(5_000),
    gpu_capabilities: [
      {
        id: 'gpu-0003-0000-0000-000000000001',
        peer_id: 'a1b2c3d4-0003-0000-0000-000000000003',
        gpu_name: 'NVIDIA GeForce RTX 4070 Ti Super',
        vram_mb: 16384,                 // 16 GB
        driver_version: '545.29.06',
        cuda_version: '12.3',
        compute_capability: '8.9',
        created_at: daysAgo(1),
        updated_at: daysAgo(1),
      },
    ],
  },

  // ── Busy peers ───────────────────────────────────────────────────────────
  {
    id: 'a1b2c3d4-0004-0000-0000-000000000004',
    owner_id: 'usr-0000-0000-0000-000000000002',
    hostname: 'workstation-beta',
    status: 'busy',
    registered_at: daysAgo(6),
    last_seen_at: ago(11_000),          // ~11s ago
    created_at: daysAgo(6),
    updated_at: ago(11_000),
    gpu_capabilities: [
      {
        id: 'gpu-0004-0000-0000-000000000001',
        peer_id: 'a1b2c3d4-0004-0000-0000-000000000004',
        gpu_name: 'NVIDIA GeForce RTX 3090',
        vram_mb: 24576,                 // 24 GB
        driver_version: '525.89.02',
        cuda_version: '12.0',
        compute_capability: '8.6',
        created_at: daysAgo(6),
        updated_at: daysAgo(6),
      },
      {
        id: 'gpu-0004-0000-0000-000000000002',
        peer_id: 'a1b2c3d4-0004-0000-0000-000000000004',
        gpu_name: 'NVIDIA GeForce RTX 3090',
        vram_mb: 24576,                 // 24 GB (second GPU, same model)
        driver_version: '525.89.02',
        cuda_version: '12.0',
        compute_capability: '8.6',
        created_at: daysAgo(6),
        updated_at: daysAgo(6),
      },
    ],
  },
  {
    id: 'a1b2c3d4-0005-0000-0000-000000000005',
    owner_id: 'usr-0000-0000-0000-000000000004',
    hostname: 'render-farm-zeta',
    status: 'busy',
    registered_at: daysAgo(14),
    last_seen_at: ago(4_000),           // ~4s ago
    created_at: daysAgo(14),
    updated_at: ago(4_000),
    gpu_capabilities: [
      {
        id: 'gpu-0005-0000-0000-000000000001',
        peer_id: 'a1b2c3d4-0005-0000-0000-000000000005',
        gpu_name: 'NVIDIA RTX A6000',
        vram_mb: 49152,                 // 48 GB
        driver_version: '535.104.05',
        cuda_version: '12.2',
        compute_capability: '8.6',
        created_at: daysAgo(14),
        updated_at: daysAgo(14),
      },
    ],
  },

  // ── Offline peers ────────────────────────────────────────────────────────
  {
    id: 'a1b2c3d4-0006-0000-0000-000000000006',
    owner_id: 'usr-0000-0000-0000-000000000003',
    hostname: 'node-gamma-03',
    status: 'offline',
    registered_at: daysAgo(10),
    last_seen_at: daysAgo(1),           // went offline ~1 day ago
    created_at: daysAgo(10),
    updated_at: daysAgo(1),
    gpu_capabilities: [
      {
        id: 'gpu-0006-0000-0000-000000000001',
        peer_id: 'a1b2c3d4-0006-0000-0000-000000000006',
        gpu_name: 'NVIDIA GeForce RTX 4070 Ti',
        vram_mb: 12288,                 // 12 GB
        driver_version: '535.104.05',
        cuda_version: '12.2',
        compute_capability: '8.9',
        created_at: daysAgo(10),
        updated_at: daysAgo(10),
      },
    ],
  },
  {
    id: 'a1b2c3d4-0007-0000-0000-000000000007',
    owner_id: 'usr-0000-0000-0000-000000000005',
    hostname: 'ml-box-theta',
    status: 'offline',
    registered_at: daysAgo(20),
    last_seen_at: daysAgo(3),           // went offline ~3 days ago
    created_at: daysAgo(20),
    updated_at: daysAgo(3),
    gpu_capabilities: [
      {
        id: 'gpu-0007-0000-0000-000000000001',
        peer_id: 'a1b2c3d4-0007-0000-0000-000000000007',
        gpu_name: 'NVIDIA GeForce RTX 3080',
        vram_mb: 10240,                 // 10 GB
        driver_version: '520.61.05',
        cuda_version: '11.8',
        compute_capability: '8.6',
        created_at: daysAgo(20),
        updated_at: daysAgo(20),
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * List all registered peers with their GPU capabilities.
 *
 * Mock mode  (VITE_USE_MOCK=true):  returns MOCK_PEERS (no network call)
 * Real mode  (VITE_USE_MOCK=false): calls GET /api/v1/peers — this endpoint
 *   does NOT yet exist in the coordinator. The request will fail and the
 *   real error is propagated to the UI (no silent fallback to mock data).
 *
 * Backend integration:
 *   When GET /api/v1/peers is implemented, remove the isMockMode() guard
 *   and the MOCK_PEERS constant, then verify field names against the schema.
 *
 * @returns {Promise<Array>} PeerResponse[]
 */
export async function listPeers() {
  if (isMockMode()) {
    await new Promise((r) => setTimeout(r, 280));
    return MOCK_PEERS.map(normalizePeerResponse);
  }

  // Real mode: attempt the list endpoint. Will fail until backend implements it.
  // Error is propagated — mock data is NOT substituted on failure.
  const data = await apiFetch('/api/v1/peers');
  return Array.isArray(data) ? data.map(normalizePeerResponse) : [];
}

/**
 * Retrieve a single peer by UUID, including its GPU capabilities.
 *
 * Uses the real coordinator endpoint: GET /api/v1/peers/{peer_id}
 *
 * @param {string} peerId - UUID string
 * @returns {Promise<Object>} PeerResponse
 */
export async function getPeer(peerId) {
  const data = await apiFetch(`/api/v1/peers/${peerId}`);
  return normalizePeerResponse(data);
}

// ---------------------------------------------------------------------------
// Response normalisation
// ---------------------------------------------------------------------------

/**
 * Normalise a raw PeerResponse from the Coordinator into the frontend model.
 *
 * Rules:
 *   - Known fields: mapped directly
 *   - Unknown / missing fields: left as null / undefined (never fabricated)
 *   - Do NOT add gpu telemetry (utilization, temperature, free_vram)
 *     because the current PeerResponse does not include those fields.
 *
 * When the backend schema changes, update this function — not the pages.
 *
 * @param {object} raw - Raw API or mock object
 * @returns {object} Normalised peer object
 */
export function normalizePeerResponse(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    id:              raw.id              ?? null,
    owner_id:        raw.owner_id        ?? null,
    hostname:        raw.hostname        ?? '(unknown)',
    status:          raw.status          ?? 'offline',
    registered_at:   raw.registered_at   ?? null,
    last_seen_at:    raw.last_seen_at    ?? null,
    created_at:      raw.created_at      ?? null,
    updated_at:      raw.updated_at      ?? null,
    gpu_capabilities: Array.isArray(raw.gpu_capabilities)
      ? raw.gpu_capabilities.map(normalizeGpuCapability)
      : [],
  };
}

/**
 * Normalise a raw GpuCapabilityResponse.
 *
 * @param {object} raw
 * @returns {object}
 */
function normalizeGpuCapability(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    id:                  raw.id                  ?? null,
    peer_id:             raw.peer_id             ?? null,
    gpu_name:            raw.gpu_name            ?? '(unknown GPU)',
    vram_mb:             typeof raw.vram_mb === 'number' ? raw.vram_mb : null,
    driver_version:      raw.driver_version      ?? null,
    cuda_version:        raw.cuda_version        ?? null,
    compute_capability:  raw.compute_capability  ?? null,
    created_at:          raw.created_at          ?? null,
    updated_at:          raw.updated_at          ?? null,
  };
}
