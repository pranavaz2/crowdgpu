/**
 * usePeers — fetches the list of registered peers.
 *
 * Supports optional polling for pages that need live updates.
 * By default, polling is disabled — use the refetch() return value
 * for manual refresh.
 *
 * Mock mode (VITE_USE_MOCK=true):
 *   Returns local mock data. No network call.
 *
 * Real mode (VITE_USE_MOCK=false):
 *   Calls GET /api/v1/peers. Shows a real error if unavailable.
 *   Does NOT fall back to mock data on failure.
 *
 * Options:
 *   pollingInterval — number (ms) | undefined
 *     When set, polls the service at the given interval.
 *     Set to 0 or undefined to disable polling (default).
 *     Only enable on the Dashboard; leave manual on Resources page.
 *
 * Returns:
 *   data    — PeerResponse[] | null
 *   loading — boolean
 *   error   — Error | null
 *   refetch — function to manually trigger a refresh
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { listPeers } from '../services/peersService.js';

/**
 * @param {{ pollingInterval?: number }} [options]
 * @returns {{ data: object[]|null, loading: boolean, error: Error|null, refetch: function }}
 */
export function usePeers({ pollingInterval } = {}) {
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
      const result = await listPeers();
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
