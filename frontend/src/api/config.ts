/**
 * Runtime backend base URL for API and WebSockets.
 * When the app is opened from a remote host (e.g. Tailscale IP), use that host
 * for the backend so API/WS connect to the lab PC, not the client's localhost.
 */
function isLocalHost(): boolean {
  if (typeof window === 'undefined') return true;
  const h = window.location.hostname;
  return h === 'localhost' || h === '127.0.0.1';
}

/** Base URL for REST API (e.g. http://100.x.x.x:8080/api). No trailing slash. */
export function getApiBase(): string {
  if (typeof window !== 'undefined' && !isLocalHost()) {
    const protocol = window.location.protocol;
    const host = window.location.hostname;
    return `${protocol}//${host}:8080/api`.replace(/\/$/, '');
  }
  return (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
}

/** Base URL for WebSockets (e.g. ws://100.x.x.x:8080/api). No trailing slash. */
export function getWsBase(): string {
  if (import.meta.env.VITE_WS_BASE_URL) {
    return (import.meta.env.VITE_WS_BASE_URL as string).replace(/\/$/, '');
  }
  if (typeof window !== 'undefined' && !isLocalHost()) {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;
    return `${wsProtocol}//${host}:8080/api`;
  }
  return 'ws://localhost:8080/api';
}
