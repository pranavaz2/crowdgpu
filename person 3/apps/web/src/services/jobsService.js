/**
 * CrowdGPU Jobs Service
 *
 * ── STATUS ───────────────────────────────────────────────────────────────────
 * ALL functions in this module are FRONTEND MOCKS.
 * The CrowdGPU Coordinator does NOT yet implement any job endpoints.
 * The /api/v1/jobs namespace does not exist in the backend.
 *
 * ── TODO: BACKEND INTEGRATION ────────────────────────────────────────────────
 * When the Coordinator implements job endpoints, replace each function body:
 *
 *   listJobs()   →  return apiFetch('/api/v1/jobs');
 *   getJob(id)   →  return apiFetch(`/api/v1/jobs/${id}`);
 *   createJob(p) →  return apiFetch('/api/v1/jobs', { method: 'POST', body: JSON.stringify(p) });
 *   cancelJob(id)→  return apiFetch(`/api/v1/jobs/${id}/cancel`, { method: 'POST' });
 *
 * Only adopt exact request/response fields after the Coordinator job API
 * specification is finalised. The fields below are frontend-only placeholders.
 *
 * Expected future endpoints (from PRD.md §10 — Batch Compute Mode):
 *   POST /api/v1/jobs              → create job
 *   GET  /api/v1/jobs              → list jobs (paginated)
 *   GET  /api/v1/jobs/{job_id}     → get job detail + status
 *   POST /api/v1/jobs/{job_id}/cancel  → cancel a queued/running job
 *
 * ── FRONTEND JOB MODEL ───────────────────────────────────────────────────────
 * This is the frontend mock model. The real backend schema may differ.
 *
 * {
 *   id:                   string   (UUID or mock ID)
 *   name:                 string   human-readable job name
 *   status:               string   'queued' | 'matching' | 'assigned' | 'running' | 'completed' | 'failed'
 *   workload_type:        string   'batch' (only batch supported now; 'render' future)
 *   docker_image:         string   container image reference
 *   command:              string   entrypoint command
 *   vram_required_mb:     number   required VRAM in MiB
 *   submitted_at:         string   ISO datetime — when job was submitted
 *   matching_at:          string|null  ISO datetime — when peer matching started
 *   assigned_at:          string|null  ISO datetime — when a peer was assigned
 *   started_at:           string|null  ISO datetime — when execution started
 *   completed_at:         string|null  ISO datetime — when job completed
 *   peer_id:              string|null  UUID of assigned peer
 *   peer_hostname:        string|null  hostname of assigned peer
 *   gpu_name:             string|null  GPU model on the assigned peer
 *   result:               string|null  success result message (completed only)
 *   error:                string|null  error message (failed only)
 * }
 *
 * ── SESSION PERSISTENCE ───────────────────────────────────────────────────────
 * Jobs are stored in sessionStorage under SESSION_KEY so that newly created
 * jobs survive page navigation within the same browser tab.
 * They are reset when the tab is closed (sessionStorage semantics).
 */

import { apiFetch } from './api.js';
import { isMockMode } from '../utils/environment.js';

// ---------------------------------------------------------------------------
// Session storage key
// ---------------------------------------------------------------------------
const SESSION_KEY = 'crowdgpu_mock_jobs';

