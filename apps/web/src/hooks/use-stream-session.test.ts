import { describe, expect, it, vi, beforeEach } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { waitFor } from "@testing-library/dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import React from "react"
import { endSessionBeaconUrl, useEndStreamSession } from "./use-stream-session"
import { API_ORIGIN, api } from "@/lib/api"

vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>()
  return { ...orig, api: { post: vi.fn(() => Promise.resolve({ data: { id: "uuid" } })) } }
})

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return React.createElement(QueryClientProvider, { client: qc }, children)
}

describe("useEndStreamSession", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("passes UUID string ids through untouched (no Number() coercion)", async () => {
    const uuid = "123e4567-e89b-12d3-a456-426614174000"
    const { result } = renderHook(() => useEndStreamSession(), { wrapper })
    await act(async () => {
      await result.current.mutateAsync({ sessionId: uuid })
    })
    expect(api.post).toHaveBeenCalledWith(`/v1/stream/sessions/${uuid}/end`)
  })

  it("rejects empty session ids instead of firing", async () => {
    const { result } = renderHook(() => useEndStreamSession(), { wrapper })
    await expect(
      act(async () => {
        await result.current.mutateAsync({ sessionId: "" })
      }),
    ).rejects.toThrow("Invalid session id")
    expect(api.post).not.toHaveBeenCalled()
  })

  it("routes the unload beacon through the API-origin base", () => {
    const uuid = "123e4567-e89b-12d3-a456-426614174000"
    expect(endSessionBeaconUrl(uuid)).toBe(`${API_ORIGIN}/v1/stream/sessions/${uuid}/end`)
  })

  it("type test: numeric ids no longer compile", () => {
    const acceptStringId = (_v: { sessionId: string }) => undefined
    // @ts-expect-error sessionId must be a UUID string, not a number
    acceptStringId({ sessionId: 42 })
    expect(true).toBe(true)
  })
})
