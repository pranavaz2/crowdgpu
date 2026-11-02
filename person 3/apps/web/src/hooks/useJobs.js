/**
 * useJobs — fetches the list of jobs.
 *
 * Supports optional polling for pages that need live status updates.
 * By default, polling is disabled — use refetch() for manual refresh.
 *
 * Mock mode (VITE_USE_MOCK=true):
 *   Returns data from sessionStorage/seed. No network call.
 *
 * Real mode (VITE_USE_MOCK=false):
 *   Will call GET /api/v1/jobs once the coordinator implements it.
 *   Currently throws a clear "not yet available" error.
 *   Does NOT fall back to mock data on failure.
 *
 * Options:
 *   pollingInterval — number (ms) | undefined
 *     When set, polls at the given interval. Intended for JobDetailPage
 *     once live status updates are needed.
 *
 * Returns:
 *   data    — job[] | null
 *   loading — boolean
 *   error   — Error | null
 *   refetch — function to manually trigger a refresh
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { listJobs } from '../services/jobsService.js';

/**
 * @param {{ pollingInterval?: number }} [options]
 * @returns {{ data: object[]|null, loading: boolean, error: Error|null, refetch: function }}
 */
export function useJobs({ pollingInterval } = {}) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  const mountedRef  = useRef(true);
  const intervalRef = useRef(null);
  const reqIdRef    = useRef(0);

  const doFetch = useCallback(async () => {
    const thisId = ++reqIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const result = await listJobs();
      if (mountedRef.current && thisId === reqIdRef.current) {
        setData(result);
      }
    } catch (err) {
      if (mountedRef.current && thisId === reqIdRef.current) {
        setError(err);
      }
    } finally {
      if (mountedRef.current && thisId === reqIdRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;

    doFetch();

    if (pollingInterval && pollingInterval > 0) {
      intervalRef.current = setInterval(doFetch, pollingInterval);
    }

    return () => {
      mountedRef.current = false;
      clearInterval(intervalRef.current);
    };
  }, [doFetch, pollingInterval]);

  return { data, loading, error, refetch: doFetch };
}
