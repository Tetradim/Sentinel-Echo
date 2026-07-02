/**
 * Backend URL config.
 * The browser can override the backend at runtime with:
 *   ?backend_url=http://127.0.0.1:8003
 *
 * This keeps exported web builds usable when the backend is launched on a
 * non-default local port by the launcher or audit harness.
 */
function getRuntimeBackendUrl(): string | null {
  if (typeof window === 'undefined') return null;

  try {
    const params = new URLSearchParams(window.location.search);
    const urlFromQuery = params.get('backend_url') || params.get('backendUrl');
    if (urlFromQuery) {
      window.localStorage?.setItem('sentinel-echo.backendUrl', urlFromQuery);
      return urlFromQuery;
    }

    if (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost') {
      if (window.location.pathname.startsWith('/app')) return window.location.origin;
      if (window.location.port === '3123') return 'http://127.0.0.1:8123';
      if (window.location.port === '3003') return 'http://127.0.0.1:8003';
    }

    return window.localStorage?.getItem('sentinel-echo.backendUrl');
  } catch {
    return null;
  }
}

export const BACKEND_URL: string =
  getRuntimeBackendUrl() || process.env.EXPO_PUBLIC_BACKEND_URL || 'http://localhost:8003';

// Demo mode is opt-in; the local launcher starts the real backend by default.
export const DEMO_MODE = process.env.EXPO_PUBLIC_DEMO_MODE === 'true';
