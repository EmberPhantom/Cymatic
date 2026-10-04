// Edge-safe token gate (Phase C-Web P1).
//
// The middleware runs in the edge runtime without the API secret, so it
// cannot *verify* the HS256 signature — full verification stays in the API.
// This module provides the cheap structural hardening: reject cookies that
// are not 3-part JWTs, whose payload is not base64url JSON, whose `exp` is
// malformed, or whose `exp` is in the past. Tokens without an `exp` claim
// pass the edge gate (the API decides); everything else malformed does not.
//
// No Node imports: safe for the edge runtime, jsdom, and vitest.

const EDGE_CLOCK_SKEW_SEC = 30

function base64UrlDecode(segment: string): string {
  let b64 = segment.replace(/-/g, "+").replace(/_/g, "/")
  const pad = b64.length % 4
  if (pad === 2) b64 += "=="
  else if (pad === 3) b64 += "="
  else if (pad !== 0) throw new Error("invalid base64url length")
  const binary = atob(b64) // throws on invalid alphabet
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0) & 0xff)
  return new TextDecoder().decode(bytes)
}

/**
 * Returns true when `raw` is a JWT-shaped token that is not provably
 * expired/malformed. `nowSec` is injectable for tests.
 */
export function isEdgeAuthenticated(raw: string | undefined | null, nowSec?: number): boolean {
  if (!raw) return false
  const parts = raw.split(".")
  if (parts.length !== 3 || !parts[0] || !parts[1] || !parts[2]) return false
  try {
    const payload = JSON.parse(base64UrlDecode(parts[1])) as unknown
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) return false
    const exp = (payload as Record<string, unknown>).exp
    if (exp === undefined || exp === null) return true // no exp: API verifies
    const expSec =
      typeof exp === "number" ? exp : typeof exp === "string" && exp.trim() !== "" ? Number(exp) : NaN
    if (!Number.isFinite(expSec)) return false // malformed exp
    const now = nowSec ?? Math.floor(Date.now() / 1000)
    return expSec > now - EDGE_CLOCK_SKEW_SEC
  } catch {
    return false
  }
}
