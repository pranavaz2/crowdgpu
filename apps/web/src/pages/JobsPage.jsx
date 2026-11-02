/**
 * JobsPage — /jobs route
 *
 * GPU workload management — list, filter, search, and sort jobs.
 *
 * Data source:
 *   Mock → listJobs() via useJobs() (GET /api/v1/jobs not yet in coordinator)
 *
 * When the coordinator implements GET /api/v1/jobs, update jobsService.js only.
 * This page requires no changes to integrate.
 */

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import PageLayout from '../components/layout/PageLayout.jsx';
import Badge from '../components/ui/Badge.jsx';
import LoadingSpinner from '../components/ui/LoadingSpinner.jsx';
import ErrorMessage from '../components/ui/ErrorMessage.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import { useJobs } from '../hooks/useJobs.js';
import { formatVram, timeAgo } from '../utils/formatters.js';

// ── Filter / sort config ─────────────────────────────────────────────────────
const STATUS_FILTERS = ['all', 'queued', 'matching', 'assigned', 'running', 'completed', 'failed', 'cancelled'];

const SORT_OPTIONS = [
  { value: 'newest',  label: 'Newest'        },
  { value: 'oldest',  label: 'Oldest'        },
  { value: 'name',    label: 'Name'          },
  { value: 'status',  label: 'Status'        },
  { value: 'vram',    label: 'Required VRAM' },
];

// Status sort order
const STATUS_ORDER = { queued: 0, matching: 1, assigned: 2, running: 3, completed: 4, failed: 5, cancelled: 6 };

