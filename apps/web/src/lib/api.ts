// Axios retained intentionally (interceptors, refresh queue, typed errors).
// Bundle cost ~14kB gz; tree-shaking N/A (CJS) but deduped via optimizePackageImports is not applicable.
// Fetch-native alternative would save ~10kB but requires rewriting queue + interceptors — defer until bundle budget tightens.
// If migrating: replace with `fetch` + custom `fetchWithRefresh` wrapper; keep same `api` export shape.
import axios, { type AxiosRequestConfig, type InternalAxiosRequestConfig } from "axios"
import { useAuthStore } from "@/stores/auth-store"

export const DEFAULT_REQUEST_TIMEOUT_MS = 30_000
// Intake/clarify are synchronous LLM calls (120s/180s router timeouts + cold
// Ollama warmup ~60-180s). The 30s default aborts first-run generation with
// "timeout of 30000ms exceeded", so long LLM endpoints override per-request.
export const LONG_REQUEST_TIMEOUT_MS = 180_000

// Next.js's built-in rewrites() proxy (see next.config.js) kills the upstream
// connection ("socket hang up" / ECONNRESET) well before a slow intake/clarify
// LLM call finishes, returning a 500 regardless of LONG_REQUEST_TIMEOUT_MS.
// Those two calls go straight to the API's public origin instead, bypassing
// the proxy; CORS already allows this origin with credentials.
export const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export const api = axios.create({
  baseURL: "",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
  timeout: DEFAULT_REQUEST_TIMEOUT_MS,
})

// Attach the in-memory access token as a fallback for deployments where the
// HttpOnly cookie has not propagated yet (e.g. immediately after login) or
// where rewrites strip cookies. Cookies remain the primary mechanism.
api.interceptors.request.use((config) => {
  try {
    const token = useAuthStore.getState().token
    const url = config.url || ""
    const isAuthRoute = url.includes("/v1/auth/login") || url.includes("/v1/auth/register") || url.includes("/api/auth/")
    if (token && !isAuthRoute && !config.headers?.Authorization && !config.headers?.authorization) {
      config.headers = config.headers ?? {}
      ;(config.headers as Record<string, string>).Authorization = `Bearer ${token}`
    }
  } catch {
    // store unavailable (SSR) — fall through to cookie auth
  }
  return config
})

let isRefreshing = false
let failedQueue: Array<{ resolve: (v: string | null) => void; reject: (e: unknown) => void }> = []

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token)))
  failedQueue = []
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as (AxiosRequestConfig & { _retry?: boolean }) | undefined
    if (error.response?.status === 401 && !originalRequest?._retry && typeof window !== "undefined") {
      const path = window.location.pathname
      if (path.startsWith("/login") || path.startsWith("/register")) return Promise.reject(error)
      if (originalRequest?.url?.includes("/v1/auth/refresh") || originalRequest?.url?.includes("/api/auth/")) {
        window.location.assign(`/login?next=${encodeURIComponent(path)}`)
        return Promise.reject(error)
      }
      if (isRefreshing) {
        if (!originalRequest) return Promise.reject(error)
        const req = originalRequest
        return new Promise((resolve, reject) => failedQueue.push({ resolve, reject }))
          .then(() => api(req))
          .catch((err) => Promise.reject(err))
      }
      if (!originalRequest) return Promise.reject(error)
      originalRequest._retry = true
      isRefreshing = true
      try {
        const refreshRes = await api.post("/v1/auth/refresh", {}, { withCredentials: true })
        // Store refreshed access token so retry uses fresh header (was stale).
        const newToken = (refreshRes.data as { access_token?: string })?.access_token ?? null
        if (newToken) {
          try {
            const st = useAuthStore.getState()
            if (st.user) st.setAuth(st.user, newToken)
          } catch {
            // SSR-safe: cookies remain primary
          }
        }
        processQueue(null, newToken ?? "refreshed")
        if (originalRequest.headers && newToken) {
          const h = originalRequest.headers as unknown as Record<string, string>
          h.Authorization = `Bearer ${newToken}`
        }
        return api(originalRequest as InternalAxiosRequestConfig)
      } catch (refreshError) {
        processQueue(refreshError, null)
        window.location.assign(`/login?next=${encodeURIComponent(path)}`)
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(error)
  }
)
