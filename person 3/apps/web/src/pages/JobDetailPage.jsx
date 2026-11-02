/**
 * JobDetailPage — /jobs/:id route
 *
 * Execution detail view for a single GPU workload.
 *
 * Sections:
 *   Header   — job name, ID, status badge, refresh
 *   Workload — docker image, command, VRAM, type
 *   Assignment — peer, GPU (shown only when assigned)
 *   Timeline — stage checkmarks derived from actual timestamps
 *   Result   — success message / error / awaiting states
 *
 * Data source:
 *   Mock → getJob(id) via jobsService (no coordinator job API yet)
 *
 * When GET /api/v1/jobs/{job_id} is implemented, update jobsService.js only.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import PageLayout from '../components/layout/PageLayout.jsx';
import Badge from '../components/ui/Badge.jsx';
import LoadingSpinner from '../components/ui/LoadingSpinner.jsx';
import ErrorMessage from '../components/ui/ErrorMessage.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import { getJob, cancelJob } from '../services/jobsService.js';
import { formatVram, formatDateTime, timeAgo } from '../utils/formatters.js';

export default function JobDetailPage() {
  const { id } = useParams();
  const [job,         setJob]         = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState(null);
  const [cancelling,  setCancelling]  = useState(false);
  const [cancelError, setCancelError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getJob(id);
      setJob(result);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function handleCancel() {
    if (!job || cancelling) return;
    setCancelling(true);
    setCancelError(null);
    try {
      const updated = await cancelJob(id);
      setJob(updated);
    } catch (err) {
      setCancelError(err);
    } finally {
      setCancelling(false);
    }
  }

  // ── Not found ────────────────────────────────────────────────────────────
  if (!loading && error?.status === 404) {
    return (
      <PageLayout title="Job Not Found">
        <EmptyState
          title="Job not found"
          description="The requested job does not exist or may have been removed."
          action={
            <Link
              to="/jobs"
              className="inline-flex items-center rounded-md bg-gray-800 border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:text-white transition-colors"
            >
              ← Back to Jobs
            </Link>
          }
        />
      </PageLayout>
    );
  }

  return (
    <PageLayout
      title={loading ? 'Job Detail' : (job?.name ?? 'Job Detail')}
      description={job ? `Job ID: ${job.id}` : undefined}
      actions={
        <div className="flex items-center gap-3">
          <button
            id="btn-refresh-job"
            onClick={load}
            disabled={loading}
            className="text-xs text-gray-500 hover:text-white transition-colors disabled:opacity-40"
          >
            ↻ Refresh
          </button>
          <Link to="/jobs" className="text-sm text-gray-400 hover:text-white transition-colors">
            ← Back to jobs
          </Link>
        </div>
      }
    >
      {loading && (
        <div className="py-20">
          <LoadingSpinner size="lg" label="Loading job…" />
        </div>
      )}

      {error && !loading && error.status !== 404 && (
        <ErrorMessage message={error} onRetry={load} />
      )}

      {!loading && !error && job && (
        <div className="space-y-6 max-w-3xl">

          {/* ── Status header card ──────────────────────────────────────── */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 px-5 py-4">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="space-y-2">
                <div className="flex items-center gap-3 flex-wrap">
                  <Badge status={job.status} />
                  <span className="text-xs text-gray-500 font-mono">{job.id}</span>
                </div>
                <p className="text-xl font-semibold text-white">{job.name}</p>
                <p className="text-xs text-gray-500">
                  Submitted {timeAgo(job.submitted_at)} · {formatDateTime(job.submitted_at)}
                </p>
              </div>

              {/* Cancel button — only for cancellable statuses */}
              {['queued', 'matching', 'assigned'].includes(job.status) && (
                <div className="flex flex-col items-end gap-1">
                  <button
                    id="btn-cancel-job"
                    onClick={handleCancel}
                    disabled={cancelling}
                    className="rounded-md border border-red-900/60 bg-red-950/30 px-3 py-1.5 text-xs text-red-400 hover:bg-red-950/60 disabled:opacity-40 transition-colors"
                  >
                    {cancelling ? 'Cancelling…' : 'Cancel Job'}
                  </button>
                  {cancelError && (
                    <p className="text-xs text-red-400">{cancelError.message}</p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* ── Workload ─────────────────────────────────────────────────── */}
          <Section title="Workload">
            <DetailRow label="Docker Image"   value={job.docker_image}  mono />
            <DetailRow label="Command"        value={job.command}       mono />
            <DetailRow label="Required VRAM"  value={formatVram(job.vram_required_mb)} />
            <DetailRow label="Workload Type"  value={
              job.workload_type
                ? job.workload_type.charAt(0).toUpperCase() + job.workload_type.slice(1)
                : '—'
            } />
          </Section>

          {/* ── Assignment ───────────────────────────────────────────────── */}
          <Section title="Assignment">
            {job.peer_hostname ? (
              <>
                <DetailRow label="Peer"    value={job.peer_hostname} mono />
                <DetailRow label="GPU"     value={job.gpu_name}      />
                <DetailRow label="Peer ID" value={job.peer_id}       mono />
              </>
            ) : (
              <div className="px-5 py-5 text-center">
                <p className="text-sm text-gray-500">Waiting for GPU assignment</p>
                <p className="text-xs text-gray-600 mt-1">
                  The scheduler will assign a provider once one meets the VRAM requirement.
                </p>
              </div>
            )}
          </Section>

          {/* ── Timeline ─────────────────────────────────────────────────── */}
          <Section title="Timeline">
            <div className="px-5 py-4">
              <JobTimeline job={job} />
            </div>
          </Section>

          {/* ── Result / Error / Awaiting ─────────────────────────────────── */}
          <ResultSection job={job} />

        </div>
      )}
    </PageLayout>
  );
}

