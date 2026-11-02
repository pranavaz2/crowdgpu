/**
 * useHealth — coordinator health check hook.
 *
 * Fetches GET /health on mount and polls every 30 seconds.
 * Uses AbortController to cancel in-flight requests on unmount.
 * Cleans up the interval on unmount to avoid memory leaks.
 *
 * Returns:
 *   data    — { status: string, version: string } | null
 *   loading — boolean (true only on first load)
 *   error   — Error | null
 *   refetch — function to manually trigger a refresh
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { getHealth } from '../services/healthService.js';

const POLL_INTERVAL_MS = 30_000;

/**
 * @returns {{ data: object|null, loading: boolean, error: Error|null, refetch: function }}
 */
export function useHealth() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  // Track whether the component is still mounted
  const mountedRef  = useRef(true);
  const intervalRef = useRef(null);
  // Incrementing request ID prevents a slow earlier response from overwriting
  // a newer one (request-ID pattern)
  const reqIdRef    = useRef(0);

  const doFetch = useCallback(async () => {
    const thisId = ++reqIdRef.current;
    try {
      const result = await getHealth();
      if (mountedRef.current && thisId === reqIdRef.current) {
        setData(result);
        setError(null);
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
    intervalRef.current = setInterval(doFetch, POLL_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      clearInterval(intervalRef.current);
    };
  }, [doFetch]);

  return { data, loading, error, refetch: doFetch };
}
