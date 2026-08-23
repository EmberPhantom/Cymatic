import { beforeEach, describe, expect, it } from "vitest"
import { useAuthStore } from "./auth-store"

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({ user: null, token: null, isAuthenticated: false })
  })

  it("persists authentication and clears it on logout", () => {
    const user = { id: 1, email: "test@example.com", name: "Test User", role: "creator" } as never

    useAuthStore.getState().setAuth(user, "token-123")
    expect(localStorage.getItem("cymatic_token")).toBe("token-123")
    expect(useAuthStore.getState().isAuthenticated).toBe(true)

    useAuthStore.getState().logout()
    expect(localStorage.getItem("cymatic_token")).toBeNull()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})
