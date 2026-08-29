import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
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

export function useEndStreamSession() {
  return useMutation<StreamSession, Error, { sessionId: number }>({
    mutationFn: async ({ sessionId }) => {
      const res = await api.post(`/v1/stream/sessions/${sessionId}/end`)
      return res.data
    },
  })
}
