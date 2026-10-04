const API_URL = (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:8000";

// In-memory only: tokens are NEVER persisted to localStorage (XSS-readable).
// Mirrors apps/web's auth-store — the HttpOnly cookie set by /v1/auth/login
// is the source of truth; the memory token is a fallback for deployments
// where the cookie has not propagated yet. A page reload therefore requires
// re-login only when the cookie is also absent (refresh() below covers the
// cookie-present case).
let accessToken: string | null = null;

function decodeExp(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1] as string)) as { exp?: unknown };
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

/** True only with a non-expired in-memory access token. */
export function isLoggedIn(): boolean {
  if (!accessToken) return false;
  const exp = decodeExp(accessToken);
  if (exp !== null && exp * 1000 <= Date.now()) {
    accessToken = null;
    return false;
  }
  return true;
}

export function logout() {
  accessToken = null;
  // Best-effort server-side cookie clear; ignore failures (offline etc.).
  fetch(`${API_URL}/v1/auth/logout`, { method: "POST", credentials: "include" }).catch(() => {});
}

export async function login(email: string, password: string): Promise<void> {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  const res = await fetch(`${API_URL}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    // Required so the HttpOnly auth cookies are stored.
    credentials: "include",
    body,
  });
  if (!res.ok) {
    throw new Error(res.status === 401 ? "Invalid email or password" : `Login failed (${res.status})`);
  }
  const data = (await res.json()) as { access_token?: string };
  accessToken = typeof data.access_token === "string" ? data.access_token : null;
}

async function refresh(): Promise<boolean> {
  // Cookie-first refresh: the backend accepts the HttpOnly
  // cymatic_refresh_token cookie when the body token is absent, so no
  // refresh token is stored anywhere on this client.
  const res = await fetch(`${API_URL}/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({}),
  }).catch(() => null);
  if (!res || !res.ok) {
    logout();
    return false;
  }
  const data = (await res.json()) as { access_token?: string };
  if (typeof data.access_token !== "string" || !data.access_token) {
    logout();
    return false;
  }
  accessToken = data.access_token;
  return true;
}

/** Authenticated fetch against the CYMATIC API. Retries once after a token refresh on 401. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const doFetch = () =>
    fetch(`${API_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        ...(init.headers || {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
    });

  let res = await doFetch();
  if (res.status === 401 && (await refresh())) {
    res = await doFetch();
  }
  return res;
}

/** Cookie-based session restore after reload (mirrors apps/web's
 * cookie-validation on rehydrate). Uses only the HttpOnly cookie — succeeds
 * without any stored token. */
export async function tryRestoreSession(): Promise<boolean> {
  if (isLoggedIn()) return true;
  return refresh();
}

export { API_URL };
