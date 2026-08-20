import { create } from "zustand"
import type { User } from "@/types"

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  setAuth: (user: User, token: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: typeof window !== "undefined" ? localStorage.getItem("cymatic_token") : null,
  isAuthenticated: typeof window !== "undefined" ? !!localStorage.getItem("cymatic_token") : false,
  setAuth: (user, token) => {
    localStorage.setItem("cymatic_token", token)
    set({ user, token, isAuthenticated: true })
  },
  logout: () => {
    localStorage.removeItem("cymatic_token")
    set({ user: null, token: null, isAuthenticated: false })
  },
}))
