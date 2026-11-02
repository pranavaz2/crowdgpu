/**
 * StatCard — metric summary card.
 *
 * Props:
 *   title       — string  Card heading (e.g. "Active Peers")
 *   value       — string | number  Primary metric value
 *   description — string  (optional) Supporting context text
 *   icon        — React node (optional) Icon rendered above the value
 *   loading     — boolean (optional) Show skeleton when true
 */

/**
 * @param {{
 *   title: string,
 *   value: string | number,
 *   description?: string,
 *   icon?: React.ReactNode,
 *   loading?: boolean,
 * }} props
 */
export default function StatCard({ title, value, description, icon, loading = false }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
      {icon && (
        <div className="mb-3 text-gray-500">
          {icon}
        </div>
      )}

      {loading ? (
        <>
          <div className="h-7 w-16 rounded bg-gray-800 animate-pulse mb-2" />
          <div className="h-3 w-24 rounded bg-gray-800 animate-pulse" />
        </>
      ) : (
        <>
          <div className="text-2xl font-semibold text-white tabular-nums mb-1">
            {value ?? '—'}
          </div>
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
            {title}
          </div>
          {description && (
            <div className="mt-1 text-xs text-gray-600">{description}</div>
          )}
        </>
      )}
    </div>
  );
}
