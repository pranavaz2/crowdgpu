/**
 * DashboardPage — / route
 *
 * Main CrowdGPU control center.
 *
 * Data sources:
 *   Real  → GET /health       (coordinator liveness, via useHealth)
 *   Mock  → listPeers()       (GET /api/v1/peers not yet in coordinator)
 *   Mock  → listJobs()        (jobs module not yet in coordinator)
 *
 * Stats are derived from live data arrays — never hardcoded.
 */

import React from 'react';
import { Link } from 'react-router-dom';
import PageLayout from '../components/layout/PageLayout.jsx';
import StatCard from '../components/ui/StatCard.jsx';
import Badge from '../components/ui/Badge.jsx';
import LoadingSpinner from '../components/ui/LoadingSpinner.jsx';
import ErrorMessage from '../components/ui/ErrorMessage.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import { useHealth } from '../hooks/useHealth.js';
import { usePeers } from '../hooks/usePeers.js';
import { useJobs } from '../hooks/useJobs.js';
import { formatVram, sumVram, timeAgo } from '../utils/formatters.js';

export default function DashboardPage() {
  const { data: health, loading: healthLoading, error: healthError } = useHealth();
  const { data: peers, loading: peersLoading, error: peersError, refetch: refetchPeers } = usePeers();
  const { data: jobs,  loading: jobsLoading,  error: jobsError  } = useJobs();

  // ── Derived stats (computed from data arrays, never hardcoded) ─────────
  const availablePeers  = peers?.filter((p) => p.status === 'available') ?? [];
  const allGpus         = peers?.flatMap((p) => p.gpu_capabilities ?? []) ?? [];
  const availableGpus   = availablePeers.flatMap((p) => p.gpu_capabilities ?? []);
  const totalVramMb     = availableGpus.reduce((s, g) => s + (g.vram_mb ?? 0), 0);
  const runningJobs     = jobs?.filter((j) => j.status === 'running') ?? [];

  const statsLoading = peersLoading || jobsLoading;

  return (
    <div className="flex flex-col min-h-full">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="border-b border-gray-800 bg-gray-950">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-8">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-white">
                CrowdGPU
              </h1>
              <p className="mt-1 text-sm text-gray-400">
                Distributed GPU Resource Platform — monitor shared capacity, connected providers, and workload activity.
              </p>
            </div>

            {/* Coordinator status */}
            <CoordinatorStatus
              loading={healthLoading}
              health={health}
              error={healthError}
            />
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl w-full px-4 sm:px-6 py-8 space-y-10">

        {/* ── Stat cards ─────────────────────────────────────────────────── */}
        <section aria-label="Platform statistics">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="Active Peers"
              value={statsLoading ? undefined : availablePeers.length}
              description={peers ? `${peers.length} total registered` : undefined}
              loading={statsLoading}
              icon={<Icon path="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />}
            />
            <StatCard
              title="Available GPUs"
              value={statsLoading ? undefined : availableGpus.length}
              description={allGpus.length > 0 ? `${allGpus.length} total registered` : undefined}
              loading={statsLoading}
              icon={<Icon path="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />}
            />
            <StatCard
              title="Available VRAM"
              value={statsLoading ? undefined : (availableGpus.length ? formatVram(totalVramMb) : '—')}
              description="across active peers"
              loading={statsLoading}
              icon={<Icon path="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />}
            />
            <StatCard
              title="Running Jobs"
              value={statsLoading ? undefined : runningJobs.length}
              description={jobs ? `${jobs.length} total jobs` : undefined}
              loading={statsLoading}
              icon={<Icon path="M13 10V3L4 14h7v7l9-11h-7z" />}
            />
          </div>
        </section>

        {/* ── GPU Resources overview ──────────────────────────────────────── */}
        <section aria-label="GPU resources overview">
          <SectionHeader
            title="GPU Resources"
            action={
              <Link
                to="/peers"
                className="text-xs text-brand-400 hover:text-brand-300 transition-colors"
              >
                View all resources →
              </Link>
            }
          />

          {peersLoading && <SectionSkeleton rows={3} />}

          {peersError && (
            <ErrorMessage message={peersError} onRetry={refetchPeers} />
          )}

          {!peersLoading && !peersError && (!peers || peers.length === 0) && (
            <EmptyState
              title="No GPU providers connected"
              description="Start the CrowdGPU worker daemon on a provider machine to register its GPUs."
            />
          )}

          {!peersLoading && !peersError && peers && peers.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {peers
                .filter((p) => p.status !== 'offline')
                .slice(0, 6)
                .map((peer) => (
                  <React.Fragment key={peer.id}>
                    {(peer.gpu_capabilities ?? []).map((gpu) => (
                      <GpuResourceCard key={gpu.id} peer={peer} gpu={gpu} />
                    ))}
                  </React.Fragment>
                ))}
            </div>
          )}
        </section>

        {/* ── Two-column: recent providers + recent jobs ───────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Recent providers */}
          <section aria-label="Recent providers" className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
              <h2 className="text-sm font-semibold text-white">Recent Providers</h2>
              <Link
                to="/peers"
                className="text-xs text-brand-400 hover:text-brand-300 transition-colors"
              >
                View all →
              </Link>
            </div>

            {peersLoading && <RowSkeleton count={4} />}

            {peersError && (
              <div className="p-4">
                <ErrorMessage message={peersError} onRetry={refetchPeers} />
              </div>
            )}

            {!peersLoading && !peersError && (!peers || peers.length === 0) && (
              <EmptyState
                title="No providers registered"
                description="Register a provider to see it here."
              />
            )}

            {!peersLoading && !peersError && peers && peers.length > 0 && (
              <div className="divide-y divide-gray-800">
                {peers.slice(0, 5).map((peer) => (
                  <PeerRow key={peer.id} peer={peer} />
                ))}
              </div>
            )}
          </section>

          {/* Recent jobs */}
          <section aria-label="Recent jobs" className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
              <h2 className="text-sm font-semibold text-white">Recent Jobs</h2>
              <Link
                to="/jobs"
                className="text-xs text-brand-400 hover:text-brand-300 transition-colors"
              >
                View all →
              </Link>
            </div>

            {jobsLoading && <RowSkeleton count={4} />}

            {jobsError && (
              <div className="p-4">
                <ErrorMessage message={jobsError} />
              </div>
            )}

            {!jobsLoading && !jobsError && (!jobs || jobs.length === 0) && (
              <EmptyState
                title="No jobs submitted"
                description="Submit a GPU workload to get started."
                action={
                  <Link
                    to="/jobs/submit"
                    className="inline-flex items-center rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-500 transition-colors"
                  >
                    Submit a job
                  </Link>
                }
              />
            )}

            {!jobsLoading && !jobsError && jobs && jobs.length > 0 && (
              <div className="divide-y divide-gray-800">
                {jobs.slice(0, 5).map((job) => (
                  <JobRow key={job.id} job={job} />
                ))}
              </div>
            )}
          </section>
        </div>

      </div>
    </div>
  );
}

// ============================================================================
// Sub-components
// ============================================================================

// ── Coordinator health indicator ────────────────────────────────────────────

function CoordinatorStatus({ loading, health, error }) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-gray-600 animate-pulse" />
        <span>Checking coordinator…</span>
      </div>
    );
  }

  if (error || !health || health.status !== 'ok') {
    return (
      <div
        className="flex items-start gap-3 rounded-lg border border-red-900/40 bg-red-950/20 px-4 py-3 max-w-xs"
        role="alert"
      >
        <span className="mt-0.5 inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full bg-red-500" />
        <div>
          <p className="text-xs font-medium text-red-400">Coordinator Offline</p>
          <p className="text-xs text-red-400/60 mt-0.5">
            Unable to reach the backend coordinator.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-xs text-gray-400 rounded-lg border border-gray-800 bg-gray-900 px-3 py-2">
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
      <span>
        Coordinator Online
        {health.version && (
          <span className="ml-1 text-gray-600">v{health.version}</span>
        )}
      </span>
    </div>
  );
}

