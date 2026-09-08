import axios from "axios"

export const api = axios.create({
  baseURL: "",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
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
