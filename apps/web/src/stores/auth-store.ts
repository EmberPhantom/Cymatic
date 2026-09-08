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
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      authReady: false,
      setAuth: (user, token = null) => {
        // token kept in memory, not persisted; cookie is source of truth
        const prevToken = get().token
        set({ user, token: token ?? prevToken, isAuthenticated: true, authReady: true })
      },
      setAuthReady: (authReady) => {
        set({ authReady })
      },
      logout: () => {
        set({ user: null, token: null, isAuthenticated: false, authReady: true })
      },
    }),
    {
      name: "auth-storage",
      version: 1,
      partialize: (state) => ({ user: state.user }),
      onRehydrateStorage: () => (state) => {
        // After rehydration, require cookie validation; mark not authenticated until /v1/auth/me succeeds
        if (state) {
          state.authReady = false
          state.isAuthenticated = false
          state.token = null
        }
      },
      skipHydration: false,
    }
  )
)
