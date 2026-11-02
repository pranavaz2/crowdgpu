/**
 * CrowdGPU Web Portal — application root.
 *
 * This file is the router shell only.
 * Business logic lives in pages/ and hooks/.
 * Shared UI lives in components/.
 * API calls live in services/.
 */

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Navbar from './components/layout/Navbar.jsx';
import DashboardPage from './pages/DashboardPage.jsx';
import PeersPage from './pages/PeersPage.jsx';
import JobsPage from './pages/JobsPage.jsx';
import SubmitJobPage from './pages/SubmitJobPage.jsx';
import JobDetailPage from './pages/JobDetailPage.jsx';
import NotFoundPage from './pages/NotFoundPage.jsx';
import { isMockMode } from './utils/environment.js';

export default function App() {
  const mockMode = isMockMode();

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100 font-sans flex flex-col">
        <Navbar />

        <div className="flex-1">
          <Routes>
            {/* Dashboard */}
            <Route path="/" element={<DashboardPage />} />

            {/* GPU Resources / Peer registry */}
            <Route path="/peers" element={<PeersPage />} />

            {/* Jobs */}
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/jobs/submit" element={<SubmitJobPage />} />
            <Route path="/jobs/:id" element={<JobDetailPage />} />

            {/* 404 — unknown routes */}
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </div>

        <footer className="border-t border-gray-800/60 px-6 py-3 text-xs text-gray-700 flex items-center justify-between gap-4">
          <span>CrowdGPU v0.1.0</span>

          <div className="flex items-center gap-4">
            {/* Demo-mode indicator — shown only when VITE_USE_MOCK=true */}
            {mockMode && (
              <span
                className="inline-flex items-center gap-1.5 rounded border border-amber-900/50 bg-amber-950/20 px-2 py-0.5 text-xs text-amber-600"
                title="Peer and job data is using local mock/demo values. Set VITE_USE_MOCK=false to use the real Coordinator API."
              >
                <span className="h-1.5 w-1.5 rounded-full bg-amber-600 inline-block" />
                DEMO DATA
              </span>
            )}
            <span>Intelligent P2P GPU Resource Sharing Platform</span>
          </div>
        </footer>
      </div>
    </BrowserRouter>
  );
}
