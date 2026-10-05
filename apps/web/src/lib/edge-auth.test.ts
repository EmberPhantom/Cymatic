import { describe, expect, it } from "vitest"
import { isEdgeAuthenticated } from "./edge-auth"

function b64url(obj: unknown): string {
  return Buffer.from(JSON.stringify(obj), "utf8").toString("base64url")
}

const NOW = 1_700_000_000

function token(payload: unknown): string {
  return `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url(payload)}.sig`
}

describe("isEdgeAuthenticated", () => {
  it("rejects empty / garbage cookies", () => {
    expect(isEdgeAuthenticated("", NOW)).toBe(false)
    expect(isEdgeAuthenticated(null, NOW)).toBe(false)
    expect(isEdgeAuthenticated(undefined, NOW)).toBe(false)
    expect(isEdgeAuthenticated("garbage", NOW)).toBe(false)
    expect(isEdgeAuthenticated("a.b", NOW)).toBe(false)
    expect(isEdgeAuthenticated("a.b.c.d", NOW)).toBe(false)
  })

  it("rejects JWT-shaped garbage (bad base64 / non-JSON / non-object)", () => {
    expect(isEdgeAuthenticated("a.!!!.c", NOW)).toBe(false)
    const notJson = `${b64url({ alg: "x" })}.bm90LWpzb24.sig` // "not-json"
    expect(isEdgeAuthenticated(notJson, NOW)).toBe(false)
    expect(isEdgeAuthenticated(token([1, 2, 3]), NOW)).toBe(false)
    expect(isEdgeAuthenticated(token("str"), NOW)).toBe(false)
  })

  it("rejects expired tokens", () => {
    expect(isEdgeAuthenticated(token({ sub: "1", exp: NOW - 3600 }), NOW)).toBe(false)
  })

  it("rejects malformed exp", () => {
    expect(isEdgeAuthenticated(token({ sub: "1", exp: "soon" }), NOW)).toBe(false)
    expect(isEdgeAuthenticated(token({ sub: "1", exp: true }), NOW)).toBe(false)
    expect(isEdgeAuthenticated(token({ sub: "1", exp: { v: 1 } }), NOW)).toBe(false)
  })

  it("accepts unexpired tokens (numeric or numeric-string exp)", () => {
    expect(isEdgeAuthenticated(token({ sub: "1", exp: NOW + 3600 }), NOW)).toBe(true)
    expect(isEdgeAuthenticated(token({ sub: "1", exp: String(NOW + 3600) }), NOW)).toBe(true)
  })

  it("passes tokens without exp (API verifies)", () => {
    expect(isEdgeAuthenticated(token({ sub: "1" }), NOW)).toBe(true)
  })

  it("tolerates small clock skew", () => {
    expect(isEdgeAuthenticated(token({ sub: "1", exp: NOW - 10 }), NOW)).toBe(true)
  })
})
