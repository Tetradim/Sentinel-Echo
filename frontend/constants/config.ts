/**
 * Backend URL config.
 * In the desktop launcher this defaults to localhost:8003.
 * In mobile/web builds it comes from EXPO_PUBLIC_BACKEND_URL.
 */
export const BACKEND_URL: string =
  process.env.EXPO_PUBLIC_BACKEND_URL || 'http://localhost:8003';

// Demo mode - set to true to show mock data when backend unavailable
export const DEMO_MODE = true;
