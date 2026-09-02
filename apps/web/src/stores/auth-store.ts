import { create } from "zustand"
import { persist } from "zustand/middleware"
import type { User } from "@/types"

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  authReady: boolean
  setAuth: (user: User, token?: string | null) => void
  setAuthReady: (ready: boolean) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      authReady: false,
      setAuth: (user, token = null) => {
        if (typeof window !== "undefined" && token) {
          (window as any).__authToken = token
        }
        set({ user, token, isAuthenticated: true, authReady: true })
      },
      setAuthReady: (authReady) => {
        set({ authReady })
      },
      logout: () => {
        if (typeof window !== "undefined") (window as any).__authToken = null
        set({ user: null, token: null, isAuthenticated: false, authReady: true })
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({ user: state.user, token: state.token, isAuthenticated: state.isAuthenticated }),
    }
  )
)
