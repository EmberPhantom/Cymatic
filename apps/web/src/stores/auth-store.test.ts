import { beforeEach, describe, expect, it } from "vitest"
import { useAuthStore } from "./auth-store"

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({ user: null, token: null, isAuthenticated: false, authReady: false })
  })

  it("persists authentication and clears it on logout", () => {
    const user = { id: 1, email: "test@example.com", name: "Test User", role: "creator" } as never

    useAuthStore.getState().setAuth(user, "token-123")
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(useAuthStore.getState().token).toBe("token-123")
    expect(useAuthStore.getState().authReady).toBe(true)

    useAuthStore.getState().logout()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(useAuthStore.getState().authReady).toBe(true)
  })
})
