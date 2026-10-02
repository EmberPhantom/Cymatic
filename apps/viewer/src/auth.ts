const API_URL = (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:8000";
const STORAGE_KEY = "cymatic_viewer_tokens";

interface Tokens {
  access_token: string;
  refresh_token: string;
}

let tokens: Tokens | null = loadTokens();

function loadTokens(): Tokens | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    return null;
  }
}

function saveTokens(t: Tokens) {
  tokens = t;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(t));
}

export function isLoggedIn(): boolean {
  return tokens !== null;
}

export function logout() {
  tokens = null;
  localStorage.removeItem(STORAGE_KEY);
}

export async function login(email: string, password: string): Promise<void> {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  const res = await fetch(`${API_URL}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    throw new Error(res.status === 401 ? "Invalid email or password" : `Login failed (${res.status})`);
  }
  saveTokens((await res.json()) as Tokens);
}

async function refresh(): Promise<boolean> {
  if (!tokens) return false;
  const res = await fetch(`${API_URL}/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token: tokens.refresh_token }),
  });
  if (!res.ok) {
    logout();
    return false;
  }
  saveTokens((await res.json()) as Tokens);
  return true;
}

/** Authenticated fetch against the CYMATIC API. Retries once after a token refresh on 401. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (!tokens) throw new Error("Not logged in");

  const doFetch = () =>
    fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        ...(init.headers || {}),
        Authorization: `Bearer ${tokens!.access_token}`,
      },
    });

  let res = await doFetch();
  if (res.status === 401 && (await refresh())) {
    res = await doFetch();
  }
  return res;
}

export { API_URL };
