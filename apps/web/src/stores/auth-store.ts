import { create } from "zustand"
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

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  authReady: false,
  setAuth: (user, token = null) => {
    set({ user, token, isAuthenticated: true, authReady: true })
  },
  setAuthReady: (authReady) => {
    set({ authReady })
  },
  logout: () => {
    set({ user: null, token: null, isAuthenticated: false, authReady: true })
  },
}))
