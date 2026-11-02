/**
 * Badge — status pill component.
 *
 * Renders a colour-coded pill for peer and job statuses.
 *
 * Props:
 *   status  — 'available' | 'busy' | 'offline' | 'running' | 'queued'
 *             | 'completed' | 'failed' | string
 *   className — optional additional Tailwind classes
 */

const STATUS_STYLES = {
  // Peer statuses
  available: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/25',
  busy:      'bg-amber-500/15  text-amber-400  ring-amber-500/25',
  offline:   'bg-gray-500/15   text-gray-400   ring-gray-500/25',

  // Job statuses
  queued:    'bg-violet-500/15 text-violet-400  ring-violet-500/25',
  matching:  'bg-sky-500/15    text-sky-400     ring-sky-500/25',
  assigned:  'bg-indigo-500/15 text-indigo-400  ring-indigo-500/25',
  running:   'bg-blue-500/15   text-blue-400    ring-blue-500/25',
  completed: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/25',
  failed:    'bg-red-500/15    text-red-400     ring-red-500/25',
};

const STATUS_LABELS = {
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

/**
 * @param {{ status: string, className?: string }} props
 */
export default function Badge({ status, className = '' }) {
  const key = status?.toLowerCase();
  const style = STATUS_STYLES[key] || 'bg-gray-500/15 text-gray-400 ring-gray-500/25';
  const label = STATUS_LABELS[key] || status;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style} ${className}`}
    >
      {label}
    </span>
  );
}
