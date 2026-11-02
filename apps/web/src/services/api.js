/**
 * CrowdGPU API base client.
 *
 * All coordinator HTTP calls must go through apiFetch so that:
 *   - base URL is consistently resolved from environment.js
 *   - requests time out after REQUEST_TIMEOUT_MS
 *   - HTTP errors produce clear, user-readable messages
 *   - FastAPI { detail } error bodies are surfaced correctly
 *   - network failures produce a friendly message (not a raw browser error)
 *
 * ── Architecture ──────────────────────────────────────────────────────────────
 *   Page → Hook → Service → apiFetch → Coordinator
 *
 * ── Base URL resolution ───────────────────────────────────────────────────────
 *   VITE_API_BASE_URL=''         → relative path; Vite proxy handles /api/*
 *   VITE_API_BASE_URL=https://…  → absolute URL to remote Coordinator
 *
 * See src/utils/environment.js for environment helpers.
 */

import { getApiBaseUrl } from '../utils/environment.js';

/** Abort after 10 seconds. Adjust if the Coordinator has known slow endpoints. */
const REQUEST_TIMEOUT_MS = 10_000;

/**
 * Fetch wrapper for the CrowdGPU Coordinator API.
 *
 * @param {string} path    Absolute path, e.g. '/api/v1/peers/123'
 * @param {RequestInit} [options]  Standard fetch options (method, body, …)
 * @returns {Promise<unknown>}     Parsed JSON, or raw text if not JSON.
 * @throws {Error} On network failure, timeout, or non-2xx HTTP status.
 *   err.status  — HTTP status code (number) or undefined for network errors
 *   err.data    — raw response body, if available
 */
export async function apiFetch(path, options = {}) {
  const baseUrl = (getApiBaseUrl() || '').replace(/\/+$/, '');
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const url = `${baseUrl}${cleanPath}`;

  const demoUserId = import.meta.env.VITE_DEMO_USER_ID || '00000000-0000-0000-0000-000000000001';

  // ── Timeout via AbortController ──────────────────────────────────────────
  const controller = new AbortController();
  const timeoutId  = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response;
  try {
    response = await fetch(url, {
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': demoUserId,
        ...(options.headers ?? {}),
      },
      ...options,
    });
  } catch (networkErr) {
    clearTimeout(timeoutId);

    // AbortError → timeout
    if (networkErr?.name === 'AbortError') {
      const err = new Error('Request timed out. Please try again.');
      err.status = 408;
      throw err;
    }

    // Network-level failure (no connection, DNS failure, CORS, etc.)
    const err = new Error('Unable to reach the Coordinator. Check your network connection.');
    err.status = 0;
    err.cause  = networkErr;
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }

  // ── Parse body ────────────────────────────────────────────────────────────
  const contentType = response.headers.get('content-type') ?? '';
  let data;
  try {
    data = contentType.includes('application/json')
      ? await response.json()
      : await response.text();
  } catch {
    data = null;
  }

  // ── HTTP error mapping ────────────────────────────────────────────────────
  if (!response.ok) {
    const message = extractErrorMessage(response.status, data);
    const err = new Error(message);
    err.status = response.status;
    err.data   = data;
    throw err;
  }

  return data;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Produce a user-readable error message from HTTP status and parsed body.
 * FastAPI returns { detail: string | ValidationError[] } on 4xx/5xx.
 *
 * @param {number} status
 * @param {unknown} data
 * @returns {string}
 */
function extractErrorMessage(status, data) {
  // Try to surface a FastAPI { detail } message
  if (data && typeof data === 'object') {
    const detail = data.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail.trim();
    }
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((e) => e.msg ?? String(e)).join('; ');
    }
    if (typeof data.message === 'string' && data.message.trim()) {
      return data.message.trim();
    }
  }

  // Status-specific fallbacks
  switch (status) {
    case 400: return 'Invalid request. Check the submitted values and try again.';
    case 401: return 'Authentication required.';
    case 403: return 'You do not have permission to perform this action.';
    case 404: return 'Resource not found.';
    case 408: return 'Request timed out. Please try again.';
    case 409: return 'Conflict — the resource state does not allow this operation.';
    case 422: return 'Validation error. Check the request fields.';
    case 500: return 'Coordinator returned an internal server error.';
    case 502: return 'Coordinator is unavailable (bad gateway).';
    case 503: return 'Coordinator is temporarily unavailable. Please try again shortly.';
    default:  return `Request failed with status ${status}.`;
  }
}
