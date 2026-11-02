/**
 * CrowdGPU Web Portal — placeholder dashboard.
 *
 * Bootstrap phase: this is a structural placeholder only.
 * Actual dashboard functionality will be implemented in a later phase.
 */

export default function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 font-sans flex flex-col">
      {/* ------------------------------------------------------------------ */}
      {/* Navigation */}
      {/* ------------------------------------------------------------------ */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
            </svg>
          </div>
          <span className="text-lg font-semibold tracking-tight">CrowdGPU</span>
        </div>

        <nav className="hidden md:flex items-center gap-6 text-sm text-gray-400">
          <a href="#" className="hover:text-white transition-colors">Dashboard</a>
          <a href="#" className="hover:text-white transition-colors">Jobs</a>
          <a href="#" className="hover:text-white transition-colors">Resources</a>
          <a href="#" className="hover:text-white transition-colors">Sessions</a>
        </nav>

        <div className="flex items-center gap-3">
          <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-amber-900/40 text-amber-400 border border-amber-800/50">
            Bootstrap Phase
          </span>
        </div>
      </header>

      {/* ------------------------------------------------------------------ */}
      {/* Main content */}
      {/* ------------------------------------------------------------------ */}
      <main className="flex-1 px-6 py-10 max-w-5xl mx-auto w-full">

        {/* Hero */}
        <div className="mb-10">
          <h1 className="text-3xl font-bold tracking-tight mb-2">
            Distributed GPU Platform
          </h1>
          <p className="text-gray-400 text-base max-w-xl">
            CrowdGPU connects consumers who need GPU compute with providers who have available
            resources — enabling batch workloads and interactive remote rendering.
          </p>
        </div>

        {/* Status banner */}
        <div className="mb-8 rounded-xl border border-brand-700/50 bg-brand-950/40 px-5 py-4 flex items-start gap-4">
          <div className="mt-0.5 w-2 h-2 rounded-full bg-amber-400 flex-shrink-0 animate-pulse" />
          <div>
            <p className="text-sm font-medium text-white">Repository Bootstrap Phase</p>
            <p className="text-sm text-gray-400 mt-0.5">
              The project skeleton has been created. Dashboard functionality, job submission,
              peer discovery and remote rendering will be implemented in subsequent phases.
            </p>
          </div>
        </div>

        {/* Placeholder stat cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
          {[
            { label: 'Active Peers',     value: '—', icon: '🖥️' },
            { label: 'Jobs Running',     value: '—', icon: '⚙️' },
            { label: 'GPU·Hours Used',   value: '—', icon: '📊' },
            { label: 'Available VRAM',   value: '—', icon: '🧠' },
          ].map((card) => (
            <div
              key={card.label}
              className="rounded-xl border border-gray-800 bg-gray-900 px-5 py-4"
            >
              <div className="text-2xl mb-2">{card.icon}</div>
              <div className="text-2xl font-bold text-gray-300 mb-1">{card.value}</div>
              <div className="text-xs text-gray-500 uppercase tracking-wide">{card.label}</div>
            </div>
          ))}
        </div>

        {/* Placeholder sections */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="text-base font-semibold mb-3">Recent Jobs</h2>
            <p className="text-sm text-gray-500">Job history will appear here once the job
            submission system is implemented.</p>
          </section>

          <section className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="text-base font-semibold mb-3">Available Resources</h2>
            <p className="text-sm text-gray-500">Peer GPU resources will appear here once the
            peer registry and matchmaker are implemented.</p>
          </section>
        </div>
      </main>

      {/* ------------------------------------------------------------------ */}
      {/* Footer */}
      {/* ------------------------------------------------------------------ */}
      <footer className="border-t border-gray-800 px-6 py-4 text-xs text-gray-600 flex justify-between">
        <span>CrowdGPU v0.1.0 — Bootstrap</span>
        <span>Intelligent P2P GPU Resource Sharing</span>
      </footer>
    </div>
  )
}
