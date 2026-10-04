import { describe, expect, it } from "vitest"
import { parseProjectId } from "./project-id"

describe("parseProjectId", () => {
  it("accepts positive integer strings", () => {
    expect(parseProjectId("42")).toBe(42)
    expect(parseProjectId(" 7 ")).toBe(7)
  })

  it("rejects NaN-producing input (builder page bug: Number(params.id))", () => {
    expect(parseProjectId("abc")).toBeNull()
    expect(parseProjectId("")).toBeNull()
    expect(parseProjectId(undefined)).toBeNull()
    expect(parseProjectId(null)).toBeNull()
    expect(parseProjectId(Number.NaN)).toBeNull()
  })

  it("rejects non-positive, fractional, and unsafe values", () => {
    expect(parseProjectId("0")).toBeNull()
    expect(parseProjectId("-3")).toBeNull()
    expect(parseProjectId("4.5")).toBeNull()
    expect(parseProjectId("1e21")).toBeNull()
    expect(parseProjectId(3.14)).toBeNull()
  })

  it("takes the first segment of catch-all arrays", () => {
    expect(parseProjectId(["9", "extra"])).toBe(9)
    expect(parseProjectId(["oops"])).toBeNull()
  })
})
