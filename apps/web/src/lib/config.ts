function _num(v: string | undefined, fallback: number): number {
  const n = Number(v ?? fallback)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

function _url(v: string | undefined, fallback: string): string {
  const s = (v ?? fallback).trim() || fallback
  try {
    // Throws on invalid URL (e.g. missing scheme from bad env).
    new URL(s)
    return s
  } catch {
    return fallback
  }
}

export const config = {
  apiUrl: _url(process.env.NEXT_PUBLIC_API_URL, "http://localhost:8000"),
  wsUrl: (process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000").trim() || "ws://localhost:8000",
  minioUrl: _url(process.env.NEXT_PUBLIC_MINIO_URL, "http://localhost:9000"),
  stunUrl: process.env.NEXT_PUBLIC_STUN_URL || "stun:stun.l.google.com:19302",
  turnUrl: process.env.NEXT_PUBLIC_TURN_URL || "",
  turnUsername: process.env.NEXT_PUBLIC_TURN_USERNAME || "",
  turnPassword: process.env.NEXT_PUBLIC_TURN_PASSWORD || "",
  maxUploadMB: _num(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB, 50),
  jobTimeoutMs: _num(process.env.NEXT_PUBLIC_JOB_TIMEOUT_MS, 5 * 60 * 1000),
  isProduction: process.env.NODE_ENV === "production",
} as const
