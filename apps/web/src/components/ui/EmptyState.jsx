/**
 * EmptyState — no-data placeholder.
 *
 * Props:
 *   title       — string  Primary message (e.g. "No peers registered")
 *   description — string (optional) Supporting context
 *   action      — React node (optional) CTA button or link
 */

/**
 * @param {{
 *   title: string,
 *   description?: string,
 *   action?: React.ReactNode,
 * }} props
 */
export default function EmptyState({ title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center px-4">
      {/* Icon */}
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-gray-800 bg-gray-900">
        <svg
          className="h-6 w-6 text-gray-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
          />
        </svg>
      </div>

      <h3 className="text-sm font-semibold text-gray-300 mb-1">{title}</h3>

      {description && (
        <p className="text-sm text-gray-500 max-w-sm">{description}</p>
      )}

      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
