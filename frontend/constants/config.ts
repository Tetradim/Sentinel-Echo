/**
 * Backend URL config.
 * In the desktop launcher this defaults to localhost:8003.
 * In mobile/web builds it comes from EXPO_PUBLIC_BACKEND_URL.
 */
export const BACKEND_URL: string =
  process.env.EXPO_PUBLIC_BACKEND_URL || 'http://localhost:8003';

// Demo mode is opt-in; the local launcher starts the real backend by default.
export const DEMO_MODE = process.env.EXPO_PUBLIC_DEMO_MODE === 'true';
