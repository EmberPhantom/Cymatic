import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook } from "@testing-library/react"
import { waitFor } from "@testing-library/dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import React from "react"
import { useProjects } from "./use-projects"

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(() => Promise.resolve({ data: [{ id: 1, name: "Test" }] })) },
}))

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return React.createElement(QueryClientProvider, { client: qc }, children)
}

describe("useProjects", () => {
  it("fetches projects", async () => {
    const { result } = renderHook(() => useProjects(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.length).toBe(1)
  })
})
