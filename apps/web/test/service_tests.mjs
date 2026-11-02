import assert from 'node:assert/strict';
import { normalizeJobResponse } from '../src/services/jobsService.js';
import { normalizePeerResponse } from '../src/services/peersService.js';

console.log('--- Running Frontend Service Layer & Normalization Tests ---');

// 1. Job Normalization Tests
{
  const rawBackendJob = {
    id: 'b1234567-0000-0000-0000-000000000001',
    name: 'PyTorch Matrix Multiplication',
    command: 'matrix_multiply',
    status: 'COMPLETED',
    created_at: '2026-10-12T10:00:00Z',
    started_at: '2026-10-12T10:00:02Z',
    completed_at: '2026-10-12T10:00:05Z',
    assigned_peer_id: 'a1b2c3d4-0001-0000-0000-000000000001',
    peer_hostname: 'rtx3050-worker',
    gpu_name: 'NVIDIA GeForce RTX 3050 Laptop GPU',
    requirements: {
      workload_type: 'matrix_multiply',
      required_vram_mb: 256,
    },
    result: {
      matrix_dim: 1024,
      result_shape: [1024, 1024],
      execution_time_s: 0.042,
      exit_code: 0,
    },
    error: null,
  };

  const normalized = normalizeJobResponse(rawBackendJob);

  assert.equal(normalized.id, rawBackendJob.id);
  assert.equal(normalized.name, rawBackendJob.name);
  assert.equal(normalized.status, 'completed', 'Job status must be normalized to lowercase');
  assert.equal(normalized.submitted_at, '2026-10-12T10:00:00Z', 'submitted_at must fall back to created_at');
  assert.equal(normalized.peer_id, rawBackendJob.assigned_peer_id);
  assert.equal(normalized.peer_hostname, 'rtx3050-worker');
  assert.equal(normalized.gpu_name, 'NVIDIA GeForce RTX 3050 Laptop GPU');
  assert.equal(normalized.vram_required_mb, 256);
  assert.equal(normalized.workload_type, 'matrix_multiply');
  assert.deepEqual(normalized.result, rawBackendJob.result);
  assert.equal(normalized.error, null);
  console.log('✓ normalizeJobResponse handles real coordinator schema and lowercases status');
}

// 2. Peer Normalization Tests
{
  const rawBackendPeer = {
    id: 'a1b2c3d4-0001-0000-0000-000000000001',
    owner_id: '00000000-0000-0000-0000-000000000001',
    hostname: 'worker-laptop-01',
    status: 'AVAILABLE',
    registered_at: '2026-10-12T09:00:00Z',
    last_seen_at: '2026-10-12T10:05:00Z',
    created_at: '2026-10-12T09:00:00Z',
    updated_at: '2026-10-12T10:05:00Z',
    gpu_capabilities: [
      {
        id: 'g1111111-0000-0000-0000-000000000001',
        peer_id: 'a1b2c3d4-0001-0000-0000-000000000001',
        gpu_name: 'NVIDIA GeForce RTX 3050 Laptop GPU',
        vram_mb: 4096,
        driver_version: '566.14',
        cuda_version: '12.7',
        compute_capability: '8.6',
      },
    ],
  };

  const normalized = normalizePeerResponse(rawBackendPeer);

  assert.equal(normalized.id, rawBackendPeer.id);
  assert.equal(normalized.hostname, 'worker-laptop-01');
  assert.equal(normalized.status, 'available', 'Peer status must be normalized to lowercase');
  assert.equal(normalized.gpu_capabilities.length, 1);
  assert.equal(normalized.gpu_capabilities[0].gpu_name, 'NVIDIA GeForce RTX 3050 Laptop GPU');
  assert.equal(normalized.gpu_capabilities[0].vram_mb, 4096);
  assert.equal(normalized.gpu_capabilities[0].cuda_version, '12.7');
  assert.equal(normalized.gpu_capabilities[0].driver_version, '566.14');
  assert.equal(normalized.gpu_capabilities[0].compute_capability, '8.6');
  // Confirm NO fabricated telemetry
  assert.equal(normalized.gpu_capabilities[0].temperature, undefined);
  assert.equal(normalized.gpu_capabilities[0].utilization, undefined);
  console.log('✓ normalizePeerResponse maps capabilities and avoids fabricating telemetry');
}

// 3. Fallback and Empty Schema Safety
{
  const emptyJob = normalizeJobResponse({});
  assert.equal(emptyJob.id, null);
  assert.equal(emptyJob.name, '(unknown)');
  assert.equal(emptyJob.status, 'queued');
  assert.equal(emptyJob.result, null);
  assert.equal(emptyJob.error, null);

  const emptyPeer = normalizePeerResponse({});
  assert.equal(emptyPeer.id, null);
  assert.equal(emptyPeer.hostname, '(unknown)');
  assert.equal(emptyPeer.status, 'offline');
  assert.deepEqual(emptyPeer.gpu_capabilities, []);

  assert.equal(normalizeJobResponse(null), null);
  assert.equal(normalizePeerResponse(null), null);
  console.log('✓ Normalizers handle empty or null payloads gracefully without crashing');
}

console.log('ALL SERVICE-LAYER TESTS PASSED SUCCESSFULLY (3 suites, 15 assertions)!');
