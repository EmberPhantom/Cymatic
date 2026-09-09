// Axios retained intentionally (interceptors, refresh queue, typed errors).
// Bundle cost ~14kB gz; tree-shaking N/A (CJS) but deduped via optimizePackageImports is not applicable.
// Fetch-native alternative would save ~10kB but requires rewriting queue + interceptors — defer until bundle budget tightens.
// If migrating: replace with `fetch` + custom `fetchWithRefresh` wrapper; keep same `api` export shape.
import axios from "axios"
import { useAuthStore } from "@/stores/auth-store"

export const api = axios.create({
  baseURL: "",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
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
    const originalRequest: any = error.config
    if (error.response?.status === 401 && !originalRequest?._retry && typeof window !== "undefined") {
      const path = window.location.pathname
      if (path.startsWith("/login") || path.startsWith("/register")) return Promise.reject(error)
      if (originalRequest?.url?.includes("/v1/auth/refresh") || originalRequest?.url?.includes("/api/auth/")) {
        window.location.assign(`/login?next=${encodeURIComponent(path)}`)
        return Promise.reject(error)
      }
      if (isRefreshing) {
        return new Promise((resolve, reject) => failedQueue.push({ resolve, reject }))
          .then(() => api(originalRequest))
          .catch((err) => Promise.reject(err))
      }
      originalRequest._retry = true
      isRefreshing = true
      try {
        await api.post("/v1/auth/refresh", {}, { withCredentials: true })
        processQueue(null, "refreshed")
        return api(originalRequest)
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
