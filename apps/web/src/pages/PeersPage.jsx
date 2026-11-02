/**
 * PeersPage — /peers route
 *
 * Visible title: "GPU Resources"
 * Browse connected providers and their GPU capabilities.
 *
 * Features:
 *   - Text search (hostname, GPU name, driver, CUDA, compute capability)
 *   - Status filter (all / available / busy / offline)
 *   - Sort (hostname, GPU name, VRAM, status, last seen)
 *   - Expandable GPU capability detail per provider card
 *
 * Data source:
 *   Mock  → listPeers() via usePeers() hook
 *   (GET /api/v1/peers not yet implemented in coordinator)
 */

import { useMemo, useState } from 'react';
import PageLayout from '../components/layout/PageLayout.jsx';
import Badge from '../components/ui/Badge.jsx';
import LoadingSpinner from '../components/ui/LoadingSpinner.jsx';
import ErrorMessage from '../components/ui/ErrorMessage.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import { usePeers } from '../hooks/usePeers.js';
import { formatVram, timeAgo, formatDateTime } from '../utils/formatters.js';

// ── Sort options ─────────────────────────────────────────────────────────────
const SORT_OPTIONS = [
  { value: 'hostname',  label: 'Hostname'  },
  { value: 'gpu_name',  label: 'GPU Name'  },
  { value: 'vram',      label: 'VRAM'      },
  { value: 'status',    label: 'Status'    },
  { value: 'last_seen', label: 'Last Seen' },
];

const STATUS_FILTERS = ['all', 'available', 'busy', 'offline'];

// Status sort order for consistent grouping
const STATUS_ORDER = { available: 0, busy: 1, offline: 2 };

