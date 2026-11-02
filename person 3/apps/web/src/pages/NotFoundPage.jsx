/**
 * NotFoundPage — * (catch-all) route.
 *
 * Shown when a URL does not match any defined route.
 */

import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-24 flex flex-col items-center text-center">
      <p className="text-5xl font-semibold text-gray-800 mb-4 tabular-nums">404</p>
      <h1 className="text-xl font-semibold text-white mb-2">Page not found</h1>
      <p className="text-sm text-gray-500 mb-8 max-w-xs">
        The page you are looking for does not exist or has been moved.
      </p>
      <Link
        to="/"
        id="link-404-dashboard"
        className="inline-flex items-center rounded-md border border-gray-700 bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:text-white hover:bg-gray-700 transition-colors"
      >
        ← Back to Dashboard
      </Link>
    </div>
  );
}
