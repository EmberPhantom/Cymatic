import axios from "axios"

export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
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