// ---------------------------------------------------------------------------
// Seed data — representative lifecycle states for demonstration.
// These are loaded once and merged with any sessionStorage jobs.
// ---------------------------------------------------------------------------
const SEED_JOBS = [
  {
    id: 'job-0000-0000-0000-000000000001',
    name: 'MNIST Training Run',
    status: 'completed',
    workload_type: 'batch',
    docker_image: 'pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime',
    command: 'python train.py --epochs 10 --lr 0.001',
    vram_required_mb: 4096,
    submitted_at: '2026-10-08T10:00:00Z',
    matching_at:  '2026-10-08T10:00:05Z',
    assigned_at:  '2026-10-08T10:00:30Z',
    started_at:   '2026-10-08T10:01:30Z',
    completed_at: '2026-10-08T10:45:00Z',
    peer_id:       'a1b2c3d4-0001-0000-0000-000000000001',
    peer_hostname: 'rig-alpha.local',
    gpu_name:      'NVIDIA GeForce RTX 4090',
    result: 'Training complete. Final accuracy: 99.2% on test set. Checkpoint saved.',
    error: null,
  },
  {
    id: 'job-0000-0000-0000-000000000002',
    name: 'ResNet-50 Inference Benchmark',
    status: 'running',
    workload_type: 'batch',
    docker_image: 'pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime',
    command: 'python benchmark.py --model resnet50 --batch-size 64',
    vram_required_mb: 8192,
    submitted_at: '2026-10-08T18:00:00Z',
    matching_at:  '2026-10-08T18:00:08Z',
    assigned_at:  '2026-10-08T18:00:50Z',
    started_at:   '2026-10-08T18:01:00Z',
    completed_at: null,
    peer_id:       'a1b2c3d4-0004-0000-0000-000000000004',
    peer_hostname: 'workstation-beta',
    gpu_name:      'NVIDIA GeForce RTX 3090',
    result: null,
    error: null,
  },
  {
    id: 'job-0000-0000-0000-000000000003',
    name: 'Stable Diffusion Render',
    status: 'queued',
    workload_type: 'batch',
    docker_image: 'stability-ai/stable-diffusion:v2.1',
    command: 'python generate.py --prompt "mountain landscape at sunset" --steps 50 --cfg 7.5',
    vram_required_mb: 12288,
    submitted_at: '2026-10-08T19:55:00Z',
    matching_at:  null,
    assigned_at:  null,
    started_at:   null,
    completed_at: null,
    peer_id:       null,
    peer_hostname: null,
    gpu_name:      null,
    result: null,
    error: null,
  },
  {
    id: 'job-0000-0000-0000-000000000004',
    name: 'BERT Fine-tuning',
    status: 'failed',
    workload_type: 'batch',
    docker_image: 'huggingface/transformers:4.35.0-cuda11.8-cudnn8-runtime',
    command: 'python fine_tune.py --model bert-base-uncased --dataset sst2',
    vram_required_mb: 10240,
    submitted_at: '2026-10-07T14:30:00Z',
    matching_at:  '2026-10-07T14:30:10Z',
    assigned_at:  '2026-10-07T14:30:55Z',
    started_at:   '2026-10-07T14:31:00Z',
    completed_at: '2026-10-07T14:45:00Z',
    peer_id:       'a1b2c3d4-0006-0000-0000-000000000006',
    peer_hostname: 'node-gamma-03',
    gpu_name:      'NVIDIA GeForce RTX 4070 Ti',
    result: null,
    error: 'CUDA out of memory: tried to allocate 2.50 GiB. Available: 1.38 GiB.',
  },
  {
    id: 'job-0000-0000-0000-000000000005',
    name: 'LLaMA-2 Inference',
    status: 'matching',
    workload_type: 'batch',
    docker_image: 'meta-llama/llama2:7b-chat-hf',
    command: 'python inference.py --model llama2-7b --max-tokens 512',
    vram_required_mb: 16384,
    submitted_at: '2026-10-08T19:58:00Z',
    matching_at:  '2026-10-08T19:58:04Z',
    assigned_at:  null,
    started_at:   null,
    completed_at: null,
    peer_id:       null,
    peer_hostname: null,
    gpu_name:      null,
    result: null,
    error: null,
  },
  {
    id: 'job-0000-0000-0000-000000000006',
    name: 'YOLOv8 Object Detection',
    status: 'assigned',
    workload_type: 'batch',
    docker_image: 'ultralytics/ultralytics:8.0.196',
    command: 'yolo detect train data=coco.yaml model=yolov8n.pt epochs=50',
    vram_required_mb: 8192,
    submitted_at: '2026-10-08T19:50:00Z',
    matching_at:  '2026-10-08T19:50:06Z',
    assigned_at:  '2026-10-08T19:50:45Z',
    started_at:   null,
    completed_at: null,
    peer_id:       'a1b2c3d4-0002-0000-0000-000000000002',
    peer_hostname: 'gpu-cluster-delta',
    gpu_name:      'NVIDIA A100 SXM4 80GB',
    result: null,
    error: null,
  },
];

