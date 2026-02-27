/** Base URL for REST API (same-origin `/api` by default). No trailing slash. */
export function getApiBase(): string {
  // For dev with Vite proxy we want all calls to hit `/api`,
  // which Vite forwards to `http://localhost:8080` on the lab PC.
  return (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
}

/** Base URL for WebSockets (same-origin `/api` by default). No trailing slash. */
export function getWsBase(): string {
  // Allow explicit override when needed (e.g. production deployment).
  if (import.meta.env.VITE_WS_BASE_URL) {
    return (import.meta.env.VITE_WS_BASE_URL as string).replace(/\/$/, '');
  }

  if (typeof window !== 'undefined') {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Use the same host/port as the page (e.g. 100.x.x.x:5173 over VPN),
    // and let Vite's proxy forward `/api` to the backend on localhost:8080.
    return `${wsProtocol}//${window.location.host}/api`.replace(/\/$/, '');
  }

  // Fallback for non-browser environments; mainly for local dev.
  return 'ws://localhost:5173/api';
}