// ============================================================================
// Timeline
// ============================================================================

const STAGES = [
  { key: 'submitted', label: 'Submitted', tsField: 'submitted_at' },
  { key: 'matching',  label: 'Matching',  tsField: 'matching_at'  },
  { key: 'assigned',  label: 'Assigned',  tsField: 'assigned_at'  },
  { key: 'started',   label: 'Started',   tsField: 'started_at'   },
  { key: 'completed', label: 'Completed / Failed', tsField: 'completed_at' },
];

function JobTimeline({ job }) {
  return (
    <ol className="relative space-y-0">
      {STAGES.map((stage, idx) => {
        const ts = job[stage.tsField];
        const isDone = Boolean(ts);
        const isLast = idx === STAGES.length - 1;

        // For the final stage, check failed vs completed
        let label = stage.label;
        if (stage.key === 'completed' && job.status === 'failed' && job.completed_at) {
          label = 'Failed';
        } else if (stage.key === 'completed' && job.status === 'completed' && job.completed_at) {
          label = 'Completed';
        }

        return (
          <li key={stage.key} className="flex gap-4 pb-4 last:pb-0">
            {/* Track */}
            <div className="flex flex-col items-center">
              <div
                className={`h-6 w-6 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                  isDone
                    ? stage.key === 'completed' && job.status === 'failed'
                      ? 'border-red-600 bg-red-900/40'
                      : 'border-emerald-600 bg-emerald-900/30'
                    : 'border-gray-700 bg-gray-900'
                }`}
              >
                {isDone ? (
                  stage.key === 'completed' && job.status === 'failed' ? (
                    <svg className="h-3 w-3 text-red-400" viewBox="0 0 12 12" fill="currentColor">
                      <path d="M4 4l4 4M8 4L4 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none"/>
                    </svg>
                  ) : (
                    <svg className="h-3 w-3 text-emerald-400" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2 6l3 3 5-5" />
                    </svg>
                  )
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-600" />
                )}
              </div>
              {!isLast && (
                <div className={`w-0.5 flex-1 mt-1 ${isDone ? 'bg-emerald-900/60' : 'bg-gray-800'}`} />
              )}
            </div>

            {/* Content */}
            <div className="pb-4 min-w-0">
              <p className={`text-sm font-medium ${isDone ? 'text-white' : 'text-gray-600'}`}>
                {label}
              </p>
              {ts ? (
                <p className="text-xs text-gray-500 mt-0.5">
                  {formatDateTime(ts)}
                  <span className="ml-2 text-gray-600">({timeAgo(ts)})</span>
                </p>
              ) : (
                <p className="text-xs text-gray-700 mt-0.5">Pending</p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// ============================================================================
// Result / Error / Awaiting section
// ============================================================================

function ResultSection({ job }) {
  if (job.status === 'completed' && job.result) {
    return (
      <div className="rounded-xl border border-emerald-900/50 bg-emerald-950/20 px-5 py-5">
        <p className="text-xs font-semibold text-emerald-500 uppercase tracking-wide mb-2">
          Result
        </p>
        <p className="text-sm text-emerald-300 leading-relaxed">{job.result}</p>
      </div>
    );
  }

  if (job.status === 'failed' && job.error) {
    return (
      <div className="rounded-xl border border-red-900/50 bg-red-950/20 px-5 py-5">
        <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-2">
          Error
        </p>
        <p className="text-sm text-red-300 font-mono leading-relaxed">{job.error}</p>
      </div>
    );
  }

  if (job.status === 'running') {
    return (
      <div className="rounded-xl border border-blue-900/40 bg-blue-950/10 px-5 py-5 flex items-center gap-4">
        <div className="h-2 w-2 rounded-full bg-blue-400 animate-pulse flex-shrink-0" />
        <div>
          <p className="text-sm text-blue-300 font-medium">Executing on provider GPU</p>
          <p className="text-xs text-blue-400/60 mt-0.5">
            Results will appear here when the job completes.
          </p>
        </div>
      </div>
    );
  }

  if (job.status === 'queued' || job.status === 'matching' || job.status === 'assigned') {
    return (
      <div className="rounded-xl border border-dashed border-gray-700 bg-gray-900/50 px-5 py-6 text-center">
        <p className="text-sm text-gray-500">
          {job.status === 'queued'
            ? 'Job is queued and waiting for a provider GPU.'
            : job.status === 'matching'
            ? 'Searching for a provider that meets the VRAM requirement.'
            : 'A provider GPU has been assigned — execution starting soon.'}
        </p>
      </div>
    );
  }

  return null;
}

// ============================================================================
// Layout helpers
// ============================================================================

function Section({ title, children }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{title}</p>
      </div>
      {children}
    </div>
  );
}

function DetailRow({ label, value, mono = false }) {
  return (
    <div className="flex justify-between items-start gap-4 px-5 py-3 border-b border-gray-800 last:border-b-0">
      <span className="text-sm text-gray-400 flex-shrink-0 w-32">{label}</span>
      <span
        className={`text-sm text-right break-all min-w-0 ${
          mono ? 'font-mono text-gray-300' : 'text-white'
        }`}
      >
        {value ?? '—'}
      </span>
    </div>
  );
}
