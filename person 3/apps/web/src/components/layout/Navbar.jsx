/**
 * Navbar — top navigation bar for the CrowdGPU web portal.
 *
 * Uses React Router NavLink for active-state styling.
 * Navigation links: Dashboard, Resources, Jobs.
 * Sessions is intentionally excluded — no backend endpoint exists.
 */

import { NavLink } from 'react-router-dom';
import { useHealth } from '../../hooks/useHealth.js';

/** Brand icon — CPU/grid SVG */
function BrandIcon() {
  return (
    <svg
      className="h-5 w-5 text-white"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      aria-hidden="true"
    >
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <path d="M9 4v2M15 4v2M9 18v2M15 18v2M4 9h2M4 15h2M18 9h2M18 15h2" strokeLinecap="round" />
    </svg>
  );
}

/** Health dot — green when coordinator is reachable, gray otherwise */
function HealthDot({ health }) {
  const isOnline = health?.status === 'ok';

  return (
    <span className="flex items-center gap-1.5 text-xs text-gray-500" title="Coordinator status">
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${
          isOnline ? 'bg-emerald-500' : 'bg-gray-600'
        }`}
      />
      <span className="hidden sm:inline">
        {isOnline ? `Coordinator v${health.version}` : 'Coordinator offline'}
      </span>
    </span>
  );
}

/** Base classes for nav links */
const NAV_BASE =
  'text-sm transition-colors duration-150 hover:text-white';
const NAV_INACTIVE = 'text-gray-400';
const NAV_ACTIVE = 'text-white font-medium';

export default function Navbar() {
  const { data: health } = useHealth();

  function navClass({ isActive }) {
    return `${NAV_BASE} ${isActive ? NAV_ACTIVE : NAV_INACTIVE}`;
  }

  return (
    <header className="sticky top-0 z-30 border-b border-gray-800 bg-gray-950/90 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6">
        {/* Brand */}
        <NavLink
          to="/"
          className="flex items-center gap-2.5 flex-shrink-0 mr-2"
          aria-label="CrowdGPU home"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600">
            <BrandIcon />
          </div>
          <span className="text-base font-semibold tracking-tight text-white">
            CrowdGPU
          </span>
        </NavLink>

        {/* Primary navigation */}
        <nav className="flex items-center gap-5" aria-label="Primary navigation">
          <NavLink to="/" end className={navClass} id="nav-dashboard">
            Dashboard
          </NavLink>
          <NavLink to="/peers" className={navClass} id="nav-resources">
            Resources
          </NavLink>
          <NavLink to="/jobs" className={navClass} id="nav-jobs">
            Jobs
          </NavLink>
        </nav>

        {/* Right-side status */}
        <div className="ml-auto flex items-center gap-4">
          <HealthDot health={health} />

          {/* Submit Job CTA */}
          <NavLink
            to="/jobs/submit"
            id="nav-submit-job"
            className="hidden sm:inline-flex items-center rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-500 transition-colors"
          >
            + Submit Job
          </NavLink>
        </div>
      </div>
    </header>
  );
}