// ── GPU resource card (dashboard preview) ───────────────────────────────────

function GpuResourceCard({ peer, gpu }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 flex flex-col gap-3">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs text-gray-500 font-mono truncate">{peer.hostname}</p>
          <p className="text-sm font-semibold text-white mt-0.5 leading-snug">{gpu.gpu_name}</p>
        </div>
        <Badge status={peer.status} className="flex-shrink-0 mt-0.5" />
      </div>

      {/* VRAM — primary metric */}
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-semibold text-white tabular-nums">
          {formatVram(gpu.vram_mb)}
        </span>
        <span className="text-xs text-gray-500">VRAM</span>
      </div>

      {/* Capability details */}
      <dl className="grid grid-cols-3 gap-x-3 gap-y-1.5 text-xs border-t border-gray-800 pt-3">
        <CapDetail label="CUDA"   value={gpu.cuda_version} />
        <CapDetail label="CC"     value={gpu.compute_capability} />
        <CapDetail label="Driver" value={gpu.driver_version} />
      </dl>

      {/* Last seen */}
      <p className="text-xs text-gray-600">
        Last seen {timeAgo(peer.last_seen_at)}
      </p>
    </div>
  );
}

function CapDetail({ label, value }) {
  return (
    <div>
      <dt className="text-gray-600">{label}</dt>
      <dd className="text-gray-300 font-mono">{value ?? '—'}</dd>
    </div>
  );
}