export default function JobsPage() {
  const { data: jobs, loading, error, refetch } = useJobs();

  const [search,       setSearch]  = useState('');
  const [statusFilter, setStatus]  = useState('all');
  const [sortBy,       setSortBy]  = useState('newest');

  // ── Derived list ──────────────────────────────────────────────────────────
  const processed = useMemo(() => {
    if (!jobs) return [];
    const q = search.trim().toLowerCase();

    let list = jobs.filter((job) => {
      if (statusFilter !== 'all' && job.status !== statusFilter) return false;
      if (q) {
        const text = [job.name, job.id, job.peer_hostname, job.docker_image]
          .filter(Boolean).join(' ').toLowerCase();
        if (!text.includes(q)) return false;
      }
      return true;
    });

    list = [...list].sort((a, b) => {
      switch (sortBy) {
        case 'newest':
          return new Date(b.submitted_at) - new Date(a.submitted_at);
        case 'oldest':
          return new Date(a.submitted_at) - new Date(b.submitted_at);
        case 'name':
          return (a.name ?? '').localeCompare(b.name ?? '');
        case 'status':
          return (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9);
        case 'vram':
          return (b.vram_required_mb ?? 0) - (a.vram_required_mb ?? 0);
        default:
          return 0;
      }
    });

    return list;
  }, [jobs, search, statusFilter, sortBy]);

  // ── Status counts for filter pills ───────────────────────────────────────
  const counts = useMemo(() => {
    if (!jobs) return {};
    return jobs.reduce((acc, j) => {
      acc[j.status] = (acc[j.status] ?? 0) + 1;
      return acc;
    }, {});
  }, [jobs]);

  return (
    <PageLayout
      title="Jobs"
      description="GPU workloads submitted to the CrowdGPU network."
      actions={
        <Link
          to="/jobs/submit"
          id="btn-submit-job-header"
          className="inline-flex items-center rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 transition-colors"
        >
          + Submit Job
        </Link>
      }
    >
      {/* ── Controls ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3 mb-6">
        {/* Search + sort row */}
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Search */}
          <div className="relative flex-1 max-w-sm">
            <SearchIcon />
            <input
              id="input-job-search"
              type="search"
              placeholder="Search jobs, images, peers…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 pl-9 pr-3 py-2 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 transition-colors"
            />
          </div>

          {/* Sort + refresh */}
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-xs text-gray-500">Sort:</span>
            <select
              id="select-job-sort"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="rounded-md border border-gray-700 bg-gray-800 px-2 py-1.5 text-xs text-white focus:border-brand-500 focus:outline-none"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>

            <button
              id="btn-refresh-jobs"
              onClick={refetch}
              title="Refresh job list"
              className="text-gray-500 hover:text-white transition-colors text-sm px-1"
            >
              ↻
            </button>
          </div>
        </div>

        {/* Status filter pills */}
        <div className="flex flex-wrap gap-2">
          {STATUS_FILTERS.map((s) => {
            const count = s === 'all' ? (jobs?.length ?? 0) : (counts[s] ?? 0);
            if (s !== 'all' && count === 0) return null; // hide empty status pills
            return (
              <button
                key={s}
                id={`filter-job-${s}`}
                onClick={() => setStatus(s)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors flex items-center gap-1.5 ${
                  statusFilter === s
                    ? 'bg-brand-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'
                }`}
              >
                {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
                <span className={statusFilter === s ? 'text-brand-200' : 'text-gray-600'}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Result summary ────────────────────────────────────────────────── */}
      {!loading && !error && jobs && (
        <p className="text-xs text-gray-500 mb-4">
          {processed.length === jobs.length
            ? `${jobs.length} job${jobs.length !== 1 ? 's' : ''}`
            : `${processed.length} of ${jobs.length} jobs`}
          {search && ` matching "${search}"`}
        </p>
      )}

      {/* ── States ───────────────────────────────────────────────────────── */}
      {loading && (
        <div className="py-20">
          <LoadingSpinner size="lg" label="Loading jobs…" />
        </div>
      )}

      {error && <ErrorMessage message={error} onRetry={refetch} />}

      {!loading && !error && processed.length === 0 && (
        <EmptyState
          title={
            search ? `No results for "${search}"`
            : statusFilter !== 'all' ? `No ${statusFilter} jobs`
            : 'No jobs submitted yet'
          }
          description={
            !jobs || jobs.length === 0
              ? 'Submit a GPU workload to get started.'
              : 'Try adjusting the search or filter.'
          }
          action={
            (!jobs || jobs.length === 0) && (
              <Link
                to="/jobs/submit"
                className="inline-flex items-center rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-500 transition-colors"
              >
                Submit a job
              </Link>
            )
          }
        />
      )}

      {/* ── Job list ─────────────────────────────────────────────────────── */}
      {!loading && !error && processed.length > 0 && (
        <>
          {/* Desktop table */}
          <div className="hidden md:block rounded-xl border border-gray-800 overflow-hidden">
            {/* Header */}
            <div className="grid grid-cols-[1fr_100px_120px_100px_80px] gap-4 px-5 py-3 bg-gray-900 border-b border-gray-800 text-xs font-medium text-gray-500 uppercase tracking-wide">
              <span>Job</span>
              <span>VRAM</span>
              <span>Peer</span>
              <span>Submitted</span>
              <span>Status</span>
            </div>

            {/* Rows */}
            <div className="divide-y divide-gray-800 bg-gray-900/40">
              {processed.map((job) => (
                <Link
                  key={job.id}
                  to={`/jobs/${job.id}`}
                  id={`job-row-${job.id}`}
                  className="grid grid-cols-[1fr_100px_120px_100px_80px] gap-4 items-center px-5 py-3.5 hover:bg-gray-800/50 transition-colors"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-white font-medium truncate">{job.name}</p>
                    <p className="text-xs text-gray-500 font-mono truncate mt-0.5">
                      {job.docker_image || job.workload_type || job.command || '—'}
                    </p>
                  </div>
                  <span className="text-xs text-gray-400 whitespace-nowrap">
                    {formatVram(job.vram_required_mb)}
                  </span>
                  <span className="text-xs text-gray-500 truncate">
                    {job.peer_hostname ?? '—'}
                  </span>
                  <span className="text-xs text-gray-500 whitespace-nowrap">
                    {timeAgo(job.submitted_at)}
                  </span>
                  <Badge status={job.status} />
                </Link>
              ))}
            </div>
          </div>

          {/* Mobile stacked cards */}
          <div className="md:hidden space-y-3">
            {processed.map((job) => (
              <Link
                key={job.id}
                to={`/jobs/${job.id}`}
                id={`job-card-${job.id}`}
                className="block rounded-xl border border-gray-800 bg-gray-900 px-4 py-4 hover:bg-gray-800/50 transition-colors"
              >
                <div className="flex items-start justify-between gap-3 mb-2">
                  <p className="text-sm font-medium text-white leading-snug">{job.name}</p>
                  <Badge status={job.status} className="flex-shrink-0" />
                </div>
                <p className="text-xs text-gray-500 font-mono truncate mb-2">
                  {job.docker_image || job.workload_type || job.command || '—'}
                </p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                  <span>{formatVram(job.vram_required_mb)} VRAM</span>
                  {job.peer_hostname && <span>{job.peer_hostname}</span>}
                  <span>{timeAgo(job.submitted_at)}</span>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </PageLayout>
  );
}

function SearchIcon() {
  return (
    <svg
      className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500"
      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  );
}
