import axios from "axios"

export const api = axios.create({
  baseURL: "",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
})

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    try {
      const raw = localStorage.getItem("auth-storage")
      let token: string | null = null
      if (raw) {
        const parsed = JSON.parse(raw)
        token = parsed?.state?.token || parsed?.state?.accessToken || parsed?.accessToken || null
      }
      if (!token) {
        // fallback to zustand store without persist (in-memory)
        const storeRaw = (window as any).__authToken
        if (storeRaw) token = storeRaw
      }
      if (token) config.headers.Authorization = `Bearer ${token}`
    } catch {}
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      const path = window.location.pathname
      if (!path.startsWith("/login") && !path.startsWith("/register")) {
        window.location.assign(`/login?next=${encodeURIComponent(path)}`)
      }
    }
    return Promise.reject(error)
  },
)