// ── Recent provider row ──────────────────────────────────────────────────────

function PeerRow({ peer }) {
  const gpuCount   = peer.gpu_capabilities?.length ?? 0;
  const totalVram  = sumVram(peer.gpu_capabilities);
  const primaryGpu = peer.gpu_capabilities?.[0];

  return (
    <div className="flex items-center justify-between gap-4 px-5 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-white font-mono truncate">{peer.hostname}</p>
        <p className="text-xs text-gray-500 mt-0.5">
          {gpuCount} GPU{gpuCount !== 1 ? 's' : ''}
          {primaryGpu && <span> · {primaryGpu.gpu_name}</span>}
          {' · '}{totalVram} VRAM
          {' · last seen '}{timeAgo(peer.last_seen_at)}
        </p>
      </div>
      <Badge status={peer.status} className="flex-shrink-0" />
    </div>
  );
}

// ── Recent job row ───────────────────────────────────────────────────────────

function JobRow({ job }) {
  return (
    <Link
      to={`/jobs/${job.id}`}
      className="flex items-center justify-between gap-4 px-5 py-3 hover:bg-gray-800/50 transition-colors"
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-white truncate">{job.name}</p>
        <p className="text-xs text-gray-500 mt-0.5">
          {formatVram(job.vram_required_mb)} required
          {job.peer_hostname && <span> · {job.peer_hostname}</span>}
          {' · '}{timeAgo(job.submitted_at)}
        </p>
      </div>
      <Badge status={job.status} className="flex-shrink-0" />
    </Link>
  );
}

// ── Layout helpers ───────────────────────────────────────────────────────────

function SectionHeader({ title, action }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="text-base font-semibold text-white">{title}</h2>
      {action}
    </div>
  );
}

function SectionSkeleton({ rows = 3 }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-xl border border-gray-800 bg-gray-900 p-4 space-y-3 animate-pulse">
          <div className="h-3 w-24 rounded bg-gray-800" />
          <div className="h-5 w-40 rounded bg-gray-800" />
          <div className="h-8 w-20 rounded bg-gray-800" />
          <div className="h-3 w-full rounded bg-gray-800" />
        </div>
      ))}
    </div>
  );
}

function RowSkeleton({ count = 4 }) {
  return (
    <div className="divide-y divide-gray-800 animate-pulse">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex items-center justify-between px-5 py-3.5">
          <div className="space-y-1.5">
            <div className="h-3 w-32 rounded bg-gray-800" />
            <div className="h-2.5 w-48 rounded bg-gray-800" />
          </div>
          <div className="h-5 w-16 rounded-full bg-gray-800" />
        </div>
      ))}
    </div>
  );
}

// ── Inline icon ──────────────────────────────────────────────────────────────

function Icon({ path }) {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}