export default function PeersPage() {
  const { data: peers, loading, error, refetch } = usePeers();

  const [search, setSearch]         = useState('');
  const [statusFilter, setStatus]   = useState('all');
  const [sortBy, setSortBy]         = useState('status');
  const [sortDir, setSortDir]       = useState('asc');

  // ── Filter and sort ────────────────────────────────────────────────────
  const processed = useMemo(() => {
    if (!peers) return [];

    const q = search.trim().toLowerCase();

    let list = peers.filter((peer) => {
      // Status filter
      if (statusFilter !== 'all' && peer.status !== statusFilter) return false;

      // Search across hostname + GPU fields
      if (q) {
        const gpuText = (peer.gpu_capabilities ?? [])
          .map((g) =>
            [g.gpu_name, g.driver_version, g.cuda_version, g.compute_capability]
              .filter(Boolean)
              .join(' ')
          )
          .join(' ')
          .toLowerCase();

        const peerText = [peer.hostname].filter(Boolean).join(' ').toLowerCase();

        if (!peerText.includes(q) && !gpuText.includes(q)) return false;
      }

      return true;
    });

    // Sort
    list = [...list].sort((a, b) => {
      let cmp = 0;

      switch (sortBy) {
        case 'hostname':
          cmp = (a.hostname ?? '').localeCompare(b.hostname ?? '');
          break;

        case 'gpu_name': {
          const ag = a.gpu_capabilities?.[0]?.gpu_name ?? '';
          const bg = b.gpu_capabilities?.[0]?.gpu_name ?? '';
          cmp = ag.localeCompare(bg);
          break;
        }

        case 'vram': {
          const av = a.gpu_capabilities?.reduce((s, g) => s + g.vram_mb, 0) ?? 0;
          const bv = b.gpu_capabilities?.reduce((s, g) => s + g.vram_mb, 0) ?? 0;
          cmp = av - bv;
          break;
        }

        case 'status':
          cmp = (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9);
          break;

        case 'last_seen': {
          const at = a.last_seen_at ? new Date(a.last_seen_at).getTime() : 0;
          const bt = b.last_seen_at ? new Date(b.last_seen_at).getTime() : 0;
          cmp = bt - at; // descending by default (most recent first)
          break;
        }

        default:
          cmp = 0;
      }

      return sortDir === 'asc' ? cmp : -cmp;
    });

    return list;
  }, [peers, search, statusFilter, sortBy, sortDir]);

  // ── Status counts for filter buttons ──────────────────────────────────
  const counts = useMemo(() => {
    if (!peers) return {};
    return peers.reduce((acc, p) => {
      acc[p.status] = (acc[p.status] ?? 0) + 1;
      return acc;
    }, {});
  }, [peers]);

  // ── Toggle sort ────────────────────────────────────────────────────────
  function handleSort(value) {
    if (sortBy === value) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(value);
      setSortDir('asc');
    }
  }

  return (
    <PageLayout
      title="GPU Resources"
      description="Browse connected providers and their GPU capabilities."
    >
      {/* ── Controls bar ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <SearchIcon />
          <input
            id="input-peer-search"
            type="search"
            placeholder="Search providers or GPUs…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 pl-9 pr-3 py-2 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 transition-colors"
          />
        </div>

        {/* Status filters */}
        <div className="flex items-center gap-2 flex-wrap">
          {STATUS_FILTERS.map((s) => {
            const count = s === 'all' ? (peers?.length ?? 0) : (counts[s] ?? 0);
            return (
              <button
                key={s}
                id={`filter-status-${s}`}
                onClick={() => setStatus(s)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors flex items-center gap-1.5 ${
                  statusFilter === s
                    ? 'bg-brand-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'
                }`}
              >
                {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
                <span className={`${statusFilter === s ? 'text-brand-200' : 'text-gray-600'}`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Sort */}
        <div className="flex items-center gap-2 ml-auto flex-shrink-0">
          <span className="text-xs text-gray-500">Sort:</span>
          <select
            id="select-peer-sort"
            value={sortBy}
            onChange={(e) => handleSort(e.target.value)}
            className="rounded-md border border-gray-700 bg-gray-800 px-2 py-1.5 text-xs text-white focus:border-brand-500 focus:outline-none"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button
            id="btn-sort-direction"
            onClick={() => setSortDir((d) => d === 'asc' ? 'desc' : 'asc')}
            className="text-gray-400 hover:text-white transition-colors text-sm w-6 text-center"
            title={sortDir === 'asc' ? 'Ascending — click for descending' : 'Descending — click for ascending'}
          >
            {sortDir === 'asc' ? '↑' : '↓'}
          </button>
        </div>
      </div>

      {/* ── Result summary ─────────────────────────────────────────────────── */}
      {!loading && !error && peers && (
        <p className="text-xs text-gray-500 mb-4">
          {processed.length === peers.length
            ? `${peers.length} provider${peers.length !== 1 ? 's' : ''}`
            : `${processed.length} of ${peers.length} providers`}
          {search && ` matching "${search}"`}
          {' · '}
          <button
            className="text-brand-400 hover:text-brand-300 transition-colors"
            onClick={refetch}
          >
            Refresh
          </button>
        </p>
      )}

      {/* ── States ─────────────────────────────────────────────────────────── */}
      {loading && (
        <div className="py-24 flex items-center justify-center">
          <LoadingSpinner size="lg" label="Loading providers…" />
        </div>
      )}

      {error && (
        <ErrorMessage message={error} onRetry={refetch} />
      )}

      {!loading && !error && processed.length === 0 && (
        <EmptyState
          title={
            search
              ? `No results for "${search}"`
              : statusFilter !== 'all'
              ? `No ${statusFilter} providers`
              : 'No providers registered'
          }
          description={
            !peers || peers.length === 0
              ? 'Start the CrowdGPU worker daemon on a provider machine to register its GPUs.'
              : 'Try adjusting the search or filter.'
          }
          action={
            (search || statusFilter !== 'all') && (
              <button
                onClick={() => { setSearch(''); setStatus('all'); }}
                className="text-xs text-brand-400 hover:text-brand-300 transition-colors"
              >
                Clear filters
              </button>
            )
          }
        />
      )}

      {/* ── Provider cards grid ─────────────────────────────────────────────── */}
      {!loading && !error && processed.length > 0 && (
        <div className="space-y-4">
          {processed.map((peer) => (
            <ProviderCard key={peer.id} peer={peer} />
          ))}
        </div>
      )}
    </PageLayout>
  );
}

// ============================================================================
// ProviderCard
// ============================================================================

function ProviderCard({ peer }) {
  const [expanded, setExpanded] = useState(false);

  const gpuCount    = peer.gpu_capabilities?.length ?? 0;
  const totalVramMb = peer.gpu_capabilities?.reduce((s, g) => s + g.vram_mb, 0) ?? 0;
  const primaryGpu  = peer.gpu_capabilities?.[0];

  return (
    <div
      className={`rounded-xl border bg-gray-900 overflow-hidden transition-colors ${
        peer.status === 'available'
          ? 'border-gray-800'
          : peer.status === 'busy'
          ? 'border-gray-800'
          : 'border-gray-800/50 opacity-75'
      }`}
    >
      {/* ── Card header ────────────────────────────────────────────────────── */}
      <div className="px-5 py-4 flex items-start gap-4">

        {/* Status dot */}
        <div className="mt-1 flex-shrink-0">
          <StatusDot status={peer.status} />
        </div>

        {/* Primary info */}
        <div className="flex-1 min-w-0 grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-2">

          {/* Hostname + status */}
          <div className="sm:col-span-1">
            <p className="text-xs text-gray-500 mb-0.5">Provider</p>
            <p className="text-sm font-semibold text-white font-mono truncate">{peer.hostname}</p>
            <Badge status={peer.status} className="mt-1.5" />
          </div>

          {/* Primary GPU */}
          <div className="sm:col-span-1">
            <p className="text-xs text-gray-500 mb-0.5">GPU{gpuCount > 1 ? 's' : ''}</p>
            {primaryGpu ? (
              <>
                <p className="text-sm font-medium text-white leading-snug">{primaryGpu.gpu_name}</p>
                {gpuCount > 1 && (
                  <p className="text-xs text-gray-500 mt-0.5">+{gpuCount - 1} more</p>
                )}
              </>
            ) : (
              <p className="text-sm text-gray-500">—</p>
            )}
          </div>

          {/* VRAM + timestamps */}
          <div className="sm:col-span-1 flex flex-col gap-1">
            <div>
              <p className="text-xs text-gray-500 mb-0.5">Total VRAM</p>
              <p className="text-sm font-semibold text-white tabular-nums">
                {gpuCount > 0 ? formatVram(totalVramMb) : '—'}
              </p>
            </div>
            <p className="text-xs text-gray-500">
              Last seen: <span className="text-gray-400">{timeAgo(peer.last_seen_at)}</span>
            </p>
          </div>
        </div>

        {/* Expand toggle */}
        {gpuCount > 0 && (
          <button
            id={`btn-expand-peer-${peer.id}`}
            onClick={() => setExpanded((v) => !v)}
            className="flex-shrink-0 ml-2 text-xs text-gray-500 hover:text-white transition-colors pt-0.5"
            aria-expanded={expanded}
            aria-label={expanded ? 'Collapse GPU details' : 'Expand GPU details'}
          >
            {expanded ? '▲' : '▼'}
          </button>
        )}
      </div>

      {/* ── Expanded GPU details ───────────────────────────────────────────── */}
      {expanded && peer.gpu_capabilities && peer.gpu_capabilities.length > 0 && (
        <div className="border-t border-gray-800">
          <div className="px-5 py-2 bg-gray-950/40">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              GPU Capabilities
            </p>
          </div>

          <div className="divide-y divide-gray-800/60">
            {peer.gpu_capabilities.map((gpu, idx) => (
              <GpuDetailRow key={gpu.id} gpu={gpu} index={idx} />
            ))}
          </div>

          {/* Registered date */}
          <div className="px-5 py-3 bg-gray-950/20 border-t border-gray-800/60">
            <p className="text-xs text-gray-600">
              Registered: {formatDateTime(peer.registered_at)}
              <span className="mx-2">·</span>
              Peer ID: <span className="font-mono">{peer.id}</span>
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── GPU detail row (inside expanded card) ────────────────────────────────────

function GpuDetailRow({ gpu, index }) {
  return (
    <div className="px-5 py-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
      <div className="col-span-2 sm:col-span-3 md:col-span-2">
        <dt className="text-xs text-gray-500 mb-0.5">GPU {index + 1}</dt>
        <dd className="text-sm font-semibold text-white">{gpu.gpu_name}</dd>
      </div>

      <GpuField label="VRAM"                value={formatVram(gpu.vram_mb)} />
      <GpuField label="CUDA Version"        value={gpu.cuda_version}        mono />
      <GpuField label="Compute Capability"  value={gpu.compute_capability}  mono />
      <GpuField label="Driver Version"      value={gpu.driver_version}      mono className="col-span-2 sm:col-span-1" />
    </div>
  );
}

function GpuField({ label, value, mono = false, className = '' }) {
  return (
    <div className={className}>
      <dt className="text-xs text-gray-500 mb-0.5">{label}</dt>
      <dd className={`text-sm text-white ${mono ? 'font-mono text-gray-300' : ''}`}>
        {value ?? '—'}
      </dd>
    </div>
  );
}

// ── Animated status dot ──────────────────────────────────────────────────────

function StatusDot({ status }) {
  const colours = {
    available: 'bg-emerald-500',
    busy:      'bg-amber-500',
    offline:   'bg-gray-600',
  };

  const dot = colours[status] ?? 'bg-gray-600';
  const pulse = status === 'available';

  return (
    <span className="relative flex h-2.5 w-2.5">
      {pulse && (
        <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${dot} opacity-40`} />
      )}
      <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${dot}`} />
    </span>
  );
}

// ── Search icon ──────────────────────────────────────────────────────────────

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
