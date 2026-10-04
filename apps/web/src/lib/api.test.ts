// Verifies parked failedQueue requests re-execute with the REFRESHED token,
// not the stale Authorization header they were originally sent with.
import { describe, expect, it, vi } from "vitest"
import type { InternalAxiosRequestConfig } from "axios"

type CapturedCall = { url: string; authorization: string | undefined }

async function loadFreshApi(captured: CapturedCall[], refreshCalls: { count: number }) {
  vi.resetModules()
  // NOTE: both api and the store must come from the FRESH module registry —
  // api.ts reads the token via useAuthStore.getState(), so setting the token
  // on a stale store instance would silently no-op.
  const { api } = await import("./api")
  const { useAuthStore } = await import("@/stores/auth-store")

  api.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    const url = config.url || ""
    const headers = (config.headers ?? {}) as unknown as Record<string, string>
    if (url.includes("/v1/auth/refresh")) {
      refreshCalls.count += 1
      return {
        data: { access_token: "new-token" },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      }
    }
    captured.push({ url, authorization: headers.Authorization ?? headers.authorization })
    if ((headers.Authorization ?? headers.authorization) === "Bearer old-token") {
      // Simulate axios's own 401 rejection shape (config + response).
      throw {
        config,
        response: { status: 401, data: { detail: "expired" }, headers: {}, config },
        isAxiosError: true,
      }
    }
    return { data: { ok: true }, status: 200, statusText: "OK", headers: {}, config }
  }
  return { api, useAuthStore }
}

const testUser = { id: 1, email: "t@example.com", name: "T", role: "creator" } as never

describe("api refresh queue", () => {
  it("retries a single 401 with the refreshed token", async () => {
    const captured: CapturedCall[] = []
    const refreshCalls = { count: 0 }
    const { api, useAuthStore } = await loadFreshApi(captured, refreshCalls)
    useAuthStore.getState().setAuth(testUser, "old-token")

    const res = await api.get("/v1/projects/1")
    expect(res.status).toBe(200)
    expect(refreshCalls.count).toBe(1)
    // First attempt stale, retry carries the refreshed token.
    expect(captured.map((c) => c.authorization)).toEqual(["Bearer old-token", "Bearer new-token"])
  })

  it("parked concurrent 401s share one refresh and all retry with the new token", async () => {
    const captured: CapturedCall[] = []
    const refreshCalls = { count: 0 }
    const { api, useAuthStore } = await loadFreshApi(captured, refreshCalls)
    useAuthStore.getState().setAuth(testUser, "old-token")

    const [r1, r2] = await Promise.all([api.get("/v1/projects/1"), api.get("/v1/projects/2")])
    expect(r1.status).toBe(200)
    expect(r2.status).toBe(200)
    expect(refreshCalls.count).toBe(1)
    const retries = captured.filter((c) => c.authorization === "Bearer new-token")
    expect(retries.length).toBe(2)
    // No retry ever reuses the stale header.
    const staleRetries = captured.slice(2)
    expect(staleRetries.every((c) => c.authorization === "Bearer new-token")).toBe(true)
  })
})
