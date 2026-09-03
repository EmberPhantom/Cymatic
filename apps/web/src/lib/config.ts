export const config = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  wsUrl: process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000",
  minioUrl: process.env.NEXT_PUBLIC_MINIO_URL || "http://localhost:9000",
  stunUrl: process.env.NEXT_PUBLIC_STUN_URL || "stun:stun.l.google.com:19302",
  turnUrl: process.env.NEXT_PUBLIC_TURN_URL || "",
  turnUsername: process.env.NEXT_PUBLIC_TURN_USERNAME || "",
  turnPassword: process.env.NEXT_PUBLIC_TURN_PASSWORD || "",
  maxUploadMB: Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB || 50),
  jobTimeoutMs: Number(process.env.NEXT_PUBLIC_JOB_TIMEOUT_MS || 5 * 60 * 1000),
  isProduction: process.env.NODE_ENV === "production",
} as const
