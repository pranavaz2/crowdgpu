/**
 * PageLayout — reusable page wrapper.
 *
 * Provides:
 *   - max-width container (7xl)
 *   - consistent horizontal padding
 *   - vertical page spacing
 *   - optional page heading + description
 *
 * Props:
 *   children    — React node  Page content
 *   title       — string (optional) Page heading rendered as <h1>
 *   description — string (optional) Subtitle below heading
 *   actions     — React node (optional) Right-side header actions
 */

/**
 * @param {{
 *   children: React.ReactNode,
 *   title?: string,
 *   description?: string,
 *   actions?: React.ReactNode,
 * }} props
 */
export default function PageLayout({ children, title, description, actions }) {
  return (
    <main className="mx-auto max-w-7xl px-4 sm:px-6 py-8">
      {(title || actions) && (
        <div className="mb-8 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            {title && (
              <h1 className="text-2xl font-semibold tracking-tight text-white">
                {title}
              </h1>
            )}
            {description && (
              <p className="mt-1 text-sm text-gray-400 max-w-2xl">{description}</p>
            )}
          </div>
          {actions && (
            <div className="flex-shrink-0">{actions}</div>
          )}
        </div>
      )}

      {children}
    </main>
  );
}
