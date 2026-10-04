import { useMutation } from "@tanstack/react-query"
import { api, API_ORIGIN } from "@/lib/api"
import type { StreamSession } from "@/types"

export function useCreateStreamSession() {
  return useMutation<StreamSession, Error, { projectId: number }>({
    mutationFn: async ({ projectId }) => {
      const res = await api.post("/v1/stream/sessions", {
        project_id: projectId,
        device_info: { type: "web", browser: navigator.userAgent },
      })
      return res.data
    },
  })
}

// Session ids are UUID strings (see StreamSession.id) — never numbers. The
// previous `Number(sid)` coercion turned every real id into NaN and fell back
// to an `as unknown as number` cast that only worked by accident.
export function useEndStreamSession() {
  return useMutation<StreamSession, Error, { sessionId: string }>({
    mutationFn: async ({ sessionId }) => {
      if (!sessionId) throw new Error("Invalid session id")
      const res = await api.post(`/v1/stream/sessions/${encodeURIComponent(sessionId)}/end`)
      return res.data
    },
  })
}

// Best-effort unload beacon for ending a session. Routed through the same
// API-origin base as the rest of the app (not a relative path, which would
// hit the Next rewrite proxy on a different origin in production).
export function endSessionBeaconUrl(sessionId: string): string {
  return `${API_ORIGIN}/v1/stream/sessions/${encodeURIComponent(sessionId)}/end`
}
