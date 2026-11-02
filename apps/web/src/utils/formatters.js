/**
 * CrowdGPU shared formatting utilities.
 *
 * Rules:
 *   - Pure functions only — no React, no side effects, no imports.
 *   - Every function handles null / undefined / invalid input gracefully.
 *   - Return '—' (em dash) for missing/unknown values, not empty string.
 */

// ---------------------------------------------------------------------------
// VRAM
// ---------------------------------------------------------------------------

/**
 * Convert MiB to a human-readable VRAM string.
 *
 * Examples:
 *   8192  → "8 GB"
 *   24576 → "24 GB"
 *   81920 → "80 GB"
 *   512   → "512 MB"
 *   null  → "—"
 *
 * @param {number|null|undefined} vram_mb  VRAM in mebibytes (MiB)
 * @returns {string}
 */
export function formatVram(vram_mb) {
  if (vram_mb == null || typeof vram_mb !== 'number' || isNaN(vram_mb)) return '—';
  if (vram_mb <= 0) return '—';

  if (vram_mb >= 1024) {
    const gb = vram_mb / 1024;
    // Round to nearest integer when within 0.1 GB, otherwise one decimal.
    return `${Math.abs(gb - Math.round(gb)) < 0.05 ? Math.round(gb) : gb.toFixed(1)} GB`;
  }

  return `${vram_mb} MB`;
}

/**
 * Sum VRAM across an array of GPU capability objects and format the result.
 *
 * @param {Array<{ vram_mb: number }>|null|undefined} gpus
 * @returns {string}
 */
export function sumVram(gpus) {
  if (!Array.isArray(gpus) || gpus.length === 0) return '—';
  const total = gpus.reduce((acc, g) => acc + (Number(g?.vram_mb) || 0), 0);
  return total > 0 ? formatVram(total) : '—';
}

// ---------------------------------------------------------------------------
// Dates
// ---------------------------------------------------------------------------

/**
 * Return a relative "time ago" string from an ISO datetime.
 *
 * Examples:
 *   (5 seconds old)  → "just now"
 *   (45 seconds old) → "45s ago"
 *   (3 minutes old)  → "3m ago"
 *   (2 hours old)    → "2h ago"
 *   (3 days old)     → "3d ago"
 *   null             → "—"
 *   invalid string   → "—"
 *
 * @param {string|null|undefined} isoString
 * @returns {string}
 */
export function timeAgo(isoString) {
  if (!isoString) return '—';

  const date = new Date(isoString);
  if (isNaN(date.getTime())) return '—';

  const diffMs = Date.now() - date.getTime();
  if (diffMs < 0) return 'just now';

  const seconds = Math.floor(diffMs / 1000);
  if (seconds <= 8)  return 'just now';
  if (seconds < 60)  return `${seconds}s ago`;

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60)  return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24)    return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * Format an ISO datetime string for display in the UI.
 *
 * Example: "Oct 8, 2026, 18:30"
 *
 * @param {string|null|undefined} isoString
 * @returns {string}
 */
export function formatDateTime(isoString) {
  if (!isoString) return '—';

  const date = new Date(isoString);
  if (isNaN(date.getTime())) return '—';

  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format an ISO datetime as a short date only (no time).
 *
 * Example: "Oct 8, 2026"
 *
 * @param {string|null|undefined} isoString
 * @returns {string}
 */
export function formatDate(isoString) {
  if (!isoString) return '—';

  const date = new Date(isoString);
  if (isNaN(date.getTime())) return '—';

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// ---------------------------------------------------------------------------
// Statuses
// ---------------------------------------------------------------------------

/**
 * Peer / job status labels.
 * Maps internal status strings to user-facing labels.
 *
 * @param {string|null|undefined} status
 * @returns {string}
 */
export function formatStatus(status) {
  const labels = {
    available: 'Available',
    busy:      'Busy',
    offline:   'Offline',
    queued:    'Queued',
    matching:  'Matching',
    assigned:  'Assigned',
    running:   'Running',
    completed: 'Completed',
    failed:    'Failed',
  };

  if (!status) return '—';
  return labels[status.toLowerCase()] ?? capitalise(status);
}

// ---------------------------------------------------------------------------
// Strings
// ---------------------------------------------------------------------------

/**
 * Capitalise the first character of a string.
 *
 * @param {string|null|undefined} str
 * @returns {string}
 */
export function capitalise(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Truncate a string to a maximum length, appending '…' if truncated.
 *
 * @param {string|null|undefined} str
 * @param {number} max
 * @returns {string}
 */
export function truncate(str, max = 40) {
  if (!str) return '—';
  return str.length <= max ? str : `${str.slice(0, max)}…`;
}

// ---------------------------------------------------------------------------
// Numbers
// ---------------------------------------------------------------------------

/**
 * Format a plain integer with locale separators.
 *
 * @param {number|null|undefined} n
 * @returns {string}
 */
export function formatInt(n) {
  if (n == null || isNaN(n)) return '—';
  return Math.round(n).toLocaleString('en-US');
}