// ---------------------------------------------------------------------------
// Session persistence helpers
// ---------------------------------------------------------------------------

/**
 * Load jobs from sessionStorage, seeding with SEED_JOBS on first load.
 * Seed jobs are never overwritten — session jobs are merged on top.
 *
 * @returns {object[]}
 */
function loadJobs() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (raw) {
      const sessionJobs = JSON.parse(raw);
      // Merge: session jobs take priority over seeds of the same ID
      const seedsNotInSession = SEED_JOBS.filter(
        (s) => !sessionJobs.some((j) => j.id === s.id)
      );
      return [...sessionJobs, ...seedsNotInSession];
    }
  } catch {
    // sessionStorage unavailable or parse error — fall back to seeds
  }
  return [...SEED_JOBS];
}

/**
 * Persist the current job list to sessionStorage.
 *
 * @param {object[]} jobs
 */
function saveJobs(jobs) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(jobs));
  } catch {
    // sessionStorage unavailable — silently skip
  }
}

/**
 * Read all current jobs (from session or seed).
 *
 * @returns {object[]}
 */
function getJobs() {
  return loadJobs();
}

/**
 * Write a mutated job list back to the session.
 *
 * @param {object[]} jobs
 */
function putJobs(jobs) {
  saveJobs(jobs);
}

// ---------------------------------------------------------------------------
// ID generator
// ---------------------------------------------------------------------------

function generateId() {
  const ts = Date.now().toString(36).padStart(8, '0');
  const rnd = Math.random().toString(36).slice(2, 10).padStart(8, '0');
  return `job-mock-${ts}-${rnd}`;
}

