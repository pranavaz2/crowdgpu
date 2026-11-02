/**
 * ErrorMessage — inline error display.
 *
 * Props:
 *   title   — string (optional) Override default "Something went wrong"
 *   message — string | Error  Error detail text
 *   onRetry — function (optional) If provided, a Retry button is rendered
 */

/**
 * @param {{
 *   title?: string,
 *   message: string | Error,
 *   onRetry?: () => void,
 * }} props
 */
export default function ErrorMessage({ title, message, onRetry }) {
  const text =
    message instanceof Error ? message.message : String(message ?? 'An unexpected error occurred.');

  return (
    <div
      role="alert"
      className="rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-4 flex items-start gap-3"
    >
      {/* Error icon */}
      <svg
        className="h-5 w-5 flex-shrink-0 text-red-500 mt-0.5"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
          clipRule="evenodd"
        />
      </svg>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-red-400">
          {title || 'Something went wrong'}
        </p>
        <p className="mt-0.5 text-sm text-red-400/70">{text}</p>

        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 text-xs font-medium text-red-400 underline underline-offset-2 hover:text-red-300 transition-colors"
          >
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