// ---------------------------------------------------------------------------
// Simulated network delay
// ---------------------------------------------------------------------------
function delay(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * [MOCK] List all jobs ordered newest-first.
 *
 * Mock mode:  reads from sessionStorage/seed data.
 * Real mode:  will call GET /api/v1/jobs once coordinator implements it.
 *             Until then, throws a clear error instead of silently using mock data.
 *
 * Backend integration:
 *   Replace mock branch with: return apiFetch('/api/v1/jobs');
 *
 * @returns {Promise<object[]>}
 */
export async function listJobs() {
  if (isMockMode()) {
    await delay(200);
    const jobs = getJobs();
    return [...jobs]
      .sort((a, b) => new Date(b.submitted_at).getTime() - new Date(a.submitted_at).getTime())
      .map(normalizeJobResponse);
  }

  // Real mode: coordinator job API not yet implemented.
  throw Object.assign(
    new Error('Job API is not yet available. Enable VITE_USE_MOCK=true to use demo data.'),
    { status: 501 }
  );
}

/**
 * [MOCK] Get a single job by ID.
 *
 * Backend integration:
 *   Replace with: return apiFetch(`/api/v1/jobs/${jobId}`);
 *
 * @param {string} jobId
 * @returns {Promise<object>}
 */
export async function getJob(jobId) {
  if (isMockMode()) {
    await delay(150);
    const jobs = getJobs();
    const job = jobs.find((j) => j.id === jobId);
    if (!job) {
      const err = new Error(`Job not found: ${jobId}`);
      err.status = 404;
      throw err;
    }
    return normalizeJobResponse({ ...job });
  }

  throw Object.assign(
    new Error('Job API is not yet available. Enable VITE_USE_MOCK=true to use demo data.'),
    { status: 501 }
  );
}

/**
 * [MOCK] Create (submit) a new job.
 *
 * Backend integration:
 *   Replace with:
 *   return apiFetch('/api/v1/jobs', {
 *     method: 'POST',
 *     body: JSON.stringify(payload),
 *   });
 *
 * @param {{ name, docker_image, command, vram_required_mb, workload_type? }} payload
 * @returns {Promise<object>}
 */
export async function createJob(payload) {
  if (isMockMode()) {
    await delay(350);
    const now = new Date().toISOString();
    const newJob = {
      id:               generateId(),
      name:             payload.name?.trim() || 'Unnamed Job',
      status:           'queued',
      workload_type:    payload.workload_type || 'batch',
      docker_image:     payload.docker_image?.trim() || '',
      command:          payload.command?.trim() || '',
      vram_required_mb: Number(payload.vram_required_mb) || 0,
      submitted_at:     now,
      matching_at:      null,
      assigned_at:      null,
      started_at:       null,
      completed_at:     null,
      peer_id:          null,
      peer_hostname:    null,
      gpu_name:         null,
      result:           null,
      error:            null,
    };
    const jobs = getJobs();
    putJobs([newJob, ...jobs]);
    return normalizeJobResponse({ ...newJob });
  }

  throw Object.assign(
    new Error('Job API is not yet available. Enable VITE_USE_MOCK=true to use demo data.'),
    { status: 501 }
  );
}

/**
 * [MOCK] Cancel a queued or running job.
 *
 * Backend integration:
 *   Replace with:
 *   return apiFetch(`/api/v1/jobs/${jobId}/cancel`, { method: 'POST' });
 *
 * @param {string} jobId
 * @returns {Promise<object>} Updated job
 */
export async function cancelJob(jobId) {
  if (isMockMode()) {
    await delay(200);
    const jobs = getJobs();
    const idx = jobs.findIndex((j) => j.id === jobId);
    if (idx === -1) {
      const err = new Error(`Job not found: ${jobId}`);
      err.status = 404;
      throw err;
    }
    const job = jobs[idx];
    const cancellable = ['queued', 'matching', 'assigned'];
    if (!cancellable.includes(job.status)) {
      const err = new Error(`Cannot cancel a job with status '${job.status}'.`);
      err.status = 409;
      throw err;
    }
    const updated = {
      ...job,
      status: 'failed',
      completed_at: new Date().toISOString(),
      error: 'Cancelled by user.',
    };
    jobs[idx] = updated;
    putJobs(jobs);
    return normalizeJobResponse({ ...updated });
  }

  throw Object.assign(
    new Error('Job API is not yet available. Enable VITE_USE_MOCK=true to use demo data.'),
    { status: 501 }
  );
}

// ---------------------------------------------------------------------------
// Response normalisation
// ---------------------------------------------------------------------------

/**
 * Normalise a raw job object (from mock or future API) into the frontend model.
 *
 * Rules:
 *   - Known fields: mapped directly
 *   - Missing fields: null (never fabricated)
 *   - Do NOT add status progress, percentage, or telemetry fields
 *
 * When the backend schema is finalised, update field mappings here.
 * Pages and hooks do not need to change.
 *
 * @param {object} raw
 * @returns {object}
 */
export function normalizeJobResponse(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return {
    id:               raw.id               ?? null,
    name:             raw.name             ?? '(unknown)',
    status:           raw.status           ?? 'queued',
    workload_type:    raw.workload_type    ?? 'batch',
    docker_image:     raw.docker_image     ?? null,
    command:          raw.command          ?? null,
    vram_required_mb: typeof raw.vram_required_mb === 'number' ? raw.vram_required_mb : null,
    submitted_at:     raw.submitted_at     ?? null,
    matching_at:      raw.matching_at      ?? null,
    assigned_at:      raw.assigned_at      ?? null,
    started_at:       raw.started_at       ?? null,
    completed_at:     raw.completed_at     ?? null,
    peer_id:          raw.peer_id          ?? null,
    peer_hostname:    raw.peer_hostname    ?? null,
    gpu_name:         raw.gpu_name         ?? null,
    result:           raw.result           ?? null,
    error:            raw.error            ?? null,
  };
}
